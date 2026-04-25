"""Operations API routes.

Provides endpoints for service health monitoring, incidents, and runbooks.
"""
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from auth import get_current_user, TokenData, require_roles, Role


router = APIRouter(prefix="/api/ops", tags=["ops"])


# In-memory storage
_services_db = []
_incidents_db = []
_runbooks_db = []


class Service(BaseModel):
    service_id: str
    name: str
    status: str
    uptime: float
    last_check: str
    dependencies: List[str] = []
    metrics: dict = {}


class Incident(BaseModel):
    incident_id: str
    severity: str
    title: str
    description: str
    status: str
    service: str
    created_at: str
    updated_at: str
    owner: str


class Runbook(BaseModel):
    runbook_id: str
    title: str
    service: str
    description: str
    steps: List[str] = []


@router.get("/services", response_model=List[Service])
async def get_services(
    current_user: TokenData = Depends(get_current_user)
):
    """Get all services and their health status."""
    return _services_db or [
        {
            "service_id": "api",
            "name": "API Server",
            "status": "healthy",
            "uptime": 99.99,
            "last_check": datetime.utcnow().isoformat(),
            "dependencies": ["db", "cache"],
            "metrics": {"requests_per_sec": 150, "latency_ms": 25}
        },
        {
            "service_id": "engine",
            "name": "Trading Engine",
            "status": "healthy",
            "uptime": 99.95,
            "last_check": datetime.utcnow().isoformat(),
            "dependencies": ["api", "broker"],
            "metrics": {"orders_per_min": 10, "fills_per_min": 8}
        },
        {
            "service_id": "ws",
            "name": "WebSocket",
            "status": "healthy",
            "uptime": 99.98,
            "last_check": datetime.utcnow().isoformat(),
            "dependencies": ["api"],
            "metrics": {"connections": 25, "messages_per_sec": 50}
        },
        {
            "service_id": "db",
            "name": "Database",
            "status": "healthy",
            "uptime": 99.99,
            "last_check": datetime.utcnow().isoformat(),
            "dependencies": [],
            "metrics": {"connections": 10, "query_latency_ms": 5}
        }
    ]


@router.get("/incidents", response_model=List[Incident])
async def get_incidents(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user)
):
    """Get incidents."""
    incidents = _incidents_db or [
        {
            "incident_id": "INC001",
            "severity": "warning",
            "title": "High latency detected",
            "description": "API latency above 100ms for the last 5 minutes",
            "status": "investigating",
            "service": "api",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "owner": "oncall"
        }
    ]
    
    if status:
        incidents = [i for i in incidents if i["status"] == status]
    if severity:
        incidents = [i for i in incidents if i["severity"] == severity]
    
    return incidents


@router.get("/runbooks", response_model=List[Runbook])
async def get_runbooks(
    current_user: TokenData = Depends(get_current_user)
):
    """Get runbooks."""
    return _runbooks_db or [
        {
            "runbook_id": "RB001",
            "title": "Broker reconnection procedure",
            "service": "broker",
            "description": "Steps to reconnect a broker after disconnection",
            "steps": [
                "1. Check broker status in dashboard",
                "2. Verify credentials are valid",
                "3. Restart broker connection",
                "4. Verify positions sync"
            ]
        },
        {
            "runbook_id": "RB002",
            "title": "Database backup procedure",
            "service": "db",
            "description": "Steps to perform a database backup",
            "steps": [
                "1. Stop trading engine",
                "2. Create backup snapshot",
                "3. Verify backup integrity",
                "4. Restart trading engine"
            ]
        }
    ]


@router.post("/incidents")
async def create_incident(
    severity: str,
    title: str,
    description: str,
    service: str,
    current_user: TokenData = Depends(require_roles([Role.ADMIN, Role.RISK_OFFICER]))
):
    """Create a new incident."""
    incident = {
        "incident_id": f"INC{len(_incidents_db) + 1:03d}",
        "severity": severity,
        "title": title,
        "description": description,
        "status": "active",
        "service": service,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "owner": current_user.username
    }
    _incidents_db.append(incident)
    return incident


@router.post("/incidents/{incident_id}/resolve")
async def resolve_incident(
    incident_id: str,
    current_user: TokenData = Depends(require_roles([Role.ADMIN, Role.RISK_OFFICER]))
):
    """Resolve an incident."""
    for incident in _incidents_db:
        if incident["incident_id"] == incident_id:
            incident["status"] = "resolved"
            incident["updated_at"] = datetime.utcnow().isoformat()
            return incident
    return {"error": "Incident not found"}


__all__ = ["router"]