"""Audit log, resilience monitoring, and system routes."""
from typing import Optional
from fastapi import APIRouter, Query

import deps
from audit_service import audit_service
from resilience import broker_resilience, BrokerResilienceConfig

router = APIRouter(tags=["System"])


# ---------------------------------------------------------------------------
# Audit Logs
# ---------------------------------------------------------------------------

@router.get("/audit-logs")
async def get_audit_logs(
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    broker_id: Optional[str] = Query(None, description="Filter by broker"),
    success: Optional[bool] = Query(None, description="Filter by success status"),
    limit: int = Query(100, ge=1, le=1000),
    skip: int = Query(0, ge=0),
):
    """Get audit logs with optional filters."""
    logs = await audit_service.get_logs(
        event_type=event_type,
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
