"""Operations API routes for service health, incidents, and runbooks."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pymongo import ReturnDocument
from pydantic import BaseModel

import deps
from auth import Role, TokenData, get_current_user, require_roles


router = APIRouter(prefix="/ops", tags=["ops"])


class Service(BaseModel):
    service_id: str
    name: str
    status: str
    uptime: float
    last_check: str
    dependencies: list[str] = []
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
    steps: list[str] = []


async def _database_status() -> str:
    try:
        await deps.db.command("ping")
        return "healthy"
    except Exception:
        return "unhealthy"


@router.get("/services", response_model=list[Service])
async def get_services(current_user: TokenData = Depends(get_current_user)):
    """Get live service health."""
    now = datetime.now(timezone.utc).isoformat()
    database_status = await _database_status()
    websocket_connections = len(getattr(deps.ws_manager, "active_connections", []) or []) if deps.ws_manager else 0

    engine_running = bool(getattr(deps.engine, "running", False)) if deps.engine else False
    engine_paused = bool(getattr(deps.engine, "paused", True)) if deps.engine else True

    return [
        Service(
            service_id="api",
            name="API Server",
            status="healthy",
            uptime=0,
            last_check=now,
            dependencies=["db"],
            metrics={},
        ),
        Service(
            service_id="db",
            name="Database",
            status=database_status,
            uptime=0,
            last_check=now,
            dependencies=[],
            metrics={},
        ),
        Service(
            service_id="engine",
            name="Trading Engine",
            status="running" if engine_running and not engine_paused else "paused",
            uptime=0,
            last_check=now,
            dependencies=["db", "broker"],
            metrics={
                "positions": len(getattr(deps.engine, "_positions", {}) or {}) if deps.engine else 0,
                "pending_sells": len(getattr(deps.engine, "_pending_sells", {}) or {}) if deps.engine else 0,
            },
        ),
        Service(
            service_id="ws",
            name="WebSocket",
            status="healthy",
            uptime=0,
            last_check=now,
            dependencies=["api"],
            metrics={"connections": websocket_connections},
        ),
    ]


@router.get("/incidents", response_model=list[Incident])
async def get_incidents(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user),
):
    """Get incidents from the database."""
    query = {}
    if status:
        query["status"] = status
    if severity:
        query["severity"] = severity
    return await deps.db.incidents.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)


@router.get("/runbooks", response_model=list[Runbook])
async def get_runbooks(current_user: TokenData = Depends(get_current_user)):
    """Get configured runbooks."""
    return await deps.db.runbooks.find({}, {"_id": 0}).sort("title", 1).to_list(200)


@router.post("/incidents", response_model=Incident)
async def create_incident(
    severity: str,
    title: str,
    description: str,
    service: str,
    current_user: TokenData = Depends(require_roles([Role.ADMIN, Role.RISK_OFFICER])),
):
    """Create a new incident."""
    now = datetime.now(timezone.utc).isoformat()
    count = await deps.db.incidents.count_documents({})
    incident = {
        "incident_id": f"INC{count + 1:06d}",
        "severity": severity,
        "title": title,
        "description": description,
        "status": "active",
        "service": service,
        "created_at": now,
        "updated_at": now,
        "owner": current_user.username,
    }
    await deps.db.incidents.insert_one(incident)
    return incident


@router.post("/incidents/{incident_id}/resolve", response_model=Incident)
async def resolve_incident(
    incident_id: str,
    current_user: TokenData = Depends(require_roles([Role.ADMIN, Role.RISK_OFFICER])),
):
    """Resolve an incident."""
    now = datetime.now(timezone.utc).isoformat()
    result = await deps.db.incidents.find_one_and_update(
        {"incident_id": incident_id},
        {"$set": {"status": "resolved", "updated_at": now, "owner": current_user.username}},
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Incident not found")
    return result


__all__ = ["router"]
