import asyncio
from types import SimpleNamespace

import deps
from trading.passive_range_risk_patch import _evaluate_passive_range_with_stop


class FakeCollection:
    def __init__(self, document=None):
        self.document = document
        self.inserted = []

    async def find_one(self, query, projection=None):
        return dict(self.document) if self.document else None

    async def update_one(self, query, update, upsert=False):
        self.document = dict(update.get("$set") or {})
        return SimpleNamespace(modified_count=1)

    async def insert_one(self, document):
        self.inserted.append(dict(document))
        return SimpleNamespace(inserted_id="cycle")


class FakePriceService:
    async def get_price(self, symbol):
        return 0.90


class FakeEngine:
    def __init__(self):
        self._prices = {}
        self._positions = {"QSI": {"qty": 523, "avg_entry": 0.955, "high": 0.955}}
        self._last_exit_ts = {}
        self.trades = []
        self.profits = []

    def is_paper_trading(self):
        return True

    def _is_ticker_market_open(self, ticker_doc):
        return True

    async def _record_trade(self, trade):
        self.trades.append(trade)

    async def _update_profit(self, symbol, pnl, compound):
        self.profits.append((symbol, pnl, compound))


def test_passive_range_stop_closes_position_and_cycle(monkeypatch):
    state = {
        "symbol": "QSI",
        "phase": "SELL_WORKING",
        "cycle_id": "cycle-1",
        "cycle_started_at": "2026-07-18T14:00:00+00:00",
        "buy_filled_at": "2026-07-18T14:01:00+00:00",
        "buy_target": 0.955,
        "sell_target": 0.966,
        "position_qty": 523,
        "entry_price": 0.955,
        "sell_order": {"broker_order_id": "paper-sell"},
    }
    state_collection = FakeCollection(state)
    cycle_collection = FakeCollection()
    monkeypatch.setattr(
        deps,
        "db",
        SimpleNamespace(
            passive_range_state=state_collection,
            passive_range_cycles=cycle_collection,
        ),
    )
    monkeypatch.setattr(deps, "price_service", FakePriceService())
    monkeypatch.setattr(deps, "broker_mgr", None)

    engine = FakeEngine()
    ticker = {
        "symbol": "QSI",
        "enabled": True,
        "broker_ids": [],
        "broker_allocations": {},
        "base_power": 500,
        "stop_percent": False,
        "stop_offset": 0.92,
        "price_tick_size": 0.0001,
        "compound_profits": True,
    }

    asyncio.run(_evaluate_passive_range_with_stop(engine, ticker))

    assert engine.trades[0].side == "STOP"
    assert engine.trades[0].price == 0.90
    assert engine._positions["QSI"]["qty"] == 0
    assert state_collection.document["phase"] == "COOLDOWN"
    assert cycle_collection.inserted[0]["exit_reason"] == "stop"
