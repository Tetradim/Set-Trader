"""SLO and Alerting API routes.

Provides endpoints for SLO monitoring, alerts, and incident management.
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from auth import get_current_user, TokenData, require_roles, Role
from slo_alerting import (
    get_slo_tracker, get_slos, get_alerts, get_incidents,
    SLOTracker, AlertSeverity
)


router = APIRouter(prefix="/api/slo", tags=["slo"])


class UpdateSLORequest(BaseModel):
    name: str
    value: float


class IncidentActionRequest(BaseModel):
    incident_id: str
    action: str  # acknowledge or resolve
    user: str


@router.get("")
async def get_slo_status(
    current_user: TokenData = Depends(get_current_user)
):
    """Get all SLOs."""
    return {"slos": get_slos()}


@router.post("/metrics")
async def update_slo_metrics(
    request: UpdateSLORequest,
    current_user: TokenData = Depends(require_roles([Role.ADMIN]))
):
    """Update SLO metric value."""
    tracker = get_slo_tracker()
    tracker.update_slo(request.name, request.value)
    return {"status": "ok", "slo": request.name, "value": request.value}


@router.get("/alerts")
async def get_alert_rules(
    severity: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user)
):
    """Get all alert rules."""
    alerts = get_alerts()
    
    if severity:
        alerts = [a for a in alerts if a["severity"] == severity]
    
    return {"alerts": alerts}


@router.get("/incidents")
async def get_incident_list(
    status: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user)
):
    """Get all incidents."""
    incidents = get_incidents()
    
    if status:
        incidents = [i for i in incidents if i["status"] == status]
    
    return {"incidents": incidents}


@router.post("/incidents/action")
async def incident_action(
    request: IncidentActionRequest,
    current_user: TokenData = Depends(require_roles([Role.ADMIN, Role.RISK_OFFICER]))
):
    """Acknowledge or resolve an incident."""
    tracker = get_slo_tracker()
    
    if request.action == "acknowledge":
        success = tracker.acknowledge_incident(request.incident_id, current_user.username)
    elif request.action == "resolve":
        success = tracker.resolve_incident(request.incident_id, current_user.username)
    else:
        return {"success": False, "message": f"Unknown action: {request.action}"}
    
    return {
        "success": success,
        "incident_id": request.incident_id,
        "action": request.action,
        "user": current_user.username
    }


@router.get("/summary")
async def get_slo_summary(
    current_user: TokenData = Depends(get_current_user)
):
    """Get SLO summary with burn rates."""
    slos = get_slos()
    
    burned = sum(1 for slo in slos if slo.get("is_burned"))
    at_risk = sum(1 for slo in slos if slo.get("error_budget_remaining", 100) < 5)
    
    incidents = get_incidents()
    critical_incidents = len([i for i in incidents if i.get("severity") == "critical"])
    
    return {
        "total_slos": len(slos),
        "burned_slos": burned,
        "at_risk_slos": at_risk,
        "active_incidents": len(incidents),
        "critical_incidents": critical_incidents
    }


__all__ = ["router"]