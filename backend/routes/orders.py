"""Orders API routes.

Provides endpoints for order management and execution analytics.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from auth import get_current_user, TokenData


router = APIRouter(prefix="/api/orders", tags=["orders"])


# In-memory order storage (replace with database in production)
_orders_db = []


# Models
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


class OrderStats(BaseModel):
    total_orders: int
    filled_orders: int
    rejected_orders: int
    pending_orders: int
    avg_slippage: float
    avg_execution_lag_ms: float
    fill_rate: float


@router.get("", response_model=List[Order])
async def get_orders(
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[str] = None,
    symbol: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user)
):
    """Get list of orders."""
    orders = _orders_db
    
    if status:
        orders = [o for o in orders if o["status"] == status]
    if symbol:
        orders = [o for o in orders if o["symbol"] == symbol]
    
    # Sort by created_at descending
    orders = sorted(orders, key=lambda x: x["created_at"], reverse=True)
    
    return orders[:limit]


@router.get("/stats", response_model=OrderStats)
async def get_order_stats(
    current_user: TokenData = Depends(get_current_user)
):
    """Get order execution statistics."""
    orders = _orders_db
    
    total = len(orders)
    filled = len([o for o in orders if o["status"] == "filled"])
    rejected = len([o for o in orders if o["status"] == "rejected"])
    pending = len([o for o in orders if o["status"] == "pending"])
    
    # Calculate average slippage (in bps)
    filled_orders = [o for o in orders if o["status"] == "filled" and o.get("slippage_bps")]
    avg_slippage = 0
    if filled_orders:
        avg_slippage = sum(o.get("slippage_bps", 0) for o in filled_orders) / len(filled_orders)
    
    # Calculate average execution lag
    orders_with_lag = [o for o in orders if o.get("execution_lag_ms")]
    avg_lag = 0
    if orders_with_lag:
        avg_lag = sum(o.get("execution_lag_ms", 0) for o in orders_with_lag) / len(orders_with_lag)
    
    fill_rate = (filled / total * 100) if total > 0 else 0
    
    return OrderStats(
        total_orders=total,
        filled_orders=filled,
        rejected_orders=rejected,
        pending_orders=pending,
        avg_slippage=round(avg_slippage, 2),
        avg_execution_lag_ms=round(avg_lag, 0),
        fill_rate=round(fill_rate, 1)
    )


@router.get("/{order_id}", response_model=Order)
async def get_order(
    order_id: str,
    current_user: TokenData = Depends(get_current_user)
):
    """Get a specific order."""
    for order in _orders_db:
        if order["order_id"] == order_id:
            return order
    
    from fastapi import HTTPException, status
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Order not found"
    )


# Helper function to add orders from trading engine
def add_order(order_data: dict):
    """Add an order to the database."""
    _orders_db.append(order_data)


# Helper function to update order status
def update_order(order_id: str, **updates):
    """Update an order."""
    for order in _orders_db:
        if order["order_id"] == order_id:
            order.update(updates)
            return order
    return None


__all__ = ["router", "add_order", "update_order"]