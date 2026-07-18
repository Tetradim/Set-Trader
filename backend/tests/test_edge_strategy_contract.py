import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from trading import edge_strategy_contract_patch as contract


class FakeCollection:
    def __init__(self, ticker=None):
        self.ticker = ticker or {}
        self.updates = []

    async def find_one(self, *_args, **_kwargs):
        return dict(self.ticker) if self.ticker else None

    async def update_one(self, query, update):
        self.updates.append((query, update))
        if "$set" in update:
            self.ticker.update(update["$set"])
        if "$unset" in update:
            for key in update["$unset"]:
                self.ticker.pop(key, None)
        return SimpleNamespace(modified_count=1)


class FakeEdgeModule:
    def __init__(self, ticker=None, position=None):
        self.collection = FakeCollection(ticker)
        self.deps = SimpleNamespace(db=SimpleNamespace(tickers=self.collection))
        self.position = position or {}

    def _current_position(self, _symbol):
        return dict(self.position)

    @staticmethod
    def _handoff_response(body, *, accepted, status, reason, message=""):
        return {
            "accepted": accepted,
            "sent": accepted,
            "status": status,
            "reason": reason,
            "message": message,
            "symbol": body.symbol,
            "action": body.action.value,
        }


def _card(**overrides):
    card = {
        "card_id": "edge-card:pulse",
        "strategy_id": "edge-strategy:pulse",
        "thesis_id": "edge-thesis:pulse",
        "position_id": "edge-position:pulse",
        "symbol": "AAPL",
        "target_bot": "sentinel-pulse",
        "state": "armed",
        "direction": "long",
        "maximum_entry_price": 205.0,
        "target_notional": 1000.0,
        "risk_budget_pct": 0.5,
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
    }
    card.update(overrides)
    return card


def _body(action="buy", metadata=None):
    return SimpleNamespace(symbol="AAPL", action=SimpleNamespace(value=action), metadata=metadata or {})


def test_new_exposure_requires_edge_trade_card(monkeypatch):
    monkeypatch.setenv("PULSE_REQUIRE_EDGE_TRADE_CARD", "true")
    edge = FakeEdgeModule()

    rejection = asyncio.run(contract._validate(edge, _body("buy", {"price": 200.0})))

    assert rejection["reason"] == "edge_trade_card_required"


def test_authorized_buy_persists_position_owner():
    edge = FakeEdgeModule(ticker={"symbol": "AAPL"})
    card = _card()
    body = _body("buy", {"price": 200.0, "trade_card": card, "position_id": card["position_id"]})

    assert asyncio.run(contract._validate(edge, body)) is None
    asyncio.run(contract._persist_after(edge, body, {"accepted": True, "sent": True, "status": "accepted"}))

    assert edge.collection.ticker["edge_position_id"] == "edge-position:pulse"
    assert edge.collection.ticker["edge_card_id"] == "edge-card:pulse"


def test_supervision_rejects_different_position_owner():
    edge = FakeEdgeModule(
        ticker={"symbol": "AAPL", "edge_position_id": "edge-position:other"},
        position={"qty": 10},
    )
    card = _card(state="active")
    body = _body(
        "tighten_stop",
        {
            "trade_card": card,
            "position_id": card["position_id"],
            "supervisory_directive": "set_stop",
            "strategy_lifecycle": {"stop_owner": {"position_id": card["position_id"]}},
        },
    )

    rejection = asyncio.run(contract._validate(edge, body))

    assert rejection["reason"] == "edge_position_owner_mismatch"


def test_full_exit_invalidates_position_scoped_stop():
    card = _card(state="active")
    edge = FakeEdgeModule(
        ticker={
            "symbol": "AAPL",
            "edge_position_id": card["position_id"],
            "edge_stop_position_id": card["position_id"],
            "edge_stop_price": 190.0,
            "stop_offset": 190.0,
            "stop_percent": False,
        },
        position={"qty": 0},
    )
    body = _body(
        "sell",
        {
            "trade_card": card,
            "position_id": card["position_id"],
            "invalidate_position_scoped_stop": True,
        },
    )

    asyncio.run(contract._persist_after(edge, body, {"accepted": True, "sent": True, "status": "accepted"}))

    assert "edge_position_id" not in edge.collection.ticker
    assert "edge_stop_position_id" not in edge.collection.ticker
    assert edge.collection.ticker["stop_offset"] == 0.0
    assert edge.collection.ticker["stop_percent"] is True
