"""Apply final cumulative fills carried by terminal broker order states."""
from __future__ import annotations

from typing import Any

import deps
from trading.broker_execution import BrokerExecutionMixin
from trading import live_order_reconciliation_patch as reconciliation


_current_reconcile = BrokerExecutionMixin.reconcile_live_orders
_TERMINAL_STATUSES = {"canceled", "cancelled", "rejected", "expired"}


def _num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


async def _apply_terminal_fill_deltas(self, symbol: str | None = None) -> float:
    collection = getattr(deps.db, "broker_orders", None)
    if collection is None:
        return 0.0
    query: dict[str, Any] = {
        "status": {"$in": sorted(_TERMINAL_STATUSES)},
        "$expr": {
            "$gt": [
                {"$ifNull": ["$filled_quantity", 0]},
                {"$ifNull": ["$applied_quantity", 0]},
            ]
        },
    }
    if symbol:
        query["symbol"] = symbol.upper()
    docs = await collection.find(query, {"_id": 0}).sort("created_at", 1).to_list(200)
    applied = 0.0
    for doc in docs:
        update = {
            "status": str(doc.get("status") or "cancelled").lower(),
            "broker_order_id": str(doc.get("broker_order_id") or ""),
            "filled_quantity": _num(doc.get("filled_quantity")),
            "filled_price": _num(doc.get("avg_fill_price")),
            "error": str(doc.get("error") or ""),
        }
        applied += await reconciliation._apply_fill_delta(self, doc, update)
    return applied


async def _reconcile_including_terminal_fills(self, symbol: str | None = None) -> dict:
    result = await _current_reconcile(self, symbol)
    terminal_applied = await _apply_terminal_fill_deltas(self, symbol)
    if terminal_applied:
        result["applied"] = float(result.get("applied", 0)) + terminal_applied
        refresher = getattr(self, "refresh_parent_orders", None)
        if callable(refresher):
            await refresher(symbol)
    result["terminal_fill_applied"] = terminal_applied
    return result


BrokerExecutionMixin.reconcile_live_orders = _reconcile_including_terminal_fills
BrokerExecutionMixin.apply_terminal_fill_deltas = _apply_terminal_fill_deltas
