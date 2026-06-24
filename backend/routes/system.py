"""Audit log, resilience monitoring, and system routes."""
import os
from typing import Optional, List
from fastapi import APIRouter, Query

import deps
from audit_service import audit_service
from resilience import broker_resilience, BrokerResilienceConfig

router = APIRouter(tags=["System"])

LIVE_TRADING_OPERATOR_SECRET_ENV = "SENTINEL_PULSE_LIVE_TRADING_OPERATOR_SECRET"


def _preflight_item(check_id: str, label: str, status: str, detail: str, action: str = "") -> dict:
    return {
        "id": check_id,
        "label": label,
        "status": status,
        "detail": detail,
        "action": action,
    }


@router.get("/preflight")
async def get_release_preflight():
    """Return beta release readiness checks before users start trading."""
    checks = []

    user_count = await deps.db.users.count_documents({})
    checks.append(_preflight_item(
        "admin_user",
        "Admin account",
        "pass" if user_count > 0 else "fail",
        f"{user_count} user account(s) configured" if user_count else "No admin account has been created",
        "Create the first admin account from the sign-in screen.",
    ))

    balance_doc = await deps.db.settings.find_one({"key": "account_balance"}, {"_id": 0})
    account_balance = float(balance_doc.get("value", 0) if balance_doc else 0)
    tickers = await deps.db.tickers.find({}, {"_id": 0}).to_list(500)
    enabled_tickers = [ticker for ticker in tickers if ticker.get("enabled", True)]
    allocated = round(sum(float(ticker.get("base_power", 0) or 0) for ticker in tickers), 2)

    checks.append(_preflight_item(
        "account_balance",
        "Account balance",
        "pass" if account_balance > 0 else "fail",
        f"${account_balance:,.2f} configured" if account_balance > 0 else "No account balance configured",
        "Set total account balance in Settings.",
    ))
    checks.append(_preflight_item(
        "allocation",
        "Capital allocation",
        "pass" if account_balance > 0 and allocated <= account_balance else "fail",
        f"${allocated:,.2f} allocated of ${account_balance:,.2f}",
        "Reduce ticker buy power or increase account balance.",
    ))
    checks.append(_preflight_item(
        "tickers",
        "Enabled tickers",
        "pass" if enabled_tickers else "fail",
        f"{len(enabled_tickers)} enabled of {len(tickers)} configured",
        "Add or enable at least one ticker.",
    ))

    connected_brokers = len(getattr(deps.broker_mgr, "_adapters", {}))
    checks.append(_preflight_item(
        "brokers",
        "Broker connection",
        "pass" if connected_brokers else "warn",
        f"{connected_brokers} broker adapter(s) connected",
        "Connect a broker before live trading. Paper-only testing can continue without one.",
    ))

    has_price_source = bool(deps.YF_AVAILABLE or connected_brokers)
    checks.append(_preflight_item(
        "price_source",
        "Price source",
        "pass" if has_price_source else "fail",
        "Broker feed or yfinance is available" if has_price_source else "No broker feed or yfinance source is available",
        "Install/enable yfinance or connect a broker feed.",
    ))

    drawdown_doc = await deps.db.settings.find_one({"key": "global_daily_drawdown"}, {"_id": 0})
    global_daily_drawdown = drawdown_doc.get("value", {"enabled": False, "limit": 3, "type": "percent"}) if drawdown_doc else {"enabled": False, "limit": 3, "type": "percent"}
    checks.append(_preflight_item(
        "global_daily_drawdown",
        "Global daily drawdown",
        "pass" if global_daily_drawdown.get("enabled") else "warn",
        (
            f"Enabled at {global_daily_drawdown.get('limit', 3)}"
            f"{'%' if global_daily_drawdown.get('type') == 'percent' else ' USD'}"
        ) if global_daily_drawdown.get("enabled") else "Portfolio-level daily drawdown stop is disabled",
        "Enable the global daily drawdown circuit breaker in Settings.",
    ))

    edge_key_doc = await deps.db.settings.find_one({"key": "edge_api_key"}, {"_id": 0})
    edge_api_key = edge_key_doc.get("value", "") if edge_key_doc else ""
    checks.append(_preflight_item(
        "edge_api_key",
        "Edge API key",
        "pass",
        "Configured" if edge_api_key else "Edge REST integrations disabled",
        "Set edge_api_key only when connecting Sentinel Edge.",
    ))

    checks.append(_preflight_item(
        "alert_webhook_secret",
        "Alert webhook secret",
        "pass" if os.getenv("ALERT_WEBHOOK_SECRET") else "warn",
        "Configured" if os.getenv("ALERT_WEBHOOK_SECRET") else "Not configured",
        "Set ALERT_WEBHOOK_SECRET before connecting Alertmanager.",
    ))

    live_operator_secret_configured = bool(os.getenv(LIVE_TRADING_OPERATOR_SECRET_ENV, "").strip())
    checks.append(_preflight_item(
        "live_trading_operator_secret",
        "Live trading operator secret",
        "pass" if live_operator_secret_configured else "warn",
        "Configured" if live_operator_secret_configured else "Not configured; live mode promotion is disabled",
        f"Set {LIVE_TRADING_OPERATOR_SECRET_ENV} before any real-money cutover.",
    ))

    checks.append(_preflight_item(
        "telegram",
        "Telegram alerts",
        "pass" if deps.telegram_service.running else "warn",
        "Connected" if deps.telegram_service.running else "Not connected",
        "Configure Telegram in Settings if beta testers need push alerts.",
    ))

    counts = {
        "pass": sum(1 for check in checks if check["status"] == "pass"),
        "warn": sum(1 for check in checks if check["status"] == "warn"),
        "fail": sum(1 for check in checks if check["status"] == "fail"),
    }
    ready_to_trade = counts["fail"] == 0
    return {
        "ready_to_trade": ready_to_trade,
        "summary": counts,
        "checks": checks,
        "context": {
            "running": deps.engine.running,
            "paused": deps.engine.paused,
            "market_open": deps.engine.is_market_open(),
            "trading_mode": deps.engine.get_trading_mode(),
            "account_balance": round(account_balance, 2),
            "allocated": allocated,
            "available": round(account_balance - allocated, 2),
            "enabled_tickers": len(enabled_tickers),
            "connected_brokers": connected_brokers,
            "global_daily_drawdown": global_daily_drawdown,
        },
    }


# ---------------------------------------------------------------------------
# Audit Logs
# ---------------------------------------------------------------------------

@router.get("/audit-logs")
async def get_audit_logs(
    event_type: Optional[List[str]] = Query(None, description="Filter by one or more event types"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    broker_id: Optional[str] = Query(None, description="Filter by broker"),
    success: Optional[bool] = Query(None, description="Filter by success status"),
    limit: int = Query(100, ge=1, le=1000),
    skip: int = Query(0, ge=0),
):
    """Get audit logs with optional filters. event_type may be repeated for OR matching."""
    logs = await audit_service.get_logs(
        event_types=event_type,   # list or None
        symbol=symbol,
        broker_id=broker_id,
        success=success,
        limit=limit,
        skip=skip,
    )
    return {"logs": logs, "count": len(logs)}


@router.get("/audit-logs/event-types")
async def get_event_types():
    """Get list of all audit event types."""
    from audit_service import AuditEventType
    return {"event_types": [e.value for e in AuditEventType]}


# ---------------------------------------------------------------------------
# Resilience — rate limits + circuit breakers (replaces legacy rate_limiter)
# ---------------------------------------------------------------------------

@router.get("/rate-limits")
async def get_rate_limit_status():
    """Get resilience status (token-bucket rate limits + circuit breakers) for all brokers."""
    return {"brokers": broker_resilience.get_all_statuses()}


@router.get("/rate-limits/{broker_id}")
async def get_broker_rate_limit(broker_id: str):
    """Get resilience status for a specific broker."""
    return broker_resilience.get_status(broker_id)


@router.post("/rate-limits/{broker_id}")
async def set_broker_rate_limit(
    broker_id: str,
    max_rps: float = Query(10.0, ge=0.1, le=500, description="Max requests per second (token bucket)"),
    burst: int = Query(20, ge=1, le=200, description="Burst capacity"),
    cooldown_ms: int = Query(100, ge=0, le=5000, description="Min ms between requests"),
    failure_threshold: int = Query(5, ge=1, le=50, description="Failures in window to trip circuit"),
    failure_window_seconds: int = Query(60, ge=10, le=600, description="Sliding window for failure counting"),
    recovery_timeout_seconds: int = Query(60, ge=10, le=600, description="How long circuit stays OPEN"),
    half_open_max_calls: int = Query(2, ge=1, le=10, description="Test calls in HALF_OPEN state"),
    skip_during_opening: bool = Query(False, description="Skip this broker during market opening window"),
):
    """Set resilience configuration for a broker and persist to database."""
    old_cfg = broker_resilience.get_config(broker_id)
    config = BrokerResilienceConfig(
        max_rps=max_rps,
        burst=burst,
        cooldown_ms=cooldown_ms,
        failure_threshold=failure_threshold,
        failure_window_seconds=failure_window_seconds,
        recovery_timeout_seconds=recovery_timeout_seconds,
        half_open_max_calls=half_open_max_calls,
        skip_during_opening=skip_during_opening,
    )
    broker_resilience.set_config(broker_id, config)
    await broker_resilience.save_config()

    await audit_service.log_setting_change(
        f"resilience_{broker_id}",
        vars(old_cfg),
        vars(config),
    )

    return {"ok": True, "config": broker_resilience.get_status(broker_id)}


@router.post("/circuit/{broker_id}/reset")
async def reset_circuit_breaker(broker_id: str):
    """Manually reset a tripped circuit breaker back to CLOSED."""
    await broker_resilience.reset_circuit(broker_id)
    return {"ok": True, "broker_id": broker_id, "circuit_state": "closed"}


# ---------------------------------------------------------------------------
# Price sources
# ---------------------------------------------------------------------------

@router.get("/price-sources")
async def get_price_sources():
    """Get current price sources for all symbols."""
    return {
        "prefer_broker_feeds": deps.price_service.prefer_broker_feeds,
        "sources": deps.price_service.get_all_sources(),
    }


@router.post("/price-sources/toggle")
async def toggle_price_source(prefer_broker: bool = Query(...)):
    """Toggle between broker feeds and yfinance for price data."""
    old_value = deps.price_service.prefer_broker_feeds
    deps.price_service.set_prefer_broker_feeds(prefer_broker)

    await deps.db.settings.update_one(
        {"key": "prefer_broker_feeds"},
        {"$set": {"value": prefer_broker}},
        upsert=True,
    )

    await audit_service.log_setting_change(
        "prefer_broker_feeds",
        old_value,
        prefer_broker,
    )

    return {
        "ok": True,
        "prefer_broker_feeds": prefer_broker,
        "message": f"Price source set to: {'Broker feeds (with yfinance fallback)' if prefer_broker else 'yfinance only'}",
    }
