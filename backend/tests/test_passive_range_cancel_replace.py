import asyncio
from types import SimpleNamespace

import deps
from trading.passive_range_controls_patch import (
    _buy_config_key,
    _evaluate_with_cancel_replace,
)


class FakeCollection:
    def __init__(self, document=None):
        self.document = document

    async def find_one(self, query, projection=None):
        return dict(self.document) if self.document else None

    async def update_one(self, query, update, upsert=False):
        self.document = dict(update.get("$set") or {})
        return SimpleNamespace(modified_count=1)


class FakePriceService:
    async def get_price(self, symbol):
        return 0.96

    async def get_avg_price(self, symbol, days):
        return 0.96


class FakeEngine:
    def __init__(self):
        self._prices = {}
        self._positions = {}
        self._last_exit_ts = {}

    def is_paper_trading(self):
        return True

    def _is_ticker_market_open(self, ticker_doc):
        return True

    async def _record_trade(self, trade):
        raise AssertionError("replacement should not create a fill")

    async def _update_profit(self, symbol, pnl, compound):
        raise AssertionError("replacement should not update profit")


def test_changed_buy_configuration_replaces_working_paper_order(monkeypatch):
    old_ticker = {
        "symbol": "QSI",
        "enabled": True,
        "base_power": 500,
        "buy_percent": False,
        "buy_offset": 0.955,
        "sell_percent": False,
        "sell_offset": 0.966,
        "price_tick_size": 0.0001,
        "passive_fractional_shares": False,
        "broker_ids": [],
        "broker_allocations": {},
    }
    state_collection = FakeCollection(
        {
            "symbol": "QSI",
            "phase": "BUY_WORKING",
            "cycle_id": "old-cycle",
            "cycle_started_at": "2026-07-18T14:00:00+00:00",
            "position_qty": 0.0,
            "entry_price": 0.0,
            "buy_config_key": _buy_config_key(old_ticker),
            "buy_order": {
                "broker_id": "paper",
                "broker_order_id": "paper-old",
                "status": "working",
                "side": "BUY",
                "limit_price": 0.955,
                "requested_quantity": 523,
                "submitted_at": "2026-07-18T14:00:00+00:00",
            },
        }
    )
    monkeypatch.setattr(
        deps,
        "db",
        SimpleNamespace(passive_range_state=state_collection),
    )
    monkeypatch.setattr(deps, "price_service", FakePriceService())
    monkeypatch.setattr(deps, "broker_mgr", None)

    new_ticker = {
        **old_ticker,
        "buy_offset": 0.954,
        "passive_order_ttl_seconds": 300,
        "passive_paper_min_touches": 2,
    }
    engine = FakeEngine()

    asyncio.run(_evaluate_with_cancel_replace(engine, new_ticker))

    assert state_collection.document["phase"] == "BUY_WORKING"
    assert state_collection.document["buy_order"]["limit_price"] == 0.954
    assert state_collection.document["buy_order"]["broker_order_id"] != "paper-old"
    assert state_collection.document["replace_reason"] == "buy_configuration_changed"
    assert state_collection.document["buy_config_key"] == _buy_config_key(new_ticker)
