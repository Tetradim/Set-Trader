import asyncio
from types import SimpleNamespace

import deps
from trading.passive_range_paper_risk_patch import _arm_buy_with_paper_risk


class FakeCollection:
    def __init__(self):
        self.document = None

    async def update_one(self, query, update, upsert=False):
        self.document = dict(update.get("$set") or {})
        return SimpleNamespace(modified_count=1)


class FakeEngine:
    def is_paper_trading(self):
        return True

    async def pre_trade_check(self, symbol, side, quantity, price):
        return False, "daily drawdown limit reached"


def test_passive_paper_buy_is_blocked_by_pretrade_risk(monkeypatch):
    state_collection = FakeCollection()
    monkeypatch.setattr(
        deps,
        "db",
        SimpleNamespace(passive_range_state=state_collection),
    )

    state = {"symbol": "QSI", "phase": "IDLE"}
    ticker = {
        "symbol": "QSI",
        "broker_ids": [],
        "passive_fractional_shares": False,
    }

    asyncio.run(
        _arm_buy_with_paper_risk(
            FakeEngine(),
            ticker_doc=ticker,
            state=state,
            buy_target=0.955,
            effective_power=500,
        )
    )

    assert state["phase"] == "IDLE"
    assert state["last_risk_block_reason"] == "daily drawdown limit reached"
    assert state_collection.document["last_risk_block_reason"] == "daily drawdown limit reached"
