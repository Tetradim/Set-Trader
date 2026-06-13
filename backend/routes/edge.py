"""REST endpoints for Edge/Pulse integration.

Edge calls these endpoints to:
- POST /api/edge/handoff - Structured broker-control handoffs
- POST /api/edge/tickers/{symbol}/decision - Legacy buy/sell/stop decisions
- POST /api/edge/tickers/{symbol}/trailing - Enable trailing stop
- POST /api/edge/signals/{symbol} - Receive signal context from Edge
- GET /api/edge/positions/{symbol} - Get position
- GET /api/edge/tickers - Get all tickers
- GET /api/edge/account/status - Get account and open positions
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import PlainTextResponse

import deps
from shared import (
    edge_client,
    build_pulse_status,
    build_position_update,
    build_account_update,
)

from routes.edge_contracts import (
    DecisionRequest,
    PulseHandoffAction,
    PulseHandoffRequest,
    SignalEvalRequest,
    SignalEvalResponse,
    SignalRequest,
    SignalResponse,
    TrailingRequest,
    _check_rate_limit,
    _current_position,
    validate_api_key,
)

router = APIRouter(prefix="/edge")

# In-memory signal cache (reset on restart)
# Key = symbol, Value = latest signal dict
_signal_cache: dict = {}


def _handoff_response(
    body: PulseHandoffRequest,
    *,
    accepted: bool,
    status: str,
    reason: str,
    message: str = "",
) -> dict:
    response = {
        "accepted": accepted,
        "sent": accepted,
        "status": status,
        "reason": reason,
        "symbol": body.symbol,
        "action": body.action.value,
        "handoff_id": body.idempotency_key,
    }
    if message:
        response["message"] = message
    return response


async def _handoff_price(symbol: str, body: PulseHandoffRequest) -> float:
    metadata = body.metadata if isinstance(body.metadata, dict) else {}
    for key in ("price", "current_price", "last_price"):
        value = metadata.get(key)
        if value is not None:
            try:
                price = float(value)
            except (TypeError, ValueError):
                continue
            if price > 0:
                return price
    return float(await deps.price_service.get_price(symbol))


async def _set_trailing(symbol: str, trailing_percent: float, *, opening_bell: bool = False) -> None:
    updates = {
        "trailing_enabled": True,
        "trailing_percent": trailing_percent,
    }
    if opening_bell:
        updates.update(
            {
                "opening_bell_enabled": True,
                "opening_bell_trail_value": trailing_percent,
                "opening_bell_trail_is_percent": True,
            }
        )
    await deps.db.tickers.update_one({"symbol": symbol}, {"$set": updates})


async def _set_global_trailing(trailing_percent: float, *, opening_bell: bool = False) -> None:
    updates = {
        "trailing_enabled": True,
        "trailing_percent": trailing_percent,
    }
    if opening_bell:
        updates.update(
            {
                "opening_bell_enabled": True,
                "opening_bell_trail_value": trailing_percent,
                "opening_bell_trail_is_percent": True,
            }
        )
    await deps.db.tickers.update_many({}, {"$set": updates})


async def _set_stop_buying(symbol: str, reason: str) -> None:
    await deps.db.tickers.update_one(
        {"symbol": symbol},
        {"$set": {"enabled": False, "auto_stop_reason": reason or "edge_stop_buying"}},
    )


async def _set_dca_plan(symbol: str, body: PulseHandoffRequest) -> None:
    plan = body.dca.model_dump(exclude_none=True) if body.dca else {}
    steps = int(plan.get("steps", 1))
    allocation_pct = float(plan.get("allocation_pct", 100.0 / max(steps, 1)))
    buy_legs = [
        {"alloc_pct": allocation_pct, "offset": 0.0, "is_percent": True}
        for _ in range(max(steps, 1))
    ]
    await deps.db.tickers.update_one(
        {"symbol": symbol},
        {"$set": {"partial_fills_enabled": True, "buy_legs": buy_legs, "dca_plan": plan}},
    )


async def _process_global_handoff(body: PulseHandoffRequest) -> dict:
    action = body.action

    try:
        if action in {
            PulseHandoffAction.TRAILING_STOP,
            PulseHandoffAction.TIGHTEN_TRAILING_STOP,
        }:
            await _set_global_trailing(float(body.trailing_percent))

        elif action == PulseHandoffAction.OPENING_TRAILING_STOP:
            await _set_global_trailing(float(body.trailing_percent), opening_bell=True)

        elif action in {PulseHandoffAction.STOP_BUYING, PulseHandoffAction.STOP_ALL}:
            await deps.db.tickers.update_many(
                {"enabled": True},
                {"$set": {"enabled": False, "auto_stop_reason": body.reason or "edge_global_stop"}},
            )
            if action == PulseHandoffAction.STOP_ALL:
                deps.engine.paused = True

        elif action == PulseHandoffAction.EMERGENCY_EXIT:
            open_positions = [
                (symbol, position)
                for symbol, position in list(getattr(deps.engine, "_positions", {}).items())
                if float(position.get("qty", 0) or 0) > 0
            ]
            for symbol, _position in open_positions:
                await deps.engine.execute_sell(symbol, None)
            await deps.db.tickers.update_many(
                {"enabled": True},
                {"$set": {"enabled": False, "auto_stop_reason": body.reason or "edge_emergency_exit"}},
            )
            deps.engine.paused = True

        else:
            return _handoff_response(
                body,
                accepted=False,
                status="rejected",
                reason="global_action_not_supported",
                message=f"{action.value} is not supported for GLOBAL handoffs",
            )

    except Exception as exc:
        return _handoff_response(
            body,
            accepted=False,
            status="failed",
            reason=exc.__class__.__name__,
            message=str(exc),
        )

    return _handoff_response(
        body,
        accepted=True,
        status="accepted",
        reason="pulse_accepted",
        message=f"{action.value} accepted for GLOBAL",
    )


# --- Endpoints ---


@router.get("/status", dependencies=[Depends(validate_api_key)])
async def get_edge_status():
    """Return Edge communication health for setup and beta diagnostics."""
    expected = await deps.db.settings.find_one({"key": "edge_api_key"}, {"_id": 0})
    expected_key = expected.get("value", "") if expected else ""
    return {
        "api_key_configured": bool(expected_key),
        "signals_cached": len(_signal_cache),
        "max_retry_attempts": edge_client.max_retry_attempts,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mongo": edge_client.status_snapshot(),
    }


@router.post("/handoff", dependencies=[Depends(validate_api_key)])
async def post_handoff(body: PulseHandoffRequest):
    """Process a structured autonomous handoff from Sentinel Edge."""
    sym = body.symbol
    if sym == "GLOBAL":
        return await _process_global_handoff(body)

    ticker = await deps.db.tickers.find_one({"symbol": sym}, {"_id": 0})
    if not ticker:
        return _handoff_response(
            body,
            accepted=False,
            status="rejected",
            reason="ticker_not_found",
            message=f"{sym} is not configured in Pulse",
        )

    action = body.action
    position = _current_position(sym)
    position_qty = float(position.get("qty", 0) or 0)

    try:
        if action == PulseHandoffAction.BUY:
            if position_qty > 0:
                return _handoff_response(
                    body,
                    accepted=False,
                    status="rejected",
                    reason="already_have_position",
                    message=f"{sym} already has an open position",
                )
            price = await _handoff_price(sym, body)
            if price <= 0:
                return _handoff_response(body, accepted=False, status="rejected", reason="price_unavailable")
            await deps.engine.execute_buy(sym, price)

        elif action in {PulseHandoffAction.SELL, PulseHandoffAction.EMERGENCY_EXIT, PulseHandoffAction.REGULAR_STOP}:
            if position_qty <= 0:
                return _handoff_response(
                    body,
                    accepted=False,
                    status="rejected",
                    reason="no_position",
                    message=f"{sym} has no open position",
                )
            price = await _handoff_price(sym, body)
            await deps.engine.execute_sell(sym, price)

        elif action == PulseHandoffAction.STOP_BUYING:
            await _set_stop_buying(sym, body.reason)

        elif action == PulseHandoffAction.STOP_ALL:
            await deps.db.tickers.update_many(
                {"enabled": True},
                {"$set": {"enabled": False, "auto_stop_reason": body.reason or "edge_stop_all"}},
            )
            deps.engine.paused = True

        elif action == PulseHandoffAction.TRAILING_STOP:
            await _set_trailing(sym, float(body.trailing_percent))

        elif action == PulseHandoffAction.OPENING_TRAILING_STOP:
            await _set_trailing(sym, float(body.trailing_percent), opening_bell=True)

        elif action == PulseHandoffAction.TIGHTEN_TRAILING_STOP:
            await _set_trailing(sym, float(body.trailing_percent))

        elif action == PulseHandoffAction.TIGHTEN_STOP:
            metadata = body.metadata if isinstance(body.metadata, dict) else {}
            updates = {"auto_stop_reason": body.reason or "edge_tighten_stop"}
            if metadata.get("stop_offset") is not None:
                updates["stop_offset"] = float(metadata["stop_offset"])
            await deps.db.tickers.update_one({"symbol": sym}, {"$set": updates})

        elif action == PulseHandoffAction.DCA:
            await _set_dca_plan(sym, body)

    except Exception as exc:
        return _handoff_response(
            body,
            accepted=False,
            status="failed",
            reason=exc.__class__.__name__,
            message=str(exc),
        )

    return _handoff_response(
        body,
        accepted=True,
        status="accepted",
        reason="pulse_accepted",
        message=f"{action.value} accepted for {sym}",
    )


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
    
    position = _current_position(sym)
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
    
    # Send position update to Edge if enabled. Refresh after the decision so Edge
    # gets the post-execution position rather than the stale pre-decision state.
    if edge_client.is_enabled and edge_client.is_connected:
        try:
            position = _current_position(sym)
            position_qty = position.get("qty", 0)
            current_price = await deps.price_service.get_price(sym)
            pos_update = build_position_update(
                symbol=sym,
                quantity=position_qty,
                avg_entry=position.get("avg_entry", 0),
                current_price=current_price,
                trading_mode=trading_mode,
            )
            result["edge_update_sent"] = await edge_client.send_position_update(pos_update)
        except Exception as e:
            result["edge_update_sent"] = False
            result["edge_update_error"] = str(e)
    
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
        decision_map = {
            "buy": "buy",
            "sell": "sell",
            "stop": "stop",
            "enable_trailing_stop": "enable_trailing_stop",
            "trailing": "enable_trailing_stop",
            "stop_buying": "stop_buying",
            "emergency_stop": "emergency_stop",
        }
        decision_body = DecisionRequest(
            symbol=sym,
            decision=decision_map.get(body.action.lower(), "hold"),
            price=body.price,
            trailing_percent=body.trailing_percent,
            confidence=body.confidence,
        )
        return await post_decision(symbol, decision_body)
    
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
    
    position = _current_position(sym)
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
