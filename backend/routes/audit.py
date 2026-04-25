"""Audit API routes.

Provides endpoints for immutable audit logs and compliance reporting.
"""
from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from auth import get_current_user, TokenData, require_roles, Role
import deps


router = APIRouter(prefix="/api/audit", tags=["audit"])


# In-memory audit storage (replace with immutable store in production)
_events_db = []


class AuditEvent(BaseModel):
    event_id: str
    event_type: str
    timestamp: str
    user_id: str
    username: str
    action: str
    details: dict
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class AuditSummary(BaseModel):
    total_events: int
    unique_users: int
    events_today: int
    high_risk_events: int


@router.get("/events", response_model=List[AuditEvent])
async def get_events(
    limit: int = Query(200, ge=1, le=1000),
    event_type: Optional[str] = None,
    user_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user)
):
    """Get audit events."""
    events = _events_db
    
    if event_type:
        events = [e for e in events if e["event_type"] == event_type]
    if user_id:
        events = [e for e in events if e["user_id"] == user_id]
    if start_date:
        events = [e for e in events if e["timestamp"] >= start_date]
    if end_date:
        events = [e for e in events if e["timestamp"] <= end_date]
    
    # Sort by timestamp descending
    events = sorted(events, key=lambda x: x["timestamp"], reverse=True)
    
    return events[:limit]


@router.get("/summary", response_model=AuditSummary)
async def get_summary(
    current_user: TokenData = Depends(get_current_user)
):
    """Get audit summary."""
    events = _events_db
    
    today = datetime.utcnow().date().isoformat()
    events_today = len([e for e in events if e["timestamp"].startswith(today)])
    
    unique_users = len(set(e["user_id"] for e in events))
    
    high_risk_types = ["MANUAL_SELL", "SETTING_CHANGED", "BROKER_CONNECTED", "BROKER_DISCONNECTED"]
    high_risk = len([e for e in events if e["event_type"] in high_risk_types])
    
    return AuditSummary(
        total_events=len(events),
        unique_users=unique_users,
        events_today=events_today,
        high_risk_events=high_risk
    )


@router.get("/export")
async def export_audit_logs(
    format: str = Query("csv", regex="^(csv|json|pdf)$"),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: TokenData = Depends(require_roles([Role.ADMIN, Role.RISK_OFFICER]))
):
    """Export audit logs in various formats."""
    events = _events_db
    
    if start_date:
        events = [e for e in events if e["timestamp"] >= start_date]
    if end_date:
        events = [e for e in events if e["timestamp"] <= end_date]
    
    # In production, this would generate actual files
    return {
        "download_url": f"/api/audit/downloads/audit_export_{datetime.utcnow().isoformat()}.{format}",
        "format": format,
        "record_count": len(events),
        "generated_at": datetime.utcnow().isoformat()
    }


# Helper function to log events from anywhere in the application
def log_event(
    event_type: str,
    action: str,
    user_id: str,
    username: str,
    details: dict,
    ip_address: str = None,
    user_agent: str = None
):
    """Log an audit event."""
    event = {
        "event_id": f"EVT{len(_events_db) + 1:010d}",
        "event_type": event_type,
        "timestamp": datetime.utcnow().isoformat(),
        "user_id": user_id,
        "username": username,
        "action": action,
        "details": details,
        "ip_address": ip_address,
        "user_agent": user_agent
    }
    _events_db.append(event)
    return event


# Pre-populate with some sample events for demo
def init_sample_audit_events():
    """Initialize sample audit events for demo."""
    sample_events = [
        {
            "event_id": "EVT0000000001",
            "event_type": "LOGIN",
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": "admin",
            "username": "admin",
            "action": "User logged in",
            "details": {"method": "password"},
            "ip_address": "192.168.1.1",
            "user_agent": "Mozilla/5.0"
        },
        {
            "event_id": "EVT0000000002",
            "event_type": "SETTING_CHANGED",
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": "admin",
            "username": "admin",
            "action": "Updated trading mode",
            "details": {"key": "trading_mode", "old_value": "paper", "new_value": "live"},
            "ip_address": "192.168.1.1",
            "user_agent": "Mozilla/5.0"
        },
        {
            "event_id": "EVT0000000003",
            "event_type": "TICKER_CREATED",
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": "admin",
            "username": "admin",
            "action": "Added ticker",
            "details": {"symbol": "AAPL", "broker": "IB"},
            "ip_address": "192.168.1.1",
            "user_agent": "Mozilla/5.0"
        },
        {
            "event_id": "EVT0000000004",
            "event_type": "BUY_EXECUTED",
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": "system",
            "username": "system",
            "action": "Buy order executed",
            "details": {"symbol": "AAPL", "quantity": 100, "price": 150.00},
            "ip_address": None,
            "user_agent": None
        },
        {
            "event_id": "EVT0000000005",
            "event_type": "BROKER_CONNECTED",
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": "system",
            "username": "system",
            "action": "Broker connected",
            "details": {"broker": "IB", "status": "connected"},
            "ip_address": None,
            "user_agent": None
        }
    ]
    
    for event in sample_events:
        _events_db.append(event)


# Initialize sample events
init_sample_audit_events()


__all__ = ["router", "log_event"]