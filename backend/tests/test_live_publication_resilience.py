import asyncio
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import deps
from schemas import TradeRecord
from trading import live_publication_resilience_patch as resilience
from trading_engine import TradingEngine


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, _limit):
        return list(self.rows)


class _Trades:
    def __init__(self, persisted=None, rows=None):
        self.persisted = persisted
        self.rows = rows or []
        self.updates = []

    async def find_one(self, query, projection=None):
        if self.persisted and query.get("id") == self.persisted.get("id"):
            return dict(self.persisted)
        return None

    def find(self, query, projection=None):
        return _Cursor(self.rows)

    async def update_one(self, query, update):
        self.updates.append((query, update))


class _BrokerOrders:
    def __init__(self):
        self.updates = []

    async def update_one(self, query, update):
        self.updates.append((query, update))

    async def update_many(self, query, update):
        self.updates.append((query, update))


class _Db:
    def __init__(self, trades):
        self.trades = trades
        self.broker_orders = _BrokerOrders()


def _fill_result(quantity=2.0, price=91.25):
    return {
        "broker_id": "alpaca",
        "status": "filled",
        "broker_order_id": "alpaca-order-1",
        "filled_quantity": quantity,
        "filled_price": price,
    }


def test_persisted_trade_survives_downstream_publication_failure(monkeypatch):
    engine = TradingEngine()
    engine._positions["ASTS"] = {"qty": 2.1, "avg_entry": 90.0, "high": 90.0}
    trade = TradeRecord(
        symbol="ASTS",
        side="BUY",
        price=90.0,
        quantity=2.1,
        total_value=189.0,
        trading_mode="live",
        broker_results=[_fill_result()],
    )
    trades = _Trades(persisted={"id": trade.id})
    monkeypatch.setattr(deps, "db", _Db(trades))

    async def fail_after_persistence(self, normalized_trade):
        normalized_trade.quantity = 2.0
        normalized_trade.price = 91.25
        normalized_trade.total_value = 182.5
        self._positions["ASTS"] = {
            "qty": 2.0,
            "avg_entry": 91.25,
            "high": 91.25,
        }
        raise RuntimeError("websocket unavailable after insert")

    async def save_state():
        return None

    monkeypatch.setattr(resilience, "_current_record_trade", fail_after_persistence)
    engine.save_state = save_state

    result = asyncio.run(
        resilience._record_trade_without_replaying_persisted_fill(engine, trade)
    )

    assert result is None
    assert engine._positions["ASTS"] == {
        "qty": 2.0,
        "avg_entry": 91.25,
        "high": 91.25,
    }
    assert trades.updates
    assert trades.updates[0][1]["$set"]["reconciliation_required"] is True
    assert deps.db.broker_orders.updates


def test_recorded_broker_fill_prevents_reconciliation_replay(monkeypatch):
    recorded = {
        "broker_results": [
            {
                "broker_id": "alpaca",
                "broker_order_id": "alpaca-order-1",
                "filled_quantity": 2.0,
                "filled_price": 91.25,
            }
        ]
    }
    trades = _Trades(rows=[recorded])
    monkeypatch.setattr(deps, "db", _Db(trades))
    engine = TradingEngine()

    async def must_not_apply(*_args, **_kwargs):
        raise AssertionError("durable fill was replayed")

    monkeypatch.setattr(resilience, "_current_apply_fill_delta", must_not_apply)
    order_doc = {
        "intent_key": "ASTS:BUY:LIMIT",
        "broker_id": "alpaca",
        "durable_order_id": "alpaca-order-1",
        "broker_order_id": "alpaca-order-1",
        "applied_quantity": 0.0,
        "applied_notional": 0.0,
    }
    broker_update = {
        "status": "filled",
        "filled_quantity": 2.0,
        "filled_price": 91.25,
    }

    applied = asyncio.run(
        resilience._apply_fill_delta_with_trade_dedup(
            engine,
            order_doc,
            broker_update,
        )
    )

    assert applied == 0.0
    marker = deps.db.broker_orders.updates[0][1]["$set"]
    assert marker["applied_quantity"] == 2.0
    assert marker["applied_notional"] == 182.5
