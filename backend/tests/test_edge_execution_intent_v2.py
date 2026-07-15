import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from trading.edge_handoff_contract_patch import _apply_execution_intent


class _TickerCollection:
    def __init__(self, ticker=None):
        self.ticker = ticker
        self.updates = []

    async def find_one(self, query, projection=None):
        if self.ticker and self.ticker.get("symbol") == query.get("symbol"):
            return dict(self.ticker)
        return None

    async def update_one(self, query, update):
        self.updates.append((query, update))
        if self.ticker is None:
            self.ticker = {"symbol": query["symbol"]}
        self.ticker.update(update.get("$set", {}))


class _Db:
    def __init__(self, ticker=None):
        self.tickers = _TickerCollection(ticker)


class _EdgeModule:
    def __init__(self, ticker=None):
        self.deps = SimpleNamespace(db=_Db(ticker))
        self.created = []

    def _handoff_response(self, body, **kwargs):
        return {"symbol": body.symbol, **kwargs}

    async def _create_ticker_from_edge_buy(self, symbol):
        ticker = {
            "symbol": symbol,
            "base_power": 100.0,
            "compound_profits": False,
            "broker_ids": ["alpaca", "tradier"],
            "broker_allocations": {"alpaca": 75.0, "tradier": 25.0},
        }
        self.deps.db.tickers.ticker = ticker
        self.created.append(symbol)
        return dict(ticker)


def _body(**intent_overrides):
    intent = {
        "contract_version": "edge.execution_intent.v2",
        "intent_id": "edge:ASTS:buy:abc",
        "quantity_policy": {
            "type": "target_notional",
            "target_notional": 200.0,
        },
        "max_notional": 250.0,
        "expires_at": 2_000_000_000.0,
    }
    intent.update(intent_overrides)
    return SimpleNamespace(
        symbol="ASTS",
        action=SimpleNamespace(value="buy"),
        idempotency_key="edge:ASTS:buy:abc",
        metadata={"execution_intent": intent},
    )


def test_expired_intent_is_rejected_before_ticker_mutation():
    edge = _EdgeModule()
    with patch("trading.edge_handoff_contract_patch.time.time", return_value=2_000_000_001.0):
        response = asyncio.run(_apply_execution_intent(edge, _body()))
    assert response["accepted"] is False
    assert response["reason"] == "execution_intent_expired"
    assert edge.deps.db.tickers.updates == []


def test_target_above_maximum_is_rejected():
    edge = _EdgeModule()
    body = _body(
        quantity_policy={"type": "target_notional", "target_notional": 300.0},
        max_notional=250.0,
    )
    with patch("trading.edge_handoff_contract_patch.time.time", return_value=1_900_000_000.0):
        response = asyncio.run(_apply_execution_intent(edge, body))
    assert response["accepted"] is False
    assert response["reason"] == "target_notional_exceeds_maximum"


def test_buy_intent_creates_compounding_ticker_and_scales_broker_allocations():
    edge = _EdgeModule()
    with patch("trading.edge_handoff_contract_patch.time.time", return_value=1_900_000_000.0):
        response = asyncio.run(_apply_execution_intent(edge, _body()))
    assert response is None
    assert edge.created == ["ASTS"]
    ticker = edge.deps.db.tickers.ticker
    assert ticker["base_power"] == 200.0
    assert ticker["compound_profits"] is True
    assert ticker["edge_execution_intent_id"] == "edge:ASTS:buy:abc"
    assert ticker["broker_allocations"] == {"alpaca": 150.0, "tradier": 50.0}


def test_existing_strategy_capital_is_preserved_when_target_notional_is_omitted():
    edge = _EdgeModule(
        {
            "symbol": "ASTS",
            "base_power": 143.75,
            "compound_profits": True,
            "broker_ids": ["alpaca"],
            "broker_allocations": {"alpaca": 143.75},
        }
    )
    body = _body(
        quantity_policy={"type": "pulse_strategy_capital", "target_notional": None},
        max_notional=None,
    )
    with patch("trading.edge_handoff_contract_patch.time.time", return_value=1_900_000_000.0):
        response = asyncio.run(_apply_execution_intent(edge, body))
    assert response is None
    ticker = edge.deps.db.tickers.ticker
    assert ticker["base_power"] == 143.75
    assert ticker["broker_allocations"] == {"alpaca": 143.75}
