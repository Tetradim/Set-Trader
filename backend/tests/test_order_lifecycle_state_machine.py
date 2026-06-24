import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from trading.order_state_machine import (  # noqa: E402
    OrderLifecycleError,
    transition_order_state,
)


def _accepted_order(**overrides):
    order = {
        "order_id": "intent-1",
        "status": "accepted",
        "symbol": "SPY",
        "side": "BUY",
        "quantity": 10,
        "filled_quantity": 0,
    }
    order.update(overrides)
    return order


def test_order_lifecycle_progresses_from_accepted_to_filled_with_broker_evidence():
    order = _accepted_order()

    submitted = transition_order_state(
        order,
        {"status": "submitted", "broker_order_id": "broker-123"},
    )
    partially_filled = transition_order_state(
        submitted,
        {
            "status": "partially-filled",
            "broker_order_id": "broker-123",
            "filled_quantity": 4,
            "avg_fill_price": 50.25,
        },
    )
    filled = transition_order_state(
        partially_filled,
        {
            "status": "filled",
            "broker_order_id": "broker-123",
            "filled_quantity": 10,
            "avg_fill_price": 50.40,
        },
    )

    assert submitted["status"] == "submitted"
    assert partially_filled["status"] == "partially_filled"
    assert partially_filled["filled_quantity"] == 4
    assert filled["status"] == "filled"
    assert filled["broker_order_id"] == "broker-123"
    assert filled["filled_quantity"] == 10
    assert filled["avg_fill_price"] == 50.40


@pytest.mark.parametrize(
    ("broker_update", "expected_status"),
    [
        (
            {
                "status": "canceled",
                "broker_order_id": "broker-123",
                "reject_reason": "operator canceled before fill",
            },
            "canceled",
        ),
        (
            {
                "status": "rejected",
                "reject_reason": "risk limit exceeded",
            },
            "rejected",
        ),
        (
            {
                "status": "stale",
                "broker_order_id": "broker-123",
                "reject_reason": "broker status was not refreshed before timeout",
            },
            "stale",
        ),
    ],
)
def test_order_lifecycle_handles_canceled_rejected_and_stale_paths(broker_update, expected_status):
    submitted = transition_order_state(
        _accepted_order(),
        {"status": "submitted", "broker_order_id": "broker-123"},
    )

    transitioned = transition_order_state(submitted, broker_update)

    assert transitioned["status"] == expected_status
    assert transitioned["reject_reason"]


@pytest.mark.parametrize(
    ("order", "broker_update"),
    [
        (
            _accepted_order(status="submitted"),
            {"status": "filled", "filled_quantity": 10, "avg_fill_price": 50.25},
        ),
        (
            _accepted_order(status="submitted", broker_order_id="broker-123"),
            {"status": "filled", "broker_order_id": "broker-123"},
        ),
        (
            _accepted_order(status="submitted", broker_order_id="broker-123"),
            {"status": "partially_filled", "broker_order_id": "broker-123", "filled_quantity": 0},
        ),
    ],
)
def test_order_lifecycle_rejects_live_fill_states_without_required_broker_evidence(order, broker_update):
    with pytest.raises(OrderLifecycleError):
        transition_order_state(order, broker_update)


def test_order_lifecycle_blocks_terminal_state_regression():
    filled = _accepted_order(
        status="filled",
        broker_order_id="broker-123",
        filled_quantity=10,
        avg_fill_price=50.25,
    )

    with pytest.raises(OrderLifecycleError, match="terminal"):
        transition_order_state(filled, {"status": "submitted", "broker_order_id": "broker-123"})
