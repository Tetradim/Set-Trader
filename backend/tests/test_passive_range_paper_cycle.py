import asyncio
from types import SimpleNamespace

import deps
from trading.passive_range_patch import _evaluate_passive_range


class FakeCollection:
    def __init__(self):
        self.document = None
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
    def __init__(self, prices):
        self.prices = iter(prices)

    async def get_price(self, symbol):
        return next(self.prices)

    async def get_avg_price(self, symbol, days):
        return 1.0


class FakeEngine:
    def __init__(self):
        self._prices = {}
        self._positions = {}
        self._last_exit_ts = {}
        self.trades = []
        self.profit_updates = []

    def is_paper_trading(self):
        return True

    def _is_ticker_market_open(self, ticker_doc):
        return True

    async def _record_trade(self, trade):
        self.trades.append(trade)

    async def _update_profit(self, symbol, pnl, compound):
        self.profit_updates.append((symbol, pnl, compound))


def test_paper_cycle_rests_buy_then_sell_and_records_cycle(monkeypatch):
    state_collection = FakeCollection()
    cycle_collection = FakeCollection()
    monkeypatch.setattr(
        deps,
        "db",
        SimpleNamespace(
            passive_range_state=state_collection,
            passive_range_cycles=cycle_collection,
        ),
    )
    monkeypatch.setattr(deps, "price_service", FakePriceService([0.95, 0.97]))
    monkeypatch.setattr(deps, "broker_mgr", None)

    engine = FakeEngine()
    ticker = {
        "symbol": "QSI",
        "enabled": True,
        "market": "US",
        "base_power": 500,
        "buy_percent": False,
        "buy_offset": 0.955,
        "sell_percent": False,
        "sell_offset": 0.966,
        "price_tick_size": 0.0001,
        "passive_range_enabled": True,
        "passive_paper_min_touches": 1,
        "passive_fractional_shares": False,
        "compound_profits": True,
        "broker_ids": [],
        "broker_allocations": {},
    }

    asyncio.run(_evaluate_passive_range(engine, ticker))

    assert state_collection.document["phase"] == "SELL_WORKING"
    assert engine._positions["QSI"]["qty"] == 523
    assert engine.trades[0].side == "BUY"
    assert engine.trades[0].price == 0.955

    asyncio.run(_evaluate_passive_range(engine, ticker))

    assert state_collection.document["phase"] == "COOLDOWN"
    assert engine._positions["QSI"]["qty"] == 0
    assert [trade.side for trade in engine.trades] == ["BUY", "SELL"]
    assert engine.trades[1].price == 0.966
    assert engine.profit_updates == [("QSI", 5.75, True)]
    assert cycle_collection.inserted[0]["gross_pnl"] == 5.753
    assert cycle_collection.inserted[0]["exit_reason"] == "sell_target"
