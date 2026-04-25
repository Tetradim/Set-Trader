"""Risk API routes.

Provides endpoints for risk controls, exposure limits, and kill switches.
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from auth import get_current_user, TokenData, require_roles, Role
from risk_controls import (
    risk_controls, ExposureLimit, KillSwitchLevel, 
    OrderRestriction
)


router = APIRouter(prefix="/api/risk", tags=["risk"])


# Request/Response models
class ExposureLimitRequest(BaseModel):
    limit_id: str
    level: str
    level_id: str
    max_notional: float = 0.0
    max_daily_loss: float = 0.0
    max_position_size: float = 0.0
    max_orders_per_minute: int = 0
    soft_limit: float = 0.0
    is_enabled: bool = True


class KillSwitchRequest(BaseModel):
    level: str
    target_id: str
    reason: str = ""


class RestrictionRequest(BaseModel):
    target: str
    restriction: str


class FatFingerRequest(BaseModel):
    symbol: str
    max_order_value: float


class RiskCheckRequest(BaseModel):
    symbol: str
    order_value: float
    account: str = None
    desk: str = None
    strategy: str = None
    broker: str = None


@router.get("/limits")
async def get_exposure_limits(
    current_user: TokenData = Depends(require_roles([Role.ADMIN, Role.RISK_OFFICER]))
):
    """Get all exposure limits."""
    return {"limits": risk_controls.get_all_limits()}


@router.post("/limits")
async def create_exposure_limit(
    limit: ExposureLimitRequest,
    current_user: TokenData = Depends(require_roles([Role.ADMIN]))
):
    """Create or update an exposure limit."""
    exposure_limit = ExposureLimit(
        limit_id=limit.limit_id,
        level=limit.level,
        level_id=limit.level_id,
        max_notional=limit.max_notional,
        max_daily_loss=limit.max_daily_loss,
        max_position_size=limit.max_position_size,
        max_orders_per_minute=limit.max_orders_per_minute,
        soft_limit=limit.soft_limit,
        is_enabled=limit.is_enabled
    )
    risk_controls.add_exposure_limit(exposure_limit)
    return {"status": "ok", "limit_id": limit.limit_id}


@router.get("/kill-switches")
async def get_kill_switches(
    current_user: TokenData = Depends(require_roles([Role.ADMIN, Role.RISK_OFFICER]))
):
    """Get all kill switches."""
    return {"kill_switches": risk_controls.get_all_kill_switches()}


@router.post("/kill-switches")
async def create_kill_switch(
    request: KillSwitchRequest,
    current_user: TokenData = Depends(require_roles([Role.ADMIN]))
):
    """Create a kill switch."""
    try:
        level = KillSwitchLevel(request.level)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid level: {request.level}"
        )
    
    risk_controls.add_kill_switch(level, request.target_id)
    switch_id = f"{request.level}:{request.target_id}"
    return {"status": "ok", "switch_id": switch_id}


@router.post("/kill-switches/{switch_id}")
async def toggle_kill_switch(
    switch_id: str,
    request: KillSwitchRequest,
    current_user: TokenData = Depends(require_roles([Role.ADMIN, Role.RISK_OFFICER]))
):
    """Activate or deactivate a kill switch."""
    parts = switch_id.split(":")
    if len(parts) != 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid switch_id format"
        )
    
    level_str, target_id = parts
    try:
        level = KillSwitchLevel(level_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid level: {level_str}"
        )
    
    # Activate the kill switch
    risk_controls.activate_kill_switch(level, target_id, current_user.username, request.reason)
    
    return {"status": "ok", "switch_id": switch_id, "is_active": True}


@router.delete("/kill-switches/{switch_id}")
async def deactivate_kill_switch(
    switch_id: str,
    current_user: TokenData = Depends(require_roles([Role.ADMIN]))
):
    """Deactivate a kill switch."""
    parts = switch_id.split(":")
    if len(parts) != 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid switch_id format"
        )
    
    level_str, target_id = parts
    try:
        level = KillSwitchLevel(level_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid level: {level_str}"
        )
    
    risk_controls.deactivate_kill_switch(level, target_id)
    
    return {"status": "ok", "switch_id": switch_id, "is_active": False}


@router.get("/restrictions")
async def get_restrictions(
    current_user: TokenData = Depends(require_roles([Role.ADMIN, Role.RISK_OFFICER]))
):
    """Get all symbol restrictions."""
    return {
        "restricted_symbols": list(risk_controls._symbol_restrictions),
        "order_restrictions": {k: v.value for k, v in risk_controls._order_restrictions.items()}
    }


@router.post("/restrictions/symbol")
async def add_restricted_symbol(
    request: FatFingerRequest,
    current_user: TokenData = Depends(require_roles([Role.ADMIN]))
):
    """Add a restricted symbol."""
    risk_controls.add_restricted_symbol(request.symbol)
    return {"status": "ok", "symbol": request.symbol}


@router.delete("/restrictions/symbol/{symbol}")
async def remove_restricted_symbol(
    symbol: str,
    current_user: TokenData = Depends(require_roles([Role.ADMIN]))
):
    """Remove a restricted symbol."""
    risk_controls.remove_restricted_symbol(symbol)
    return {"status": "ok", "symbol": symbol}


@router.post("/fat-finger")
async def set_fat_finger_limit(
    request: FatFingerRequest,
    current_user: TokenData = Depends(require_roles([Role.ADMIN, Role.RISK_OFFICER]))
):
    """Set a fat-finger limit for a symbol."""
    risk_controls.set_fat_finger_limit(request.symbol, request.max_order_value)
    return {"status": "ok", "symbol": request.symbol, "max_order_value": request.max_order_value}


@router.post("/check")
async def check_order_risk(
    request: RiskCheckRequest,
    current_user: TokenData = Depends(get_current_user)
):
    """Check if an order passes risk controls."""
    result = risk_controls.check_order(
        symbol=request.symbol,
        order_value=request.order_value,
        account=request.account,
        desk=request.desk,
        strategy=request.strategy,
        broker=request.broker
    )
    return {
        "is_allowed": result.is_allowed,
        "restriction": result.restriction.value,
        "message": result.message,
        "rejected_fields": result.rejected_fields
    }


@router.get("/status")
async def get_risk_status(
    current_user: TokenData = Depends(get_current_user)
):
    """Get current trading status from risk controls."""
    is_allowed, restriction, message = risk_controls.isTradingAllowed()
    return {
        "trading_allowed": is_allowed,
        "restriction": restriction.value if restriction else "none",
        "message": message
    }


__all__ = ["router"]