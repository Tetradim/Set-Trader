"""Cross Bot Event Bus routes for Sentinel Pulse."""

from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, ValidationError

from bot_event_bus import EventBusStore, publish_event
from routes.edge import post_handoff
from routes.edge_contracts import PulseHandoffRequest, validate_api_key


router = APIRouter(
    prefix="/bus",
    tags=["cross-bot-event-bus"],
    dependencies=[Depends(validate_api_key)],
)

ACTION_ALIASES = {
    "downtrend_warning": "stop_buying",
    "market_downtrend_warning": "stop_buying",
    "stand_down": "stop_buying",
    "halt_new_buys": "stop_buying",
}


class EventRequest(BaseModel):
    event_type: str = Field(..., min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    source: str = "sentinel-pulse"
    target: str | None = None


class EdgeActionRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
    source: str = "sentinel-edge"
    target: str = "sentinel-pulse"


def _normalise_edge_action(payload: dict[str, Any]) -> PulseHandoffRequest:
    action = str(payload.get("action") or payload.get("type") or "stop_buying").strip().lower()
    action = ACTION_ALIASES.get(action, action)
    symbol = str(payload.get("symbol") or payload.get("ticker") or "GLOBAL").strip().upper()
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    metadata = {**metadata, "bus_payload": payload}
    idempotency_key = str(payload.get("idempotency_key") or f"bus:{symbol}:{action}:{uuid.uuid4()}")

    return PulseHandoffRequest(
        symbol=symbol,
        action=action,
        confidence=float(payload.get("confidence", 1.0)),
        reason=str(payload.get("reason") or "cross_bot_event_bus"),
        mode=str(payload.get("mode") or "paper"),
        orb_session=str(payload.get("orb_session") or "event_bus"),
        stop_type=payload.get("stop_type"),
        trailing_percent=payload.get("trailing_percent"),
        dca=payload.get("dca"),
        idempotency_key=idempotency_key,
        source="sentinel_edge",
        created_at=float(payload.get("created_at") or time.time()),
        metadata=metadata,
    )


@router.get("/events")
async def list_events(
    limit: int = Query(100, ge=1, le=1000),
    target: str | None = Query(None),
) -> dict[str, Any]:
    events = EventBusStore().list_events(limit=limit, target=target)
    return {"events": events, "count": len(events)}


@router.post("/events")
async def create_event(request: EventRequest) -> dict[str, Any]:
    event = publish_event(
        request.event_type,
        request.payload,
        source=request.source,
        target=request.target,
    )
    return {"event": event}


@router.post("/edge-actions")
async def apply_edge_action(request: EdgeActionRequest) -> dict[str, Any]:
    received = publish_event("edge.action.received", request.payload, source=request.source, target=request.target)
    try:
        handoff = _normalise_edge_action(request.payload)
    except ValidationError as exc:
        reason = "invalid_handoff"
        for error in exc.errors():
            if error.get("loc") == ("mode",):
                reason = "unsupported_mode"
                break
        response = {
            "accepted": False,
            "sent": False,
            "status": "rejected",
            "reason": reason,
            "symbol": str(request.payload.get("symbol") or request.payload.get("ticker") or "GLOBAL").upper(),
            "action": str(request.payload.get("action") or request.payload.get("type") or "stop_buying").lower(),
            "handoff_id": str(request.payload.get("idempotency_key") or ""),
            "message": str(exc),
        }
        rejected = publish_event(
            "edge.action.rejected",
            {
                "received_event_id": received["event_id"],
                "response": response,
            },
            source="sentinel-pulse",
            target=request.source,
        )
        return {"received": received, "rejected": rejected, "response": response}
    response = await post_handoff(handoff)
    applied = publish_event(
        "edge.action.applied",
        {
            "received_event_id": received["event_id"],
            "handoff": handoff.model_dump(mode="json"),
            "response": response,
        },
        source="sentinel-pulse",
        target=request.source,
    )
    return {"received": received, "applied": applied, "response": response}
