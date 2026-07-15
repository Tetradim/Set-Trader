import asyncio
from types import SimpleNamespace

import pytest

from trading.broker_execution import BrokerExecutionMixin, LiveOrderExecutionError
import trading.live_execution_quality_patch as quality


def test_runtime_installs_execution_quality_wrapper():
    assert BrokerExecutionMixin._place_live_order_or_raise.__name__ == "_place_with_executable_quotes"
    assert BrokerExecutionMixin.reconcile_live_orders.__name__ == "_reconcile_with_expiry"


def test_buy_plans_are_normalized_to_broker_quantity_increment(monkeypatch):
    async def plans(*_args, **_kwargs):
        return [
            {"broker_id": "tradier", "quantity": 1.9, "allocation": 190},
            {"broker_id": "alpaca", "quantity": 1.12345678, "allocation": 112},
        ]

    monkeypatch.setattr(quality, "_original_build_plans", plans)
    result = asyncio.run(
        quality._build_plans_with_broker_increments(
            SimpleNamespace(),
            symbol="ASTS",
            side="BUY",
            quantity=3.02345678,
            price=100,
            broker_ids=["tradier", "alpaca"],
            allocations={"tradier": 190, "alpaca": 112},
        )
    )
    assert result[0]["quantity"] == 1.0
    assert result[0]["fractional_supported"] is False
    assert result[1]["quantity"] == 1.123456
    assert result[1]["fractional_supported"] is True


def test_fractional_sell_is_blocked_when_broker_cannot_represent_it(monkeypatch):
    async def plans(*_args, **_kwargs):
        return [{"broker_id": "tradier", "quantity": 1.5, "allocation": 150}]

    monkeypatch.setattr(quality, "_original_build_plans", plans)
    with pytest.raises(LiveOrderExecutionError, match="fractional remainder"):
        asyncio.run(
            quality._build_plans_with_broker_increments(
                SimpleNamespace(),
                symbol="ASTS",
                side="SELL",
                quantity=1.5,
                price=100,
                broker_ids=["tradier"],
                allocations={"tradier": 150},
            )
        )


def test_quote_validation_rejects_wide_spread(monkeypatch):
    monkeypatch.setenv("PULSE_MAX_LIVE_SPREAD_PCT", "1")
    with pytest.raises(LiveOrderExecutionError, match="exceeds live maximum"):
        quality._validated_quote(
            {
                "broker_id": "alpaca",
                "symbol": "ASTS",
                "bid": 9.0,
                "ask": 10.0,
                "received_at_epoch": quality.time.time(),
            }
        )


def test_buy_sizing_uses_worst_executable_ask_across_brokers(monkeypatch):
    class Adapter:
        def __init__(self, broker_id, bid, ask):
            self.broker_id = broker_id
            self.bid = bid
            self.ask = ask

        async def get_quote_snapshot(self, symbol):
            return {
                "broker_id": self.broker_id,
                "symbol": symbol,
                "bid": self.bid,
                "ask": self.ask,
                "received_at_epoch": quality.time.time(),
            }

    adapters = {
        "alpaca": Adapter("alpaca", 9.95, 10.00),
        "tradier": Adapter("tradier", 9.94, 10.02),
    }
    captured = {}

    async def original(_self, **kwargs):
        captured.update(kwargs)
        return [{"broker_id": "alpaca", "status": "filled"}]

    fake_self = SimpleNamespace(
        _should_place_broker_orders=lambda ids: True,
        _live_broker_ids_with_allocations=lambda ids, allocs: ids,
    )
    monkeypatch.setattr(quality, "_original_place", original)
    monkeypatch.setattr(
        quality.deps,
        "broker_mgr",
        SimpleNamespace(get_adapter=lambda broker_id: adapters[broker_id]),
    )
    monkeypatch.setenv("PULSE_MAX_LIVE_SPREAD_PCT", "2")

    asyncio.run(
        quality._place_with_executable_quotes(
            fake_self,
            sym="ASTS",
            broker_ids=["alpaca", "tradier"],
            broker_allocs={"alpaca": 50, "tradier": 50},
            order_template={"side": "BUY", "order_type": "LIMIT", "limit_price": 10.0},
            action_label="BUY",
        )
    )
    assert captured["order_template"]["price"] == 10.02
    assert len(captured["order_template"]["execution_quotes"]) == 2


class _Collection:
    def __init__(self):
        self.updates = []

    async def update_one(self, query, update, upsert=False):
        self.updates.append((query, update, upsert))
        return SimpleNamespace(matched_count=1, modified_count=1)


def test_parent_order_records_accept_partial_policy(monkeypatch):
    parents = _Collection()
    children = _Collection()

    async def original(*_args, **_kwargs):
        return None

    fake_self = SimpleNamespace(
        _BROKER_PENDING_STATUSES={"submitted", "pending"},
        _BROKER_PARTIAL_STATUSES={"partially_filled"},
        _broker_result_filled_quantity=lambda result: float(result.get("filled_quantity") or 0),
    )
    monkeypatch.setattr(quality, "_original_persist_results", original)
    monkeypatch.setattr(
        quality.deps,
        "db",
        SimpleNamespace(parent_orders=parents, broker_orders=children),
    )

    asyncio.run(
        quality._persist_results_with_parent(
            fake_self,
            intent_key="ASTS:BUY:LIMIT",
            symbol="ASTS",
            side="BUY",
            order_type="LIMIT",
            reference_price=10.0,
            plans=[
                {"broker_id": "alpaca", "quantity": 5},
                {"broker_id": "tradier", "quantity": 5},
            ],
            results=[
                {
                    "broker_id": "alpaca",
                    "broker_order_id": "a-1",
                    "status": "filled",
                    "filled_quantity": 5,
                },
                {
                    "broker_id": "tradier",
                    "broker_order_id": "t-1",
                    "status": "rejected",
                    "filled_quantity": 0,
                },
            ],
        )
    )
    parent_update = parents.updates[0][1]["$set"]
    assert parent_update["policy"] == "accept_partial"
    assert parent_update["target_quantity"] == 10
    assert parent_update["filled_quantity"] == 5
    assert parent_update["remaining_quantity"] == 5
    assert parent_update["state"] == "partial_complete"
