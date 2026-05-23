"""Orders API routes backed by MongoDB."""
from datetime import datetime, timezone
from typing import Optional

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
    quantity: int
    price: float
    status: str
    filled_quantity: int = 0
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


def _order_filter(status_value: Optional[str] = None, symbol: Optional[str] = None) -> dict:
    query = {}
    if status_value:
        query["status"] = status_value
    if symbol:
        query["symbol"] = symbol.upper()
    return query


@router.get("", response_model=list[Order])
async def get_orders(
    limit: int = Query(100, ge=1, le=1000),
    status_value: Optional[str] = Query(None, alias="status"),
    symbol: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user),
):
    """Get list of orders."""
    return await deps.db.orders.find(
        _order_filter(status_value, symbol),
        {"_id": 0},
    ).sort("created_at", -1).to_list(limit)


@router.get("/stats", response_model=OrderStats)
async def get_order_stats(current_user: TokenData = Depends(get_current_user)):
    """Get order execution statistics."""
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
    """Get a specific order."""
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
