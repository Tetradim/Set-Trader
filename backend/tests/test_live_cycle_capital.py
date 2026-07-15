import asyncio
from types import SimpleNamespace

import trading.live_cycle_capital_patch as cycle
from trading.trade_accounting import TradeAccountingMixin


class _Collection:
    def __init__(self, document=None):
        self.document = dict(document or {})
        self.updates = []

    async def find_one(self, query, projection=None):
        return dict(self.document) if self.document else None

    async def update_one(self, query, update, upsert=False):
        self.updates.append((query, update, upsert))
        for key, value in update.get("$set", {}).items():
            self.document[key] = value
        for key, value in update.get("$inc", {}).items():
            self.document[key] = self.document.get(key, 0) + value
        return SimpleNamespace(matched_count=1, modified_count=1)

    def find(self, *args, **kwargs):
        return SimpleNamespace(to_list=lambda _limit: _async_value([]))


async def _async_value(value):
    return value


class _WS:
    def __init__(self):
        self.messages = []

    async def broadcast(self, message):
        self.messages.append(message)


def _deps(ticker):
    return SimpleNamespace(
        tickers=_Collection(ticker),
        trades=_Collection(),
        strategy_cycles=_Collection(),
        broker_orders=_Collection(),
    )


def test_runtime_installs_net_cycle_capital_accounting():
    assert TradeAccountingMixin._update_profit.__name__ == "_update_profit_with_live_cycle_capital"


def test_positive_cycle_compounds_net_of_broker_fees(monkeypatch):
    db = _deps(
        {
            "symbol": "ASTS",
            "base_power": 100.0,
            "broker_ids": [],
            "broker_allocations": {},
            "strategy": "range",
        }
    )
    calls = []

    async def prior(_self, symbol, pnl, compound=False):
        calls.append((symbol, pnl, compound))

    monkeypatch.setattr(cycle, "_current_update_profit", prior)
    monkeypatch.setattr(cycle.deps, "db", db)
    monkeypatch.setattr(cycle.deps, "ws_manager", _WS())

    engine = SimpleNamespace(
        _last_broker_truth_trade=SimpleNamespace(
            id="trade-1",
            pnl=10.0,
            broker_results=[{"commission": 1.25, "regulatory_fee": 0.75}],
        )
    )
    asyncio.run(
        cycle._update_profit_with_live_cycle_capital(
            engine,
            "ASTS",
            10.0,
            True,
        )
    )

    assert calls == [("ASTS", 8.0, False)]
    assert db.tickers.document["base_power"] == 108.0
    assert db.tickers.document["last_cycle_gross_pnl"] == 10.0
    assert db.tickers.document["last_cycle_fees"] == 2.0
    assert db.tickers.document["last_cycle_net_pnl"] == 8.0
    assert db.strategy_cycles.document["cycle_capital"] == 108.0
    assert db.strategy_cycles.document["cycle_number"] == 1


def test_loss_reduces_next_cycle_capital(monkeypatch):
    db = _deps(
        {
            "symbol": "ASTS",
            "base_power": 100.0,
            "broker_ids": [],
            "broker_allocations": {},
        }
    )

    async def prior(*_args, **_kwargs):
        return None

    monkeypatch.setattr(cycle, "_current_update_profit", prior)
    monkeypatch.setattr(cycle.deps, "db", db)
    monkeypatch.setattr(cycle.deps, "ws_manager", _WS())

    engine = SimpleNamespace(
        _last_broker_truth_trade=SimpleNamespace(
            id="trade-loss",
            pnl=-5.0,
            broker_results=[{"total_fees": 1.0}],
        )
    )
    asyncio.run(
        cycle._update_profit_with_live_cycle_capital(
            engine,
            "ASTS",
            -5.0,
            True,
        )
    )
    assert db.tickers.document["base_power"] == 94.0
    assert db.tickers.document["last_cycle_net_pnl"] == -6.0


def test_profit_waits_when_live_broker_capacity_is_unavailable(monkeypatch):
    db = _deps(
        {
            "symbol": "ASTS",
            "base_power": 100.0,
            "broker_ids": ["alpaca"],
            "broker_allocations": {"alpaca": 100.0},
        }
    )

    async def prior(*_args, **_kwargs):
        return None

    monkeypatch.setattr(cycle, "_current_update_profit", prior)
    monkeypatch.setattr(cycle.deps, "db", db)
    monkeypatch.setattr(cycle.deps, "ws_manager", _WS())
    monkeypatch.setattr(
        cycle.deps,
        "broker_mgr",
        SimpleNamespace(get_adapter=lambda _broker_id: None),
    )

    engine = SimpleNamespace(
        _last_broker_truth_trade=SimpleNamespace(
            id="trade-profit",
            pnl=10.0,
            broker_results=[],
        )
    )
    asyncio.run(
        cycle._update_profit_with_live_cycle_capital(
            engine,
            "ASTS",
            10.0,
            True,
        )
    )
    assert db.tickers.document["base_power"] == 100.0
    assert db.tickers.document["last_cycle_state"] == "awaiting_broker_capacity"
