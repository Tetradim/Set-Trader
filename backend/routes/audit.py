"""Audit API routes backed by the audit log collection."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from audit_service import audit_service
from auth import Role, TokenData, get_current_user, require_roles


router = APIRouter(prefix="/audit", tags=["audit"])


class AuditEvent(BaseModel):
    timestamp: str
    event_type: str
    details: dict = {}
    symbol: Optional[str] = None
    broker_id: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None


class AuditSummary(BaseModel):
    total_events: int
    unique_users: int
    events_today: int
    high_risk_events: int


def _date_in_range(timestamp: str, start_date: Optional[str], end_date: Optional[str]) -> bool:
    if start_date and timestamp < start_date:
        return False
    if end_date and timestamp > end_date:
        return False
    return True


async def _load_events(
    limit: int,
    event_type: Optional[str] = None,
    user_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list[dict]:
    events = await audit_service.get_logs(event_type=event_type, limit=limit)
    filtered = []
    for event in events:
        details = event.get("details") or {}
        event_user_id = details.get("user_id") or event.get("user_id")
        if user_id and event_user_id != user_id:
            continue
        if not _date_in_range(event.get("timestamp", ""), start_date, end_date):
            continue
        filtered.append(event)
    return filtered[:limit]


@router.get("/events", response_model=list[AuditEvent])
async def get_events(
    limit: int = Query(200, ge=1, le=1000),
    event_type: Optional[str] = None,
    user_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user),
):
    """Get audit events."""
    return await _load_events(limit, event_type, user_id, start_date, end_date)


@router.get("/summary", response_model=AuditSummary)
async def get_summary(current_user: TokenData = Depends(get_current_user)):
    """Get audit summary."""
    events = await audit_service.get_logs(limit=1000)
    today = datetime.now(timezone.utc).date().isoformat()
    high_risk_types = {"MANUAL_SELL", "SETTING_CHANGED", "BROKER_CONNECTED", "BROKER_DISCONNECTED"}

    users = set()
    events_today = 0
    high_risk = 0
    for event in events:
        details = event.get("details") or {}
        event_user_id = details.get("user_id") or event.get("user_id")
        if event_user_id:
            users.add(event_user_id)
        if event.get("timestamp", "").startswith(today):
            events_today += 1
        if event.get("event_type") in high_risk_types:
            high_risk += 1

    return AuditSummary(
        total_events=len(events),
        unique_users=len(users),
        events_today=events_today,
        high_risk_events=high_risk,
    )


@router.get("/export")
async def export_audit_logs(
    format: str = Query("json", pattern="^(csv|json)$"),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: TokenData = Depends(require_roles([Role.ADMIN, Role.RISK_OFFICER])),
):
    """Export audit log records."""
    events = await _load_events(1000, start_date=start_date, end_date=end_date)
    if format == "csv":
        return {
            "format": "csv",
            "columns": ["timestamp", "event_type", "symbol", "broker_id", "success", "error_message", "details"],
            "rows": [
                [
                    event.get("timestamp"),
                    event.get("event_type"),
                    event.get("symbol"),
                    event.get("broker_id"),
                    event.get("success", True),
                    event.get("error_message"),
                    event.get("details", {}),
                ]
                for event in events
            ],
            "record_count": len(events),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    return {
        "format": "json",
        "records": events,
        "record_count": len(events),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


async def log_event(
    event_type: str,
    action: str,
    user_id: str,
    username: str,
    details: dict,
    ip_address: str = None,
    user_agent: str = None,
):
    """Compatibility helper for older callers."""
    event_details = {
        **details,
        "action": action,
        "user_id": user_id,
        "username": username,
        "ip_address": ip_address,
        "user_agent": user_agent,
    }
    from audit_service import AuditEventType

    await audit_service.log(AuditEventType(event_type), event_details)


__all__ = ["router", "log_event"]
