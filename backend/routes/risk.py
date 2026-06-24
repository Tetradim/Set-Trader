"""Risk API routes.

Provides endpoints for risk controls, exposure limits, and kill switches.
"""
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

import deps
from auth import get_current_user, TokenData, require_roles, Role
from advanced_risk import (
    AdvancedRiskLimits,
    CircuitBreakerAdjustmentInput,
    LiquiditySizingInput,
    PortfolioPosition,
    TradeRiskInput,
    VarCvarInput,
    advanced_risk_manager,
)
from risk_controls import (
    risk_controls as _fallback_risk_controls, ExposureLimit, KillSwitchLevel,
    OrderRestriction
)


router = APIRouter(prefix="/risk", tags=["risk"])


def _risk_controls():
    engine = getattr(deps, "engine", None)
    return getattr(engine, "risk_controls", None) or _fallback_risk_controls


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


class AdvancedRiskLimitsRequest(BaseModel):
    max_trade_risk_score: float = 85.0
    max_var_pct: float = 0.05
    max_cvar_pct: float = 0.08


class TradeRiskScoreRequest(BaseModel):
    symbol: str
    side: str
    order_value: float
    account_equity: float
    price: float = 0.0
    quantity: float = 0.0
    volatility_pct: float = 0.0
    average_daily_volume: float = 0.0
    broker_risk_level: str = "medium"
    existing_symbol_exposure: float = 0.0
    portfolio_notional: float = 0.0
    daily_drawdown_pct: float = 0.0
    strategy_confidence: float = 1.0


class LiquiditySizingRequest(BaseModel):
    symbol: str
    requested_order_value: float
    price: float
    account_equity: float
    average_daily_volume: float
    recent_volume: float = 0.0
    max_participation_rate: float = 0.01
    volatility_pct: float = 0.0
    risk_score: float = 0.0
    recent_volume_weight: float = 0.65


class PortfolioPositionRequest(BaseModel):
    symbol: str
    quantity: float
    price: float


class VarCvarRequest(BaseModel):
    positions: List[PortfolioPositionRequest]
    historical_returns: Dict[str, List[float]]
    confidence_level: float = 0.95
    limits: AdvancedRiskLimitsRequest = Field(default_factory=AdvancedRiskLimitsRequest)


class CircuitBreakerAdjustmentRequest(BaseModel):
    volatility_pct: float
    liquidity_score: float = 1.0
    market_stress_score: float = 0.0
    broker_risk_level: str = "medium"
    apply: bool = False


class AdvancedRiskCheckRequest(BaseModel):
    trade: TradeRiskScoreRequest
    limits: AdvancedRiskLimitsRequest = Field(default_factory=AdvancedRiskLimitsRequest)
    liquidity: Optional[LiquiditySizingRequest] = None
    var_cvar: Optional[VarCvarRequest] = None


def _advanced_limits(request: AdvancedRiskLimitsRequest) -> AdvancedRiskLimits:
    return AdvancedRiskLimits(**request.model_dump())


def _trade_input(request: TradeRiskScoreRequest) -> TradeRiskInput:
    return TradeRiskInput(**request.model_dump())


def _liquidity_input(request: LiquiditySizingRequest) -> LiquiditySizingInput:
    return LiquiditySizingInput(**request.model_dump())


def _var_cvar_input(request: VarCvarRequest) -> VarCvarInput:
    return VarCvarInput(
        positions=[PortfolioPosition(**position.model_dump()) for position in request.positions],
        historical_returns={symbol.upper(): returns for symbol, returns in request.historical_returns.items()},
        confidence_level=request.confidence_level,
        limits=_advanced_limits(request.limits),
    )


@router.get("/limits")
async def get_exposure_limits(
    current_user: TokenData = Depends(require_roles([Role.ADMIN, Role.RISK_OFFICER]))
):
    """Get all exposure limits."""
    return {"limits": _risk_controls().get_all_limits()}


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
    _risk_controls().add_exposure_limit(exposure_limit)
    return {"status": "ok", "limit_id": limit.limit_id}


@router.get("/kill-switches")
async def get_kill_switches(
    current_user: TokenData = Depends(require_roles([Role.ADMIN, Role.RISK_OFFICER]))
):
    """Get all kill switches."""
    return {"kill_switches": _risk_controls().get_all_kill_switches()}


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
    
    _risk_controls().add_kill_switch(level, request.target_id)
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
    activated = _risk_controls().activate_kill_switch(
        level, target_id, current_user.username, request.reason
    )
    if not activated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Kill switch not found: {switch_id}"
        )
    
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
    
    deactivated = _risk_controls().deactivate_kill_switch(level, target_id)
    if not deactivated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Kill switch not found: {switch_id}"
        )
    
    return {"status": "ok", "switch_id": switch_id, "is_active": False}


@router.get("/restrictions")
async def get_restrictions(
    current_user: TokenData = Depends(require_roles([Role.ADMIN, Role.RISK_OFFICER]))
):
    """Get all symbol restrictions."""
    controls = _risk_controls()
    return {
        "restricted_symbols": list(controls._symbol_restrictions),
        "order_restrictions": {k: v.value for k, v in controls._order_restrictions.items()}
    }


@router.post("/restrictions/symbol")
async def add_restricted_symbol(
    request: FatFingerRequest,
    current_user: TokenData = Depends(require_roles([Role.ADMIN]))
):
    """Add a restricted symbol."""
    _risk_controls().add_restricted_symbol(request.symbol)
    return {"status": "ok", "symbol": request.symbol}


@router.delete("/restrictions/symbol/{symbol}")
async def remove_restricted_symbol(
    symbol: str,
    current_user: TokenData = Depends(require_roles([Role.ADMIN]))
):
    """Remove a restricted symbol."""
    _risk_controls().remove_restricted_symbol(symbol)
    return {"status": "ok", "symbol": symbol}


@router.post("/fat-finger")
async def set_fat_finger_limit(
    request: FatFingerRequest,
    current_user: TokenData = Depends(require_roles([Role.ADMIN, Role.RISK_OFFICER]))
):
    """Set a fat-finger limit for a symbol."""
    _risk_controls().set_fat_finger_limit(request.symbol, request.max_order_value)
    return {"status": "ok", "symbol": request.symbol, "max_order_value": request.max_order_value}


@router.post("/check")
async def check_order_risk(
    request: RiskCheckRequest,
    current_user: TokenData = Depends(get_current_user)
):
    """Check if an order passes risk controls."""
    result = _risk_controls().check_order(
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


@router.post("/advanced/score")
async def score_advanced_trade_risk(
    request: TradeRiskScoreRequest,
    current_user: TokenData = Depends(get_current_user)
):
    """Score predictive risk for a proposed trade."""
    score = advanced_risk_manager.score_trade(_trade_input(request))
    return score.to_dict()


@router.post("/advanced/liquidity-size")
async def recommend_liquidity_position_size(
    request: LiquiditySizingRequest,
    current_user: TokenData = Depends(get_current_user)
):
    """Recommend order size from predicted tradable volume and market stress."""
    result = advanced_risk_manager.recommend_position_size(_liquidity_input(request))
    return result.to_dict()


@router.post("/advanced/var-cvar")
async def evaluate_portfolio_var_cvar(
    request: VarCvarRequest,
    current_user: TokenData = Depends(require_roles([Role.ADMIN, Role.RISK_OFFICER]))
):
    """Evaluate historical-simulation VaR/CVaR against configured limits."""
    result = advanced_risk_manager.evaluate_var_cvar(_var_cvar_input(request))
    return result.to_dict()


@router.post("/advanced/circuit-breakers/{broker_id}/adjust")
async def adjust_dynamic_circuit_breaker(
    broker_id: str,
    request: CircuitBreakerAdjustmentRequest,
    current_user: TokenData = Depends(require_roles([Role.ADMIN, Role.RISK_OFFICER]))
):
    """Recommend or apply volatility-aware broker circuit-breaker settings."""
    from audit_service import audit_service
    from resilience import broker_resilience

    old_config = broker_resilience.get_config(broker_id)
    recommendation = advanced_risk_manager.recommend_circuit_breaker(
        old_config,
        CircuitBreakerAdjustmentInput(
            broker_id=broker_id,
            volatility_pct=request.volatility_pct,
            liquidity_score=request.liquidity_score,
            market_stress_score=request.market_stress_score,
            broker_risk_level=request.broker_risk_level,
        ),
    )

    if request.apply:
        broker_resilience.set_config(broker_id, recommendation.config)
        await broker_resilience.save_config()
        await audit_service.log_setting_change(
            f"dynamic_resilience_{broker_id}",
            vars(old_config),
            vars(recommendation.config),
        )

    payload = recommendation.to_dict()
    payload["applied"] = request.apply
    return payload


@router.post("/advanced/check")
async def check_advanced_order_risk(
    request: AdvancedRiskCheckRequest,
    current_user: TokenData = Depends(get_current_user)
):
    """Run combined advanced pre-trade checks."""
    assessment = advanced_risk_manager.assess_trade(
        _trade_input(request.trade),
        limits=_advanced_limits(request.limits),
        liquidity=_liquidity_input(request.liquidity) if request.liquidity else None,
        var_cvar=_var_cvar_input(request.var_cvar) if request.var_cvar else None,
    )
    return assessment.to_dict()


@router.get("/status")
async def get_risk_status(
    current_user: TokenData = Depends(get_current_user)
):
    """Get current trading status from risk controls."""
    is_allowed, restriction, message = _risk_controls().isTradingAllowed()
    return {
        "trading_allowed": is_allowed,
        "restriction": restriction.value if restriction else "none",
        "message": message
    }


__all__ = ["router"]
