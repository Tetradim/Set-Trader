"""Orders API routes backed by MongoDB.

The legacy ``orders`` collection is retained for compatibility, while the live
execution UI reads the broker/parent ledgers used by the repaired trading
engine.  Keeping those paths explicit prevents a screen from reporting an
empty book while real broker child orders are working.
"""
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo import ReturnDocument
from pydantic import BaseModel

import deps
from auth import TokenData, get_current_user


router = APIRouter(prefix="/orders", tags=["orders"])


class Order(BaseModel):
    order_id: str
    symbol: str
    side: str
    order_type: str
    quantity: float
    price: float
    status: str
    filled_quantity: float = 0
    avg_fill_price: float = 0.0
    created_at: str
    updated_at: str
    reject_reason: Optional[str] = None
    broker: Optional[str] = None
    external_id: Optional[str] = None
    execution_lag_ms: Optional[int] = None
    slippage_bps: Optional[float] = None


class OrderStats(BaseModel):
    total_orders: int
    filled_orders: int
    rejected_orders: int
    pending_orders: int
    avg_slippage: float
    avg_execution_lag_ms: float
    fill_rate: float


_PENDING_STATUSES = {
    "new",
    "accepted",
    "submitted",
    "pending",
    "working",
    "working_unconfirmed",
    "partially_filled",
    "partial",
}
_FILLED_STATUSES = {"filled", "executed", "complete", "completed"}
_REJECTED_STATUSES = {"rejected", "error", "failed"}
_TERMINAL_STATUSES = _FILLED_STATUSES | _REJECTED_STATUSES | {
    "cancelled",
    "canceled",
    "expired",
}


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _normalise_status(value: Any) -> str:
    raw = str(value or "unknown").strip().lower()
    return {
        "partially-filled": "partially_filled",
        "cancelled": "canceled",
        "complete": "filled",
        "completed": "filled",
        "executed": "filled",
    }.get(raw, raw)


def _order_filter(status_value: Optional[str] = None, symbol: Optional[str] = None) -> dict:
    query = {}
    if status_value:
        query["status"] = status_value
    if symbol:
        query["symbol"] = symbol.upper()
    return query


def _broker_order_for_ui(doc: dict) -> dict:
    requested = _number(
        doc.get("requested_quantity")
        or doc.get("quantity")
        or doc.get("target_quantity")
    )
    filled = _number(doc.get("filled_quantity") or doc.get("filled_qty"))
    applied = _number(doc.get("applied_quantity"))
    avg_fill = _number(
        doc.get("avg_fill_price")
        or doc.get("filled_price")
        or doc.get("average_fill_price")
    )
    reference_price = _number(
        doc.get("reference_price")
        or doc.get("price")
        or doc.get("limit_price")
    )
    order_id = str(
        doc.get("broker_order_id")
        or doc.get("durable_order_id")
        or doc.get("external_id")
        or ""
    )
    status_value = _normalise_status(doc.get("status"))
    error = str(doc.get("error") or doc.get("reject_reason") or "")
    return {
        "order_id": order_id,
        "durable_order_id": str(doc.get("durable_order_id") or order_id),
        "parent_order_id": str(doc.get("parent_order_id") or ""),
        "intent_key": str(doc.get("intent_key") or ""),
        "symbol": str(doc.get("symbol") or "").upper(),
        "side": str(doc.get("side") or "").upper(),
        "order_type": str(doc.get("order_type") or "").upper(),
        "quantity": requested,
        "requested_quantity": requested,
        "filled_quantity": filled,
        "remaining_quantity": round(max(0.0, requested - filled), 8),
        "applied_quantity": applied,
        "unapplied_quantity": round(max(0.0, filled - applied), 8),
        "price": reference_price,
        "avg_fill_price": avg_fill,
        "status": status_value,
        "broker": str(doc.get("broker_id") or doc.get("broker") or ""),
        "account_id": str(doc.get("account_id") or ""),
        "external_id": order_id,
        "reject_reason": error or None,
        "error": error or None,
        "created_at": str(doc.get("created_at") or doc.get("submitted_at") or ""),
        "updated_at": str(doc.get("updated_at") or doc.get("last_applied_at") or ""),
        "valid_until_epoch": _number(doc.get("valid_until_epoch")) or None,
        "cancel_requested_at": doc.get("cancel_requested_at"),
        "reconciliation_required": bool(
            doc.get("reconciliation_required")
            or status_value in {"ambiguous", "working_unconfirmed"}
            or filled > applied + 1e-8
        ),
        "execution_quotes": list(doc.get("execution_quotes") or []),
    }


def _parent_order_for_ui(doc: dict) -> dict:
    target = _number(doc.get("target_quantity"))
    filled = _number(doc.get("filled_quantity"))
    return {
        "parent_order_id": str(doc.get("parent_order_id") or ""),
        "intent_key": str(doc.get("intent_key") or ""),
        "symbol": str(doc.get("symbol") or "").upper(),
        "side": str(doc.get("side") or "").upper(),
        "order_type": str(doc.get("order_type") or "").upper(),
        "policy": str(doc.get("policy") or ""),
        "target_quantity": target,
        "filled_quantity": filled,
        "remaining_quantity": _number(doc.get("remaining_quantity")) or round(max(0.0, target - filled), 8),
        "state": str(doc.get("state") or "unknown"),
        "child_order_ids": list(doc.get("child_order_ids") or []),
        "valid_until_epoch": _number(doc.get("valid_until_epoch")) or None,
        "created_at": str(doc.get("created_at") or ""),
        "updated_at": str(doc.get("updated_at") or ""),
    }


def _live_stats(orders: list[dict], parents: list[dict]) -> dict:
    total = len(orders)
    filled = sum(1 for order in orders if order["status"] in _FILLED_STATUSES)
    rejected = sum(1 for order in orders if order["status"] in _REJECTED_STATUSES)
    pending = sum(1 for order in orders if order["status"] in _PENDING_STATUSES)
    reconciliation = sum(1 for order in orders if order.get("reconciliation_required"))
    fill_rate = filled / total * 100 if total else 0.0
    return {
        "total_orders": total,
        "filled_orders": filled,
        "rejected_orders": rejected,
        "pending_orders": pending,
        "reconciliation_required": reconciliation,
        "working_parent_orders": sum(1 for parent in parents if parent.get("state") == "working"),
        "partial_parent_orders": sum(1 for parent in parents if parent.get("state") == "partial_complete"),
        "avg_slippage": 0.0,
        "avg_execution_lag_ms": 0.0,
        "fill_rate": round(fill_rate, 1),
    }


@router.get("", response_model=list[Order])
async def get_orders(
    limit: int = Query(100, ge=1, le=1000),
    status_value: Optional[str] = Query(None, alias="status"),
    symbol: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user),
):
    """Get legacy order records retained for compatibility."""
    return await deps.db.orders.find(
        _order_filter(status_value, symbol),
        {"_id": 0},
    ).sort("created_at", -1).to_list(limit)


@router.get("/live")
async def get_live_order_ledger(
    limit: int = Query(200, ge=1, le=1000),
    symbol: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user),
):
    """Return the authoritative live child, parent, and completed-cycle ledgers."""
    child_query: dict[str, Any] = {}
    parent_query: dict[str, Any] = {}
    cycle_query: dict[str, Any] = {}
    if symbol:
        symbol_value = symbol.upper()
        child_query["symbol"] = symbol_value
        parent_query["symbol"] = symbol_value
        cycle_query["symbol"] = symbol_value

    broker_collection = getattr(deps.db, "broker_orders", None)
    parent_collection = getattr(deps.db, "parent_orders", None)
    cycle_collection = getattr(deps.db, "strategy_cycles", None)

    child_docs = []
    parent_docs = []
    cycle_docs = []
    if broker_collection is not None:
        child_docs = await broker_collection.find(child_query, {"_id": 0}).sort("created_at", -1).to_list(limit)
    if parent_collection is not None:
        parent_docs = await parent_collection.find(parent_query, {"_id": 0}).sort("created_at", -1).to_list(limit)
    if cycle_collection is not None:
        cycle_docs = await cycle_collection.find(cycle_query, {"_id": 0}).sort("completed_at", -1).to_list(limit)

    orders = [_broker_order_for_ui(doc) for doc in child_docs]
    parents = [_parent_order_for_ui(doc) for doc in parent_docs]
    cycles = [dict(doc) for doc in cycle_docs]
    return {
        "orders": orders,
        "parent_orders": parents,
        "strategy_cycles": cycles,
        "stats": _live_stats(orders, parents),
        "source": "broker_orders",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/stats", response_model=OrderStats)
async def get_order_stats(current_user: TokenData = Depends(get_current_user)):
    """Get legacy order execution statistics."""
    orders = await deps.db.orders.find({}, {"_id": 0}).to_list(5000)
    total = len(orders)
    filled = sum(1 for order in orders if order.get("status") == "filled")
    rejected = sum(1 for order in orders if order.get("status") == "rejected")
    pending = sum(1 for order in orders if order.get("status") == "pending")

    slippage_values = [float(order.get("slippage_bps", 0)) for order in orders if order.get("slippage_bps") is not None]
    lag_values = [float(order.get("execution_lag_ms", 0)) for order in orders if order.get("execution_lag_ms") is not None]
    fill_rate = (filled / total * 100) if total else 0

    return OrderStats(
        total_orders=total,
        filled_orders=filled,
        rejected_orders=rejected,
        pending_orders=pending,
        avg_slippage=round(sum(slippage_values) / len(slippage_values), 2) if slippage_values else 0,
        avg_execution_lag_ms=round(sum(lag_values) / len(lag_values), 0) if lag_values else 0,
        fill_rate=round(fill_rate, 1),
    )


@router.get("/{order_id}", response_model=Order)
async def get_order(order_id: str, current_user: TokenData = Depends(get_current_user)):
    """Get a specific legacy order."""
    order = await deps.db.orders.find_one({"order_id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order


async def add_order(order_data: dict):
    """Add an order from the trading engine."""
    now = datetime.now(timezone.utc).isoformat()
    doc = {**order_data}
    doc.setdefault("created_at", now)
    doc.setdefault("updated_at", now)
    await deps.db.orders.update_one({"order_id": doc["order_id"]}, {"$set": doc}, upsert=True)
    return doc


async def update_order(order_id: str, **updates):
    """Update an order."""
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    return await deps.db.orders.find_one_and_update(
        {"order_id": order_id},
        {"$set": updates},
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )


__all__ = ["router", "add_order", "update_order"]
