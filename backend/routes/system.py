"""Audit log and system monitoring routes."""
from typing import Optional
from fastapi import APIRouter, Query

import deps
from audit_service import audit_service
from rate_limiter import rate_limiter, BrokerRateLimitConfig

router = APIRouter(tags=["System"])


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


@router.get("/rate-limits")
async def get_rate_limit_status():
    """Get rate limit and circuit breaker status for all brokers."""
    return {"brokers": rate_limiter.get_all_statuses()}


@router.get("/rate-limits/{broker_id}")
async def get_broker_rate_limit(broker_id: str):
    """Get rate limit status for a specific broker."""
    return rate_limiter.get_status(broker_id)


@router.post("/rate-limits/{broker_id}")
async def set_broker_rate_limit(
    broker_id: str,
    requests_per_minute: int = Query(60, ge=1, le=1000),
    requests_per_second: int = Query(5, ge=1, le=100),
    burst_limit: int = Query(10, ge=1, le=100),
    failure_threshold: int = Query(5, ge=1, le=50),
    recovery_timeout_seconds: int = Query(60, ge=10, le=600),
):
    """Set custom rate limit configuration for a broker."""
    config = BrokerRateLimitConfig(
        requests_per_minute=requests_per_minute,
        requests_per_second=requests_per_second,
        burst_limit=burst_limit,
        failure_threshold=failure_threshold,
        recovery_timeout_seconds=recovery_timeout_seconds,
    )
    rate_limiter.set_config(broker_id, config)
    
    # Save to database for persistence
    await deps.db.settings.update_one(
        {"key": f"rate_limit_{broker_id}"},
        {"$set": {"value": {
            "requests_per_minute": requests_per_minute,
            "requests_per_second": requests_per_second,
            "burst_limit": burst_limit,
            "failure_threshold": failure_threshold,
            "recovery_timeout_seconds": recovery_timeout_seconds,
        }}},
        upsert=True,
    )
    
    await audit_service.log_setting_change(
        f"rate_limit_{broker_id}",
        None,
        config.__dict__,
    )
    
    return {"ok": True, "config": rate_limiter.get_status(broker_id)}


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
    
    # Save to database
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
