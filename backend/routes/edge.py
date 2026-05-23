"""REST endpoints for Edge ← Pulse integration.

Edge calls these endpoints to:
- POST /api/tickers/{symbol}/decision - Buy/sell/stop decisions
- POST /api/tickers/{symbol}/trailing - Enable trailing stop
- POST /api/signals - Receive RSI/ORB/volatility signals from Edge
- GET /api/positions/{symbol} - Get position
- GET /api/tickers - Get all tickers
- GET /api/metrics - Prometheus metrics (includes Edge signals)

This matches what sentinel-edge's pulse_client.py expects.
"""
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Header, Depends
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

import deps
from shared import (
    edge_client,
    build_pulse_status,
    build_position_update,
    build_account_update,
)

router = APIRouter(prefix="/edge")

# In-memory signal cache (reset on restart)
# Key = symbol, Value = latest signal dict
_signal_cache: dict = {}


# --- Signal/Decision models (for Edge compatibility) ---
class SignalRequest(BaseModel):
    """Signal request from Edge.
    
    Can include:
    - action: buy/sell/stop (legacy decision)
    - ORB data: orb_high, orb_low, orb_breakout
    - RSI: rsi
    - Patterns: pattern (hs, dtb)
    - Direction: signal_type (bullish/bearish/neutral)
    """
    action: str = "signal"  # Default to signal mode
    confidence: float = 1.0
    bracket: Optional[dict] = None
    decision: str = "hold"  # Legacy field
    
    # Signal fields
    rsi: Optional[float] = None
    signal_type: Optional[str] = None  # bullish, bearish, neutral
    orb_high: Optional[float] = None
    orb_low: Optional[float] = None
    pattern: Optional[str] = None  # hs, dtb, etc
    volatility: Optional[float] = None
    volume: Optional[float] = None


class SignalResponse(BaseModel):
    """Signal response to Edge."""
    status: str
    symbol: str
    action: str = "signal"
    decision: str = "hold"
    confidence: float = 1.0
    message: str = ""


# --- Simple in-memory rate limiter ---
_rate_limits: dict = {}  # ip -> [(timestamp, count), ...]
_RATE_LIMIT = 60        # requests per minute
_RATE_WINDOW = 60        # seconds


def _check_rate_limit(client_ip: str) -> bool:
    """Check if client is within rate limit."""
    import time
    now = time.time()
    
    # Clean old entries
    if client_ip in _rate_limits:
        _rate_limits[client_ip] = [
            (ts, cnt) for ts, cnt in _rate_limits[client_ip]
            if now - ts < _RATE_WINDOW
        ]
    
    # Count requests in window
    total = sum(cnt for _, cnt in _rate_limits.get(client_ip, []))
    if total >= _RATE_LIMIT:
        return False
    
    # Add this request
    if client_ip not in _rate_limits:
        _rate_limits[client_ip] = []
    _rate_limits[client_ip].append((now, 1))
    
    return True


async def validate_api_key(x_api_key: Optional[str] = Header(None)) -> bool:
    """Validate the Edge integration API key."""
    expected = await deps.db.settings.find_one({"key": "edge_api_key"}, {"_id": 0})
    expected_key = expected.get("value", "") if expected else ""
    if not expected_key:
        raise HTTPException(503, "Edge API key is not configured")
    if not x_api_key or not secrets.compare_digest(x_api_key, expected_key):
        raise HTTPException(401, "Invalid API key")
    return True


# --- Pydantic models for Edge requests ---


class DecisionRequest(BaseModel):
    """Request for /api/tickers/{symbol}/decision endpoint.
    
    Edge sends: {"symbol": "TSLA", "decision": "buy", ...}
    """
    symbol: str
    decision: str  # buy, sell, hold, stop, enable_trailing_stop, stop_buying, emergency_stop
    price: Optional[float] = None
    trailing_percent: Optional[float] = None
    confidence: float = 1.0


class TrailingRequest(BaseModel):
    """Request for /api/tickers/{symbol}/trailing endpoint."""
    trailing_percent: float


class SignalResponse(BaseModel):
    """Response for signal submission."""
    status: str
    symbol: str
    action: str
    order_id: Optional[str] = None
    message: str


# --- Endpoints ---


@router.post("/tickers/{symbol}/decision", dependencies=[Depends(validate_api_key)])
async def post_decision(symbol: str, body: DecisionRequest):
    """Process decision from Edge.
    
    Edge calls this to control Pulse behavior:
    - buy: Open position
    - sell: Close position
    - stop: Emergency stop
    - enable_trailing_stop: Activate trailing stop
    - stop_buying: Disable new buys
    - emergency_stop: Halt all trading
    
    Returns: {"status": "ok", "symbol": "...", "decision": "..."}
    """
    sym = symbol.upper()
    decision = body.decision.lower()
    
    # Get ticker config
    ticker = await deps.db.tickers.find_one({"symbol": sym}, {"_id": 0})
    if not ticker:
        raise HTTPException(404, f"{sym} not found")
    
    position = deps.engine._positions.get(sym, {})
    position_qty = position.get("qty", 0)
    
    trading_mode = "paper" if deps.engine.simulate_24_7 else "live"
    market_open = deps.engine.is_market_open()
    
    # Process decision
    result = {"status": "ok", "symbol": sym, "decision": decision}
    
    if decision == "buy":
        if position_qty > 0:
            result["decision"] = "hold"
            result["message"] = "already have position"
        elif body.price:
            try:
                await deps.engine.execute_buy(sym, body.price)
                result["message"] = "buy order executed"
            except Exception as e:
                result["status"] = "error"
                result["message"] = str(e)
        else:
            result["message"] = "price required for buy"
    
    elif decision == "sell":
        if position_qty == 0:
            result["decision"] = "hold"
            result["message"] = "no position to sell"
        else:
            try:
                await deps.engine.execute_sell(sym, body.price)
                result["message"] = "sell order executed"
            except Exception as e:
                result["status"] = "error"
                result["message"] = str(e)
    
    elif decision == "stop":
        if position_qty == 0:
            result["message"] = "no position to stop"
        else:
            try:
                await deps.engine.execute_sell(sym, None)  # Market order
                result["message"] = "position stopped"
            except Exception as e:
                result["status"] = "error"
                result["message"] = str(e)
    
    elif decision == "enable_trailing_stop":
        if body.trailing_percent:
            await deps.db.tickers.update_one(
                {"symbol": sym},
                {"$set": {"trailing_enabled": True, "trailing_percent": body.trailing_percent}},
            )
            result["message"] = f"trailing stop enabled: {body.trailing_percent}%"
        else:
            result["message"] = "trailing_percent required"
    
    elif decision == "stop_buying":
        await deps.db.tickers.update_one(
            {"symbol": sym},
            {"$set": {"enabled": False, "auto_stop_reason": "stop_buying"}},
        )
        result["message"] = f"buying stopped for {sym}"
    
    elif decision == "emergency_stop":
        # Stop all tickers
        await deps.db.tickers.update_many(
            {"enabled": True},
            {"$set": {"enabled": False, "auto_stop_reason": "emergency_stop"}},
        )
        deps.engine.paused = True
        result["message"] = "all trading halted"
    
    else:
        result["message"] = f"unknown decision: {decision}"
    
    # Send position update to Edge if enabled
    if edge_client.is_enabled and edge_client.is_connected:
        try:
            current_price = await deps.price_service.get_price(sym)
            pos_update = build_position_update(
                symbol=sym,
                quantity=position_qty,
                avg_entry=position.get("avg_entry", 0),
                current_price=current_price,
                trading_mode=trading_mode,
            )
            await edge_client.send_position_update(pos_update)
        except Exception:
            pass
    
    return result


@router.post("/tickers/{symbol}/trailing", dependencies=[Depends(validate_api_key)])
async def enable_trailing(symbol: str, body: TrailingRequest):
    """Enable trailing stop for a symbol."""
    sym = symbol.upper()
    
    ticker = await deps.db.tickers.find_one({"symbol": sym}, {"_id": 0})
    if not ticker:
        raise HTTPException(404, f"{sym} not found")
    
    await deps.db.tickers.update_one(
        {"symbol": sym},
        {"$set": {"trailing_enabled": True, "trailing_percent": body.trailing_percent}},
    )
    
    return {"status": "ok", "symbol": sym, "trailing_enabled": True, "trailing_percent": body.trailing_percent}


@router.post("/signals/{symbol}", dependencies=[Depends(validate_api_key)])
async def submit_signal(symbol: str, body: SignalRequest) -> SignalResponse:
    """Receive signals from Edge and update metrics cache.
    
    Edge sends signals here, we:
    1. Process action if provided (legacy buy/sell/stop)
    2. Update signal cache for Prometheus metrics
    
    Edge calls: POST /api/signals/{symbol} with JSON:
    {
        "action": "signal",
        "rsi": 65,
        "signal_type": "bullish",
        "orb_high": 150.25,
        "orb_low": 149.50,
        "pattern": "hs",
        "volatility": 0.25,
        "volume": 1500000
    }
    """
    sym = symbol.upper()
    
    # Legacy action handling - convert to decision
    if body.action.lower() not in ("signal", "hold"):
        decision_map = {"buy": "buy", "sell": "sell", "stop": "stop"}
        body.decision = decision_map.get(body.action.lower(), "hold")
        return await post_decision(symbol, body)
    
    # Update signal cache for Prometheus metrics
    sig_data = {
        "rsi": body.rsi or 0,
        "direction": body.signal_type or "neutral",
        "orb_breakout": body.confidence >= 0.8 if body.confidence else False,
        "orb_direction": 1 if body.signal_type == "bullish" else (-1 if body.signal_type == "bearish" else 0),
        "orb_high": body.orb_high or 0,
        "orb_low": body.orb_low or 0,
        "volatility_24h": body.volatility or 0,
        "pattern_hs": body.pattern == "hs",
        "pattern_dtb": body.pattern == "dtb",
        "volume": body.volume or 0,
    }
    _signal_cache[sym] = sig_data
    
    return SignalResponse(status="ok", symbol=sym, action="signal", message="signal cached")


@router.get("/positions/{symbol}", dependencies=[Depends(validate_api_key)])
async def get_position(symbol: str):
    """Get position for a symbol.
    
    Returns position matching what Edge expects:
    - has_position, pnl, pnl_pct, trailing_enabled, entry_price, drawdown_pct
    """
    sym = symbol.upper()
    
    position = deps.engine._positions.get(sym, {})
    qty = position.get("qty", 0)
    avg_entry = position.get("avg_entry", 0)
    
    ticker = await deps.db.tickers.find_one({"symbol": sym}, {"_id": 0})
    trailing_enabled = ticker.get("trailing_enabled", False) if ticker else False
    trailing_percent = ticker.get("trailing_percent", 2.0) if ticker else 2.0
    
    # Get current price
    current_price = await deps.price_service.get_price(sym)
    
    # Calculate P&L
    pnl = 0.0
    pnl_pct = 0.0
    drawdown_pct = 0.0
    
    if qty > 0 and current_price > 0:
        market_value = qty * current_price
        cost_basis = qty * avg_entry
        pnl = round(market_value - cost_basis, 2)
        
        if cost_basis > 0:
            pnl_pct = round((pnl / cost_basis) * 100, 2)
            # Estimate drawdown
            high = position.get("high", current_price)
            if high > 0:
                drawdown_pct = round(((high - current_price) / high) * 100, 2)
    
    # Send to Edge if enabled
    if edge_client.is_enabled:
        pos_update = build_position_update(
            symbol=sym,
            quantity=qty,
            avg_entry=avg_entry,
            current_price=current_price,
            trading_mode="paper" if deps.engine.simulate_24_7 else "live",
        )
        await edge_client.send_position_update(pos_update)
    
    return {
        "symbol": sym,
        "has_position": qty > 0,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "trailing_enabled": trailing_enabled,
        "trailing_percent": trailing_percent if trailing_enabled else None,
        "entry_price": avg_entry,
        "drawdown_pct": drawdown_pct,
        "quantity": qty,
        "current_price": current_price,
    }


@router.get("/account/status", dependencies=[Depends(validate_api_key)])
async def get_account_status():
    """Get account status.
    
    Edge calls this to get account metrics and positions.
    
    Returns:
        Account status with balances and positions.
    """
    # Get account balances
    balance_doc = await deps.db.settings.find_one({"key": "account_balance"}, {"_id": 0})
    account_balance = round(balance_doc.get("value", 0), 2) if balance_doc else 0
    
    cash_doc = await deps.db.settings.find_one({"key": "cash_reserve"}, {"_id": 0})
    cash_reserve = round(cash_doc.get("value", 0), 2) if cash_doc else 0
    
    # Get allocated capital
    tickers = await deps.db.tickers.find({}, {"_id": 0, "base_power": 1}).to_list(100)
    allocated = round(sum(t.get("base_power", 0) for t in tickers), 2)
    available = round(account_balance - allocated, 2)
    
    # Get positions
    positions = []
    total_unrealized_pnl = 0.0
    
    for sym, position in deps.engine._positions.items():
        if position.get("qty", 0) <= 0:
            continue
        
        current_price = await deps.price_service.get_price(sym)
        qty = position.get("qty", 0)
        avg_entry = position.get("avg_entry", 0)
        
        market_value = round(qty * current_price, 2)
        cost_basis = round(qty * avg_entry, 2)
        unrealized_pnl = round(market_value - cost_basis, 2)
        total_unrealized_pnl += unrealized_pnl
        
        positions.append({
            "symbol": sym,
            "quantity": qty,
            "avg_entry": avg_entry,
            "current_price": current_price,
            "market_value": market_value,
            "unrealized_pnl": unrealized_pnl,
        })
    
    # Get total realized P&L
    profits_list = await deps.db.profits.find({}, {"_id": 0}).to_list(100)
    total_realized_pnl = round(sum(p.get("total_pnl", 0) for p in profits_list), 2)
    
    trading_mode = "paper" if deps.engine.simulate_24_7 else "live"
    
    # Build account update for Edge
    if edge_client.is_enabled:
        acc_update = build_account_update(
            account_balance=account_balance,
            allocated=allocated,
            available=available,
            cash_reserve=cash_reserve,
            total_realized_pnl=total_realized_pnl,
            total_unrealized_pnl=total_unrealized_pnl,
            positions=positions,
            trading_mode=trading_mode,
        )
        # Send to Edge
        await edge_client.send_account_update(acc_update)
    
    return {
        "account_balance": account_balance,
        "allocated": allocated,
        "available": available,
        "cash_reserve": cash_reserve,
        "total_realized_pnl": total_realized_pnl,
        "total_unrealized_pnl": total_unrealized_pnl,
        "open_positions": len(positions),
        "positions": positions,
        "trading_mode": trading_mode,
    }


@router.get("/tickers", dependencies=[Depends(validate_api_key)])
async def get_tickers():
    """Get all configured tickers.
    
    Edge calls this to sync tickers with Pulse.
    """
    tickers = await deps.db.tickers.find({}, {"_id": 0}).to_list(100)
    return tickers


# --- Signal Evaluation Endpoint ---


class SignalEvalRequest(BaseModel):
    """Request for signal evaluation."""
    symbol: str
    price: float
    orb_high: Optional[float] = None
    orb_low: Optional[float] = None
    volume: float = 0
    atr: float = 0
    price_change_pct: float = 0
    # Optional observation from Pulse (6th scoring layer)
    observation: Optional[dict] = None


class SignalEvalResponse(BaseModel):
    """Signal evaluation response."""
    symbol: str
    direction: str  # bullish, bearish, neutral
    strength: float  # -10 to +10
    volume_ratio: float = 1.0
    volume_zscore: float = 0.0
    observation_applied: bool = False  # Whether pattern observation was used


@router.post("/signals/evaluate", dependencies=[Depends(validate_api_key)])
async def evaluate_signal(body: SignalEvalRequest):
    """Evaluate trading signal using Edge-style scoring.
    
    6 Scoring Layers:
    1. ORB breakout analysis
    2. Volume confirmation
    3. Volume anomaly (z-score)
    4. Price momentum
    5. Volatility adjustment
    6. Pattern observation (from Pulse)
    """
    sym = body.symbol.upper()
    
    # Update volume history
    if body.volume > 0:
        deps.price_service.update_volume(sym, body.volume)
    
    # Get latest observation if not provided (query from database)
    observation = body.observation
    if not observation:
        from shared.observation_service import observation_service
        observation_service.set_db(deps.db)
        obs_doc = await observation_service.get_latest_observation(sym)
        if obs_doc:
            observation = {
                "pattern": obs_doc.get("pattern"),
                "confidence": obs_doc.get("confidence", 0.0),
                "direction": obs_doc.get("direction", "neutral"),
            }
    
    # Calculate signal
    direction, strength = deps.price_service.get_signal_strength(
        sym,
        body.price,
        body.orb_high,
        body.orb_low,
        body.volume,
        body.atr,
        body.price_change_pct,
        observation=observation,
    )
    
    volume_ratio = deps.price_service.get_volume_ratio(sym, body.volume)
    volume_zscore = deps.price_service.get_volume_zscore(sym, body.volume)
    
    return SignalEvalResponse(
        symbol=sym,
        direction=direction,
        strength=strength,
        volume_ratio=volume_ratio,
        volume_zscore=volume_zscore,
        observation_applied=observation is not None,
    )


# --- Prometheus metrics for Edge integration ---
@router.get("/metrics", response_class=PlainTextResponse, dependencies=[Depends(validate_api_key)])
async def edge_prometheus_metrics():
    """Expose Edge signals as Prometheus metrics.
    
    Prometheus scrapes this endpoint to get:
    - sentinel_rsi{...}
    - sentinel_orb_*
    - sentinel_volatility_*
    - sentinel_pattern_*
    
    These trigger alerts in sentinel_edge.yml rules.
    """
    import time
    
    lines = []
    timestamp = int(time.time())
    
    # RSI metrics
    lines.append("# HELP sentinel_rsi Relative Strength Index (0-100)")
    lines.append("# TYPE sentinel_rsi gauge")
    for sym, sig in _signal_cache.items():
        rsi = sig.get("rsi", 0)
        direction = sig.get("direction", "neutral")
        lines.append(f'sentinel_rsi{{symbol="{sym}",direction="{direction}"}} {rsi}')
    
    # ORB metrics
    lines.append("# HELP sentinel_orb_breakout Opening Range Breakout indicator")
    lines.append("# TYPE sentinel_orb_breakout gauge")
    for sym, sig in _signal_cache.items():
        breakout = 1 if sig.get("orb_breakout", False) else 0
        orb_direction = sig.get("orb_direction", 0)
        orb_high = sig.get("orb_high", 0)
        orb_low = sig.get("orb_low", 0)
        lines.append(f'sentinel_orb_breakout{{symbol="{sym}",direction="{orb_direction}"}} {breakout}')
        if orb_high or orb_low:
            lines.append(f'sentinel_orb_high{{symbol="{sym}"}} {orb_high}')
            lines.append(f'sentinel_orb_low{{symbol="{sym}"}} {orb_low}')
    
    # Volatility metrics
    lines.append("# HELP sentinel_volatility_24h 24-hour volatility")
    lines.append("# TYPE sentinel_volatility_24h gauge")
    lines.append("# HELP sentinel_volatility_10d_avg 10-day average volatility")
    lines.append("# TYPE sentinel_volatility_10d_avg gauge")
    for sym, sig in _signal_cache.items():
        vol_24h = sig.get("volatility_24h", 0)
        vol_10d = sig.get("volatility_10d_avg", 0)
        lines.append(f'sentinel_volatility_24h{{symbol="{sym}"}} {vol_24h}')
        lines.append(f'sentinel_volatility_10d_avg{{symbol="{sym}"}} {vol_10d}')
    
    # Pattern metrics
    lines.append("# HELP sentinel_pattern_head_shoulders Head & Shoulders pattern")
    lines.append("# TYPE sentinel_pattern_head_shoulders gauge")
    lines.append("# HELP sentinel_pattern_double_top_bottom Double Top/Bottom pattern")
    lines.append("# TYPE sentinel_pattern_double_top_bottom gauge")
    for sym, sig in _signal_cache.items():
        hs = 1 if sig.get("pattern_hs", False) else 0
        dtb = 1 if sig.get("pattern_dtb", False) else 0
        lines.append(f'sentinel_pattern_hs{{symbol="{sym}"}} {hs}')
        lines.append(f'sentinel_pattern_dtb{{symbol="{sym}"}} {dtb}')
    
    # Volume metrics
    lines.append("# HELP sentinel_volume Current volume")
    lines.append("# TYPE sentinel_volume gauge")
    lines.append("# HELP sentinel_volume_20d_avg 20-day average volume")
    lines.append("# TYPE sentinel_volume_20d_avg gauge")
    for sym, sig in _signal_cache.items():
        vol = sig.get("volume", 0)
        vol_20d = sig.get("volume_20d_avg", 0)
        lines.append(f'sentinel_volume{{symbol="{sym}"}} {vol}')
        lines.append(f'sentinel_volume_20d_avg{{symbol="{sym}"}} {vol_20d}')
    
    return "\n".join(lines)
