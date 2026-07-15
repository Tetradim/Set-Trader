import asyncio
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import deps  # noqa: E402
from trading_engine import TradingEngine  # noqa: E402


class _Cursor:
    def sort(self, *_args, **_kwargs):
        return self

    async def to_list(self, _limit):
        return []


class _BrokerOrders:
    def __init__(self):
        self.updates = []

    async def find_one(self, *_args, **_kwargs):
        return None

    async def update_one(self, query, update, upsert=False):
        self.updates.append((query, update, upsert))

    async def update_many(self, query, update):
        self.updates.append((query, update, False))

    def find(self, *_args, **_kwargs):
        return _Cursor()


class _Db:
    def __init__(self):
        self.broker_orders = _BrokerOrders()


class _Position:
    def __init__(self, symbol, quantity):
        self.symbol = symbol
        self.quantity = quantity


class _Adapter:
    def __init__(self, quantity=0):
        self.quantity = quantity

    async def get_positions(self):
        return [_Position("SPY", self.quantity)] if self.quantity else []

    async def get_open_orders(self):
        return []


class _BrokerManager:
    def __init__(self, holdings=None, partial=False):
        self.holdings = holdings or {}
        self.partial = partial
        self.calls = []

    def get_adapter(self, broker_id):
        return _Adapter(self.holdings.get(broker_id, 0))

    async def place_orders_for_ticker(self, **kwargs):
        self.calls.append(kwargs)
        broker_id = kwargs["broker_ids"][0]
        template = kwargs["order_template"]
        quantity = float(template["quantity"])
        filled = quantity / 2 if self.partial else quantity
        return [
            {
                "broker_id": broker_id,
                "status": "partially_filled" if self.partial else "filled",
                "broker_order_id": f"{broker_id}-order",
                "filled_quantity": filled,
                "filled_price": float(template["price"]),
            }
        ]


def _engine(monkeypatch, manager):
    monkeypatch.setattr(deps, "db", _Db())
    monkeypatch.setattr(deps, "broker_mgr", manager)
    engine = TradingEngine()
    engine.live_during_market_hours = True
    engine.simulate_24_7 = False

    async def allow(*_args, **_kwargs):
        return True, ""

    engine.pre_trade_check = allow
    return engine


def test_multi_broker_buy_is_split_by_allocation(monkeypatch):
    manager = _BrokerManager()
    engine = _engine(monkeypatch, manager)

    results = asyncio.run(
        engine._place_live_order_or_raise(
            sym="SPY",
            broker_ids=["alpha", "beta"],
            broker_allocs={"alpha": 60.0, "beta": 40.0},
            order_template={
                "symbol": "SPY",
                "side": "BUY",
                "order_type": "MARKET",
                "price": 10.0,
            },
            action_label="BUY",
        )
    )

    assert len(results) == 2
    assert manager.calls[0]["order_template"]["quantity"] == 6.0
    assert manager.calls[1]["order_template"]["quantity"] == 4.0
    assert engine._broker_results_filled_quantity(results) == 10.0
    assert engine._broker_results_weighted_fill_price(results) == 10.0


def test_multi_broker_sell_uses_each_brokers_actual_holdings(monkeypatch):
    manager = _BrokerManager({"alpha": 3.0, "beta": 7.0})
    engine = _engine(monkeypatch, manager)

    asyncio.run(
        engine._place_live_order_or_raise(
            sym="SPY",
            broker_ids=["alpha", "beta"],
            broker_allocs={"alpha": 30.0, "beta": 70.0},
            order_template={
                "symbol": "SPY",
                "side": "SELL",
                "order_type": "MARKET",
                "price": 10.0,
                "quantity": 5.0,
            },
            action_label="SELL",
        )
    )

    assert manager.calls[0]["order_template"]["quantity"] == 1.5
    assert manager.calls[1]["order_template"]["quantity"] == 3.5


def test_partial_fill_is_persisted_but_not_promoted_to_trade(monkeypatch):
    manager = _BrokerManager(partial=True)
    engine = _engine(monkeypatch, manager)

    with pytest.raises(RuntimeError, match="not fully filled"):
        asyncio.run(
            engine._place_live_order_or_raise(
                sym="SPY",
                broker_ids=["alpha"],
                broker_allocs={"alpha": 100.0},
                order_template={
                    "symbol": "SPY",
                    "side": "BUY",
                    "order_type": "MARKET",
                    "price": 10.0,
                },
                action_label="BUY",
            )
        )

    assert deps.db.broker_orders.updates
    assert engine._positions.get("SPY") is None


def test_filled_status_without_quantity_and_price_is_rejected(monkeypatch):
    class IncompleteManager(_BrokerManager):
        async def place_orders_for_ticker(self, **kwargs):
            self.calls.append(kwargs)
            return [
                {
                    "broker_id": kwargs["broker_ids"][0],
                    "status": "filled",
                    "broker_order_id": "order-1",
                }
            ]

    manager = IncompleteManager()
    engine = _engine(monkeypatch, manager)

    with pytest.raises(RuntimeError, match="not fully filled"):
        asyncio.run(
            engine._place_live_order_or_raise(
                sym="SPY",
                broker_ids=["alpha"],
                broker_allocs={"alpha": 100.0},
                order_template={
                    "symbol": "SPY",
                    "side": "BUY",
                    "order_type": "MARKET",
                    "price": 10.0,
                },
                action_label="BUY",
            )
        )
