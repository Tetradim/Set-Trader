import asyncio
import time
from types import SimpleNamespace

import pytest

from trading.edge_entry_policy import EdgeEntryPolicyError, validate_long_entry
from trading import edge_entry_profitability_patch as handoff
from trading import edge_live_entry_policy_patch as live
from trading.broker_execution import LiveOrderExecutionError


def _policy(**overrides):
    value = {
        "contract_version": "edge.entry_policy.v1",
        "reference_price": 100.0,
        "maximum_entry_price": 101.0,
        "expected_value_pct": 0.60,
        "estimated_cost_pct": 0.10,
        "maximum_execution_cost_pct": 0.25,
        "minimum_remaining_expected_value_pct": 0.15,
        "maximum_spread_pct": 0.20,
        "position_id": "edge-position:test",
        "card_id": "edge-card:test",
        "trigger_state": "triggered",
    }
    value.update(overrides)
    return value


def test_maximum_entry_price_is_a_hard_veto():
    with pytest.raises(EdgeEntryPolicyError) as raised:
        validate_long_entry(_policy(), observed_price=101.25)
    assert raised.value.reason == "maximum_entry_price_exceeded"
    assert raised.value.execution_code == "ENTRY_REJECTED_MAXIMUM_ENTRY_PRICE"


def test_wide_spread_defers_entry_before_broker_submission():
    with pytest.raises(EdgeEntryPolicyError) as raised:
        validate_long_entry(_policy(), observed_price=100.0, bid=99.80, ask=100.20)
    assert raised.value.reason == "entry_deferred_poor_liquidity"
    assert raised.value.execution_code == "ENTRY_DEFERRED_POOR_LIQUIDITY"
    assert raised.value.status == "deferred"


def test_execution_cost_limit_preserves_remaining_edge():
    policy = _policy(maximum_spread_pct=1.0, maximum_execution_cost_pct=0.15)
    with pytest.raises(EdgeEntryPolicyError) as raised:
        validate_long_entry(
            policy,
            observed_price=100.0,
            bid=99.90,
            ask=100.10,
            slippage_buffer_bps=5.0,
        )
    assert raised.value.reason == "entry_rejected_slippage_limit"
    assert raised.value.execution_code == "ENTRY_REJECTED_SLIPPAGE_LIMIT"


class _TickerCollection:
    def __init__(self):
        self.updates = []

    async def update_one(self, query, update):
        self.updates.append((query, update))


class _EdgeModule:
    def __init__(self, price):
        self.price = price
        self.deps = SimpleNamespace(
            engine=SimpleNamespace(),
            db=SimpleNamespace(tickers=_TickerCollection()),
        )

    async def _handoff_price(self, symbol, body):
        return self.price

    def _handoff_response(self, body, **kwargs):
        return {"symbol": body.symbol, "action": body.action.value, **kwargs}


def _body(maximum_entry_price=101.0, **metadata_overrides):
    card = {
        "card_id": "edge-card:test",
        "position_id": "edge-position:test",
        "entry_price": 100.0,
        "maximum_entry_price": maximum_entry_price,
        "expected_value_pct": 0.60,
        "metadata": {
            "estimated_cost_pct": 0.10,
            "maximum_execution_cost_pct": 0.25,
        },
    }
    metadata = {
        "price": 100.0,
        "trade_card": card,
        "position_id": card["position_id"],
        "execution_intent": {
            "contract_version": "edge.execution_intent.v2",
            "intent_id": "edge:AAPL:buy:test",
            "entry_policy": _policy(maximum_entry_price=maximum_entry_price),
        },
        **metadata_overrides,
    }
    return SimpleNamespace(
        symbol="AAPL",
        action=SimpleNamespace(value="buy"),
        idempotency_key="edge:AAPL:buy:test",
        metadata=metadata,
    )


def test_handoff_rejects_before_runtime_policy_or_ticker_audit_is_created():
    edge = _EdgeModule(price=101.50)
    response = asyncio.run(handoff._prepare_policy(edge, _body()))
    assert response["accepted"] is False
    assert response["reason"] == "maximum_entry_price_exceeded"
    assert response["execution_code"] == "ENTRY_REJECTED_MAXIMUM_ENTRY_PRICE"
    assert getattr(edge.deps.engine, "_edge_entry_policies", {}) == {}
    assert edge.deps.db.tickers.updates == []


def test_handoff_arms_position_scoped_runtime_policy():
    edge = _EdgeModule(price=100.05)
    response = asyncio.run(handoff._prepare_policy(edge, _body()))
    assert response is None
    runtime = edge.deps.engine._edge_entry_policies["AAPL"]
    assert runtime["policy"]["position_id"] == "edge-position:test"
    assert runtime["preflight"]["accepted"] is True


def test_fresh_broker_quote_revalidates_and_records_cost(monkeypatch):
    monkeypatch.setenv("PULSE_MAX_LIVE_SPREAD_PCT", "2")
    runtime = {"policy": _policy(maximum_spread_pct=0.30), "execution_checks": [], "rejection": None}
    token = live._CONTEXT.set({"runtime": runtime, "symbol": "AAPL"})
    try:
        quote = live._validated_quote_with_edge_policy(
            {
                "broker_id": "alpaca",
                "symbol": "AAPL",
                "bid": 99.95,
                "ask": 100.05,
                "received_at_epoch": time.time(),
            }
        )
    finally:
        live._CONTEXT.reset(token)
    assert quote["edge_execution_quality"]["estimated_execution_cost_pct"] > 0
    assert runtime["execution_checks"][0]["broker_id"] == "alpaca"


def test_fresh_broker_quote_returns_structured_live_veto(monkeypatch):
    monkeypatch.setenv("PULSE_MAX_LIVE_SPREAD_PCT", "2")
    runtime = {"policy": _policy(maximum_entry_price=100.02, maximum_spread_pct=1.0), "execution_checks": [], "rejection": None}
    token = live._CONTEXT.set({"runtime": runtime, "symbol": "AAPL"})
    try:
        with pytest.raises(LiveOrderExecutionError) as raised:
            live._validated_quote_with_edge_policy(
                {
                    "broker_id": "alpaca",
                    "symbol": "AAPL",
                    "bid": 100.00,
                    "ask": 100.05,
                    "received_at_epoch": time.time(),
                }
            )
    finally:
        live._CONTEXT.reset(token)
    assert getattr(raised.value, "reason") == "maximum_entry_price_exceeded"
    assert runtime["rejection"]["execution_code"] == "ENTRY_REJECTED_MAXIMUM_ENTRY_PRICE"
