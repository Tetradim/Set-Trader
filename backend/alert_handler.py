"""Alert handler for Prometheus Alertmanager webhooks.

Receives alerts from Alertmanager and executes corresponding Pulse actions.
"""
from fastapi import APIRouter, Request
from typing import Any
import logging
import os
import secrets

from fastapi import Header, HTTPException, status


router = APIRouter()
logger = logging.getLogger("AlertHandler")


# Map alert names to Pulse actions and their parameters
# Format: (action_type, param_key, param_value)
ALERT_ACTIONS = {
    "EdgeVolatilitySurge":    ("update_ticker", "enabled", False),  # Pause ticker
    "EdgeORBBreakoutBull":     ("adjust_bracket", "buy_offset_delta", -0.5),  # Lower buy offset
    "EdgeORBBreakoutBear":    ("adjust_bracket", "stop_offset_delta", 0.5),  # Tighten stop
    "EdgeRSIOverbought":       ("block_buy", "buy_blocked", True),  # Block new buys
    "EdgePatternHS":           ("update_ticker", "enabled", False),  # Pause ticker entirely
}


@router.post("/alerts/webhook")
async def receive_alert(request: Request, x_webhook_secret: str = Header("", alias="X-Webhook-Secret")):
    """Receive Alertmanager webhook and dispatch to appropriate handlers."""
    expected_secret = os.getenv("ALERT_WEBHOOK_SECRET", "")
    if not expected_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Alert webhook secret is not configured",
        )
    if not secrets.compare_digest(x_webhook_secret, expected_secret):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook secret")

    body: dict[str, Any] = await request.json()
    alerts = body.get("alerts", [])
    
    processed = 0
    
    for alert in alerts:
        # Only process firing alerts
        if alert.get("status") != "firing":
            continue
            
        labels = alert.get("labels", {})
        alertname = labels.get("alertname", "")
        symbol = labels.get("symbol", "")
        severity = labels.get("severity", "warning")
        
        action_spec = ALERT_ACTIONS.get(alertname)
        if not action_spec:
            logger.warning("Unknown alert: %s", alertname)
            continue
            
        if not symbol:
            logger.warning("Alert %s has no symbol label", alertname)
            continue
            
        action_type, param_key, param_value = action_spec
        logger.info("Alert %s → %s(%s=%s) on %s", alertname, action_type, param_key, param_value, symbol)
        
        await dispatch_action(action_type, symbol, param_key, param_value, severity)
        processed += 1
    
    return {"status": "ok", "processed": processed}


async def dispatch_action(action_type: str, symbol: str, param_key: str, param_value: Any, severity: str):
    """Dispatch action to update ticker in the database."""
    import deps
    
    if action_type == "update_ticker" or action_type == "block_buy":
        # Update ticker directly in database
        update = {"$set": {param_key: param_value}}
        await deps.db.tickers.update_one({"symbol": symbol}, update)
        await deps.ws_manager.broadcast({
            "type": "TICKER_UPDATED",
            "symbol": symbol,
            param_key: param_value,
        })
        logger.info("Updated ticker %s: %s = %s", symbol, param_key, param_value)
        
    elif action_type == "adjust_bracket":
        # Get current ticker config
        ticker = await deps.db.tickers.find_one({"symbol": symbol})
        if not ticker:
            logger.warning("Ticker not found: %s", symbol)
            return
            
        # Apply delta to bracket
        current_buy = ticker.get("buy_offset", 0)
        current_stop = ticker.get("stop_offset", 0)
        
        if param_key == "buy_offset_delta":
            new_buy = current_buy + param_value
            await deps.db.tickers.update_one(
                {"symbol": symbol}, 
                {"$set": {"buy_offset": new_buy}}
            )
            await deps.ws_manager.broadcast({
                "type": "TICKER_UPDATED",
                "symbol": symbol,
                "buy_offset": new_buy,
            })
            logger.info("Adjusted %s buy_offset: %s → %s", symbol, current_buy, new_buy)
            
        elif param_key == "stop_offset_delta":
            new_stop = current_stop + param_value
            await deps.db.tickers.update_one(
                {"symbol": symbol}, 
                {"$set": {"stop_offset": new_stop}}
            )
            await deps.ws_manager.broadcast({
                "type": "TICKER_UPDATED", 
                "symbol": symbol,
                "stop_offset": new_stop,
            })
            logger.info("Adjusted %s stop_offset: %s → %s", symbol, current_stop, new_stop)
