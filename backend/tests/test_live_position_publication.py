import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import deps
from schemas import TradeRecord
from trading import live_position_publication_patch as publication
from trading_engine import TradingEngine


class _BrokerOrders:
    def __init__(self):
        self.updated = []

    async def update_many(self, query, update):
        self.updated.append((query, update))


class _Db:
    def __init__(self):
        self.broker_orders = _BrokerOrders()


async def _capture_original(engine, trade, snapshots):
    snapshots.append(
        {
            "position": dict(engine._positions.get(trade.symbol, {})),
            "quantity": trade.quantity,
            "price": trade.price,
            "pnl": trade.pnl,
        }
    )


def _filled_result(side="BUY", quantity=2.0, price=91.25):
    return {
        "broker_id": "alpaca",
        "status": "filled",
        "broker_order_id": f"order-{side.lower()}",
        "filled_quantity": quantity,
        "filled_price": price,
    }


def test_live_buy_replaces_optimistic_quote_position_before_publication(monkeypatch):
    engine = TradingEngine()
    engine._positions["ASTS"] = {"qty": 2.1, "avg_entry": 90.0, "high": 90.0}
    monkeypatch.setattr(deps, "db", _Db())
    snapshots = []

    async def fake_original(self, trade):
        return await _capture_original(self, trade, snapshots)

    monkeypatch.setattr(publication, "_original_record_trade", fake_original)
    trade = TradeRecord(
        symbol="ASTS",
        side="BUY",
        price=90.0,
        quantity=2.1,
        total_value=189.0,
        trading_mode="live",
        broker_results=[_filled_result("BUY", 2.0, 91.25)],
    )

    asyncio.run(publication._record_trade_with_position_truth(engine, trade))

    assert snapshots == [
        {
            "position": {"qty": 2.0, "avg_entry": 91.25, "high": 91.25},
            "quantity": 2.0,
            "price": 91.25,
            "pnl": 0.0,
        }
    ]
    assert engine._positions["ASTS"]["qty"] == 2.0
    assert deps.db.broker_orders.updated


def test_live_sell_closes_position_before_order_filled_publication(monkeypatch):
    engine = TradingEngine()
    engine._positions["ASTS"] = {"qty": 2.0, "avg_entry": 90.0, "high": 110.0}
    engine._trailing_highs["ASTS"] = 110.0
    monkeypatch.setattr(deps, "db", _Db())
    snapshots = []

    async def fake_original(self, trade):
        return await _capture_original(self, trade, snapshots)

    monkeypatch.setattr(publication, "_original_record_trade", fake_original)
    trade = TradeRecord(
        symbol="ASTS",
        side="SELL",
        price=110.0,
        quantity=2.0,
        entry_price=90.0,
        total_value=220.0,
        trading_mode="live",
        broker_results=[_filled_result("SELL", 2.0, 109.5)],
    )

    asyncio.run(publication._record_trade_with_position_truth(engine, trade))

    assert snapshots[0]["position"]["qty"] == 0.0
    assert snapshots[0]["quantity"] == 2.0
    assert snapshots[0]["price"] == 109.5
    assert snapshots[0]["pnl"] == 39.0
    assert "ASTS" not in engine._trailing_highs


def test_reconciliation_fill_updates_position_before_trade_callback(monkeypatch):
    engine = TradingEngine()
    engine._positions["ASTS"] = {"qty": 1.0, "avg_entry": 90.0, "high": 95.0}
    broker_orders = _BrokerOrders()

    class Db:
        def __init__(self):
            self.broker_orders = broker_orders
            self.tickers = SimpleNamespace(find_one=None)

    monkeypatch.setattr(deps, "db", Db())
    snapshots = []

    async def fake_record(trade):
        snapshots.append(dict(engine._positions["ASTS"]))

    async def fake_save():
        return None

    engine._record_trade = fake_record
    engine.save_state = fake_save
    order_doc = {
        "intent_key": "ASTS:BUY:LIMIT",
        "broker_id": "alpaca",
        "durable_order_id": "order-1",
        "broker_order_id": "order-1",
        "symbol": "ASTS",
        "side": "BUY",
        "order_type": "LIMIT",
        "applied_quantity": 1.0,
        "applied_notional": 90.0,
    }
    update = {
        "status": "canceled",
        "filled_quantity": 2.0,
        "filled_price": 92.0,
    }

    applied = asyncio.run(
        publication._apply_fill_delta_before_publication(engine, order_doc, update)
    )

    assert applied == 1.0
    assert snapshots[0]["qty"] == 2.0
    assert snapshots[0]["avg_entry"] == 92.0
    assert broker_orders.updated
