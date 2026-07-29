import asyncio
from collections import deque
from datetime import datetime, timedelta, timezone

import pytest

import deps
from risk_controls import ExposureLimit, KillSwitchLevel, RiskControls
from schemas import TradeRecord
from trading import execution_order_safety_patch as execution
from trading import partial_publication_safety_patch as publication_fix
from trading import live_position_publication_patch as publication
from trading import live_truth_patch as live_truth
from trading.broker_execution import LiveOrderExecutionError
from trading_engine import TradingEngine


class AsyncCursor:
    def __init__(self, rows):
        self.rows = list(rows)

    def sort(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    async def to_list(self, *args, **kwargs):
        return list(self.rows)


class FakeSettings:
    def __init__(self):
        self.docs = {}

    async def update_one(self, query, update, upsert=False):
        key = query["key"]
        current = self.docs.setdefault(key, {})
        current.update(update.get("$set", {}))

    async def find_one(self, query, projection=None):
        value = self.docs.get(query["key"])
        return {"key": query["key"], **value} if value is not None else None


class FakeTickers:
    def __init__(self, rows):
        self.rows = list(rows)

    def find(self, query=None, projection=None):
        return AsyncCursor(self.rows)

    async def find_one(self, query, projection=None):
        symbol = query.get("symbol")
        return next((row for row in self.rows if row.get("symbol") == symbol), None)


class FakeTrades:
    def find(self, query=None, projection=None):
        return AsyncCursor([])


class FakeDb:
    def __init__(self, tickers):
        self.settings = FakeSettings()
        self.tickers = FakeTickers(tickers)
        self.trades = FakeTrades()


class FakeBrokerManager:
    def __init__(self, snapshots):
        self.snapshots = snapshots

    async def reconcile_positions(self, broker_id):
        return self.snapshots[broker_id]


def filled_result(side, quantity, price):
    return {
        "broker_id": "alpaca",
        "status": "filled",
        "broker_order_id": f"order-{side.lower()}",
        "filled_quantity": quantity,
        "filled_price": price,
    }


def test_partial_buy_uses_only_leg_allocation(monkeypatch):
    engine = TradingEngine()
    engine._positions["ASTS"] = {
        "qty": 2.0,
        "avg_entry": 90.0,
        "high": 95.0,
        "buy_legs_filled": [0],
    }
    monkeypatch.setattr(
        deps,
        "db",
        FakeDb(
            [
                {
                    "symbol": "ASTS",
                    "broker_ids": ["alpaca", "tradier"],
                    "buy_legs": [
                        {"alloc_pct": 25},
                        {"alloc_pct": 40},
                    ],
                }
            ]
        ),
    )

    allocations, template = asyncio.run(
        execution.prepare_partial_order(
            engine,
            sym="ASTS",
            broker_ids=["alpaca", "tradier"],
            broker_allocs={"alpaca": 600.0, "tradier": 400.0},
            order_template={"side": "BUY", "price": 100.0},
            action_label="PARTIAL_BUY_LEG_2",
        )
    )

    assert template["quantity"] == 4.0
    assert allocations == {"alpaca": 240.0, "tradier": 160.0}
    assert engine._partial_execution_contexts["ASTS:BUY"]["position"]["qty"] == 2.0


def test_live_partial_buy_accumulates_and_preserves_leg_state(monkeypatch):
    engine = TradingEngine()
    previous = {
        "qty": 2.0,
        "avg_entry": 90.0,
        "high": 95.0,
        "buy_legs_filled": [0],
        "sell_legs_filled": [],
    }
    engine._positions["ASTS"] = {
        "qty": 6.0,
        "avg_entry": 96.67,
        "buy_legs_filled": [0, 1],
        "sell_legs_filled": [],
    }
    engine._partial_execution_contexts = {
        "ASTS:BUY": {"position": previous, "leg_index": 1, "side": "BUY"}
    }
    captured = []

    async def fake_record(self, trade):
        captured.append((trade.quantity, trade.price, dict(self._positions["ASTS"])))

    async def fake_mark(self, trade):
        return None

    monkeypatch.setattr(live_truth, "_original_record_trade", fake_record)
    monkeypatch.setattr(publication, "_mark_child_orders_applied", fake_mark)

    trade = TradeRecord(
        symbol="ASTS",
        side="BUY",
        price=100.0,
        quantity=4.0,
        trading_mode="live",
        broker_results=[filled_result("BUY", 4.0, 101.0)],
    )
    asyncio.run(publication_fix.record_trade_with_partial_truth(engine, trade))

    position = engine._positions["ASTS"]
    assert position["qty"] == 6.0
    assert position["avg_entry"] == pytest.approx(97.33333333)
    assert position["buy_legs_filled"] == [0, 1]
    assert captured[0][0:2] == (4.0, 101.0)


def test_live_partial_sell_is_not_subtracted_twice(monkeypatch):
    engine = TradingEngine()
    previous = {
        "qty": 10.0,
        "avg_entry": 90.0,
        "high": 110.0,
        "buy_legs_filled": [0, 1],
        "sell_legs_filled": [],
    }
    # The legacy caller has already applied its optimistic subtraction.
    engine._positions["ASTS"] = {
        "qty": 5.0,
        "avg_entry": 90.0,
        "buy_legs_filled": [0, 1],
        "sell_legs_filled": [0],
    }
    engine._partial_execution_contexts = {
        "ASTS:SELL": {"position": previous, "leg_index": 0, "side": "SELL"}
    }

    async def fake_record(self, trade):
        return None

    async def fake_mark(self, trade):
        return None

    monkeypatch.setattr(live_truth, "_original_record_trade", fake_record)
    monkeypatch.setattr(publication, "_mark_child_orders_applied", fake_mark)

    trade = TradeRecord(
        symbol="ASTS",
        side="SELL",
        price=100.0,
        quantity=5.0,
        entry_price=90.0,
        trading_mode="live",
        broker_results=[filled_result("SELL", 5.0, 100.0)],
    )
    asyncio.run(publication_fix.record_trade_with_partial_truth(engine, trade))

    position = engine._positions["ASTS"]
    assert position["qty"] == 5.0
    assert position["sell_legs_filled"] == [0]
    assert trade.pnl == 50.0


def test_multi_broker_sync_aggregates_and_empty_snapshot_clears(monkeypatch):
    engine = TradingEngine()
    db = FakeDb(
        [
            {
                "symbol": "ASTS",
                "broker_ids": ["alpaca", "tradier"],
            }
        ]
    )
    manager = FakeBrokerManager(
        {
            "alpaca": {
                "ASTS": {
                    "quantity": 3.0,
                    "avg_entry": 90.0,
                    "current_price": 100.0,
                }
            },
            "tradier": {
                "ASTS": {
                    "quantity": 7.0,
                    "avg_entry": 100.0,
                    "current_price": 101.0,
                }
            },
        }
    )
    monkeypatch.setattr(deps, "db", db)
    monkeypatch.setattr(deps, "broker_mgr", manager)

    asyncio.run(engine.sync_positions_from_broker("alpaca"))
    asyncio.run(engine.sync_positions_from_broker("tradier"))

    assert engine._positions["ASTS"]["qty"] == 10.0
    assert engine._positions["ASTS"]["avg_entry"] == 97.0
    assert set(engine._positions["ASTS"]["broker_positions"]) == {"alpaca", "tradier"}

    manager.snapshots["alpaca"] = {}
    asyncio.run(engine.sync_positions_from_broker("alpaca"))
    assert engine._positions["ASTS"]["qty"] == 7.0
    assert set(engine._positions["ASTS"]["broker_positions"]) == {"tradier"}


def test_order_limit_is_a_rolling_minute(monkeypatch):
    monkeypatch.setattr(deps, "engine", None, raising=False)
    controls = RiskControls()
    controls.add_exposure_limit(
        ExposureLimit(
            limit_id="portfolio",
            level="portfolio",
            level_id="global",
            max_orders_per_minute=2,
        )
    )
    controls.update_exposure("portfolio", "global", order_count=1)
    controls.update_exposure("portfolio", "global", order_count=1)
    assert not controls.check_exposure_limit("portfolio", "global").is_allowed

    controls._order_windows_by_limit["portfolio:global"] = deque(
        [datetime.now(timezone.utc) - timedelta(seconds=61)]
    )
    assert controls.check_exposure_limit("portfolio", "global").is_allowed


def test_execution_gateway_honors_symbol_and_broker_controls(monkeypatch):
    engine = TradingEngine()
    monkeypatch.setattr(deps, "engine", None, raising=False)
    engine.risk_controls.add_restricted_symbol("ASTS")

    with pytest.raises(LiveOrderExecutionError, match="restricted"):
        asyncio.run(
            execution.enforce_execution_risk(
                engine,
                symbol="ASTS",
                side="BUY",
                quantity=1.0,
                price=100.0,
                broker_ids=["alpaca"],
            )
        )

    engine.risk_controls.remove_restricted_symbol("ASTS")
    engine.risk_controls.add_kill_switch(KillSwitchLevel.BROKER, "alpaca")
    engine.risk_controls.activate_kill_switch(
        KillSwitchLevel.BROKER, "alpaca", "test", "maintenance"
    )
    with pytest.raises(LiveOrderExecutionError, match="BROKER alpaca"):
        asyncio.run(
            execution.enforce_execution_risk(
                engine,
                symbol="ASTS",
                side="BUY",
                quantity=1.0,
                price=100.0,
                broker_ids=["alpaca"],
            )
        )
