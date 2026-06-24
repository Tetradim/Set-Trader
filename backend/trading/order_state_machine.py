"""Broker-confirmed order lifecycle transitions.

This reducer is intentionally pure: callers pass the current local order record
and the latest broker/reconciliation update, and receive the next local state.
Live execution code should still treat the broker as authoritative.
"""

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


class OrderLifecycleError(ValueError):
    """Raised when an order state transition would make local state unsafe."""


_STATUS_ALIASES = {
    "accepted": "accepted",
    "cancelled": "canceled",
    "canceled": "canceled",
    "complete": "filled",
    "completed": "filled",
    "done": "filled",
    "executed": "filled",
    "expired": "stale",
    "failed": "rejected",
    "filled": "filled",
    "partial": "partially_filled",
    "partially-filled": "partially_filled",
    "partially_filled": "partially_filled",
    "pending": "accepted",
    "rejected": "rejected",
    "stale": "stale",
    "submitted": "submitted",
}

_TERMINAL_STATUSES = {"canceled", "filled", "rejected", "stale"}

_ALLOWED_TRANSITIONS = {
    "accepted": {"submitted", "canceled", "rejected", "stale"},
    "submitted": {"submitted", "partially_filled", "filled", "canceled", "rejected", "stale"},
    "partially_filled": {"partially_filled", "filled", "canceled", "rejected", "stale"},
    "filled": {"filled"},
    "canceled": {"canceled"},
    "rejected": {"rejected"},
    "stale": {"stale"},
}


def _normalize_status(status: Any) -> str:
    normalized = str(status or "").strip().lower().replace(" ", "_")
    if normalized not in _STATUS_ALIASES:
        raise OrderLifecycleError(f"unsupported order status: {status!r}")
    return _STATUS_ALIASES[normalized]


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _broker_order_id(order: dict, broker_update: dict) -> str:
    for key in ("broker_order_id", "order_id", "external_id"):
        value = str((broker_update or {}).get(key) or "").strip()
        if value:
            return value
    for key in ("broker_order_id", "external_id"):
        value = str((order or {}).get(key) or "").strip()
        if value:
            return value
    return ""


def _validate_transition(current_status: str, next_status: str) -> None:
    allowed = _ALLOWED_TRANSITIONS.get(current_status, set())
    if current_status in _TERMINAL_STATUSES and next_status != current_status:
        raise OrderLifecycleError(
            f"cannot transition terminal order from {current_status} to {next_status}"
        )
    if next_status not in allowed:
        raise OrderLifecycleError(
            f"cannot transition order from {current_status} to {next_status}"
        )


def _validate_broker_evidence(order: dict, broker_update: dict, next_status: str) -> None:
    broker_order_id = _broker_order_id(order, broker_update)
    filled_quantity = _number(broker_update.get("filled_quantity", order.get("filled_quantity")))
    avg_fill_price = _number(broker_update.get("avg_fill_price", order.get("avg_fill_price")))
    order_quantity = _number(order.get("quantity"))

    if next_status in {"submitted", "partially_filled", "filled", "canceled", "stale"} and not broker_order_id:
        raise OrderLifecycleError(f"{next_status} orders require a broker order identifier")

    if next_status in {"partially_filled", "filled"}:
        if filled_quantity <= 0:
            raise OrderLifecycleError(f"{next_status} orders require a positive filled quantity")
        if avg_fill_price <= 0:
            raise OrderLifecycleError(f"{next_status} orders require a positive average fill price")

    if next_status == "partially_filled" and order_quantity > 0 and filled_quantity >= order_quantity:
        raise OrderLifecycleError("partially_filled quantity must be below total order quantity")

    if next_status == "filled" and order_quantity > 0 and filled_quantity < order_quantity:
        raise OrderLifecycleError("filled orders require filled quantity to meet the order quantity")

    if next_status in {"canceled", "rejected", "stale"}:
        reason = str(
            broker_update.get("reject_reason")
            or broker_update.get("error")
            or broker_update.get("message")
            or ""
        ).strip()
        if not reason:
            raise OrderLifecycleError(f"{next_status} orders require a reason")


def transition_order_state(order: dict, broker_update: dict) -> dict:
    """Return a safe next order state from a broker/reconciliation update."""
    if not order:
        raise OrderLifecycleError("current order is required")
    if not broker_update:
        raise OrderLifecycleError("broker update is required")

    current_status = _normalize_status(order.get("status"))
    next_status = _normalize_status(broker_update.get("status"))
    _validate_transition(current_status, next_status)
    _validate_broker_evidence(order, broker_update, next_status)

    next_order = deepcopy(order)
    for key, value in broker_update.items():
        if key == "status":
            continue
        next_order[key] = value
    next_order["status"] = next_status

    broker_order_id = _broker_order_id(next_order, broker_update)
    if broker_order_id:
        next_order["broker_order_id"] = broker_order_id
    next_order["updated_at"] = datetime.now(timezone.utc).isoformat()
    return next_order
