import asyncio
from types import SimpleNamespace

from trading.broker_execution import BrokerExecutionMixin
import trading.live_terminal_fill_patch as terminal


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *_args):
        return self

    async def to_list(self, _limit):
        return list(self.docs)


class _Collection:
    def __init__(self, docs):
        self.docs = docs
        self.query = None

    def find(self, query, projection=None):
        self.query = query
        return _Cursor(self.docs)


def test_runtime_installs_terminal_fill_reconciler():
    assert BrokerExecutionMixin.reconcile_live_orders.__name__ == "_reconcile_including_terminal_fills"


def test_cancelled_order_final_partial_fill_is_applied(monkeypatch):
    docs = [
        {
            "symbol": "ASTS",
            "status": "cancelled",
            "broker_id": "alpaca",
            "broker_order_id": "order-1",
            "filled_quantity": 2,
            "avg_fill_price": 10.25,
            "applied_quantity": 1,
        }
    ]
    collection = _Collection(docs)
    calls = []

    async def apply(_self, doc, update):
        calls.append((doc, update))
        return 1.0

    monkeypatch.setattr(terminal.deps, "db", SimpleNamespace(broker_orders=collection))
    monkeypatch.setattr(terminal.reconciliation, "_apply_fill_delta", apply)

    applied = asyncio.run(
        terminal._apply_terminal_fill_deltas(SimpleNamespace(), "ASTS")
    )
    assert applied == 1.0
    assert calls[0][1]["status"] == "cancelled"
    assert calls[0][1]["filled_quantity"] == 2
    assert calls[0][1]["filled_price"] == 10.25
    assert collection.query["symbol"] == "ASTS"
