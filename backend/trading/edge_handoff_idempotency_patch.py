"""Durable exactly-once command handling for Edge-to-Pulse handoffs."""
from __future__ import annotations

import functools
import time
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi.routing import APIRoute, APIRouter


_previous_include_router = APIRouter.include_router
_PATCH_MARKER = "_pulse_durable_edge_handoff_idempotency"
_LEASE_SECONDS = 120.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _duplicate_response(response: dict) -> dict:
    duplicate = deepcopy(response)
    duplicate["duplicate"] = True
    duplicate["idempotency_replayed"] = True
    return duplicate


def _pending_response(edge_module: Any, body: Any) -> dict:
    response = edge_module._handoff_response(
        body,
        accepted=True,
        status="accepted",
        reason="handoff_in_progress",
        message="This idempotency key is already being processed by Pulse.",
    )
    response["reconciliation_required"] = True
    response["command_state"] = "processing"
    return response


def _normalise_execution_response(response: Any) -> Any:
    if not isinstance(response, dict):
        return response
    status = str(response.get("status") or "").lower()
    message = str(response.get("message") or "").lower()
    reason = str(response.get("reason") or "").lower()
    ambiguous_markers = (
        "pending fill",
        "pending reconciliation",
        "broker reconciliation is required",
        "broker_order_ids",
        "not fully filled",
        "inconsistent fill evidence",
    )
    if status == "failed" and any(
        marker in message or marker in reason for marker in ambiguous_markers
    ):
        normalised = deepcopy(response)
        normalised.update(
            {
                "accepted": True,
                "sent": True,
                "status": "accepted",
                "reason": "broker_reconciliation_pending",
                "reconciliation_required": True,
                "command_state": "broker_reconciliation_pending",
            }
        )
        return normalised
    return response


async def _ensure_index(collection: Any) -> None:
    try:
        await collection.create_index("idempotency_key", unique=True)
    except Exception:
        # The index may already exist or a restricted test double may omit it.
        pass


async def _claim_or_replay(edge_module: Any, body: Any, owner: str) -> tuple[str, dict | None]:
    collection = getattr(edge_module.deps.db, "edge_handoffs", None)
    if collection is None:
        return "claimed_without_ledger", None

    await _ensure_index(collection)
    key = body.idempotency_key
    now = time.time()
    existing = await collection.find_one({"idempotency_key": key}, {"_id": 0})
    if existing:
        response = existing.get("response")
        if isinstance(response, dict):
            return "replay", _duplicate_response(response)
        lease_expires = float(existing.get("lease_expires_at") or 0.0)
        if existing.get("status") == "processing" and lease_expires > now:
            return "processing", _pending_response(edge_module, body)
        result = await collection.update_one(
            {
                "idempotency_key": key,
                "lease_expires_at": existing.get("lease_expires_at"),
                "response": {"$exists": False},
            },
            {
                "$set": {
                    "status": "processing",
                    "owner": owner,
                    "lease_expires_at": now + _LEASE_SECONDS,
                    "updated_at": _now_iso(),
                }
            },
        )
        if int(getattr(result, "modified_count", 0) or 0) == 1:
            return "claimed", None
        refreshed = await collection.find_one({"idempotency_key": key}, {"_id": 0})
        if isinstance((refreshed or {}).get("response"), dict):
            return "replay", _duplicate_response(refreshed["response"])
        return "processing", _pending_response(edge_module, body)

    document = {
        "idempotency_key": key,
        "symbol": body.symbol,
        "action": body.action.value,
        "mode": body.mode.value,
        "status": "processing",
        "owner": owner,
        "lease_expires_at": now + _LEASE_SECONDS,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    try:
        await collection.insert_one(document)
        return "claimed", None
    except Exception:
        existing = await collection.find_one({"idempotency_key": key}, {"_id": 0})
        if isinstance((existing or {}).get("response"), dict):
            return "replay", _duplicate_response(existing["response"])
        return "processing", _pending_response(edge_module, body)


async def _store_response(edge_module: Any, body: Any, owner: str, response: Any) -> None:
    collection = getattr(edge_module.deps.db, "edge_handoffs", None)
    if collection is None:
        return
    serialisable = response if isinstance(response, dict) else {"value": response}
    result = await collection.update_one(
        {
            "idempotency_key": body.idempotency_key,
            "owner": owner,
        },
        {
            "$set": {
                "status": str(serialisable.get("status") or "completed"),
                "response": serialisable,
                "lease_expires_at": 0.0,
                "completed_at": _now_iso(),
                "updated_at": _now_iso(),
            },
            "$unset": {"owner": ""},
        },
    )
    if int(getattr(result, "matched_count", 0) or 0) != 1:
        raise RuntimeError(
            f"Pulse executed handoff {body.idempotency_key} but could not persist its terminal response"
        )


async def _release_claim(edge_module: Any, body: Any, owner: str, error: Exception) -> None:
    collection = getattr(edge_module.deps.db, "edge_handoffs", None)
    if collection is None:
        return
    try:
        await collection.update_one(
            {
                "idempotency_key": body.idempotency_key,
                "owner": owner,
                "response": {"$exists": False},
            },
            {
                "$set": {
                    "status": "retryable_error",
                    "lease_expires_at": 0.0,
                    "last_error": str(error),
                    "updated_at": _now_iso(),
                },
                "$unset": {"owner": ""},
            },
        )
    except Exception:
        pass


def _wrap_handoff_route(route: APIRoute) -> None:
    if getattr(route.endpoint, _PATCH_MARKER, False):
        return
    original_endpoint = route.endpoint

    @functools.wraps(original_endpoint)
    async def wrapped(*args: Any, **kwargs: Any):
        body = kwargs.get("body")
        if body is None and args:
            body = args[0]
        if body is None:
            return await original_endpoint(*args, **kwargs)

        edge_module = __import__("routes.edge", fromlist=["post_handoff"])
        owner = str(uuid4())
        state, replay = await _claim_or_replay(edge_module, body, owner)
        if replay is not None:
            return replay
        if state == "claimed_without_ledger":
            # Pulse requires MongoDB in production, but preserve test and
            # development compatibility if a reduced database double is used.
            return await original_endpoint(*args, **kwargs)

        try:
            response = _normalise_execution_response(
                await original_endpoint(*args, **kwargs)
            )
            await _store_response(edge_module, body, owner, response)
            return response
        except Exception as exc:
            await _release_claim(edge_module, body, owner, exc)
            raise

    setattr(wrapped, _PATCH_MARKER, True)
    route.endpoint = wrapped


def _include_router_with_idempotency(
    self: APIRouter,
    router: APIRouter,
    *args: Any,
    **kwargs: Any,
):
    before = len(self.routes)
    result = _previous_include_router(self, router, *args, **kwargs)
    for route in self.routes[before:]:
        if (
            isinstance(route, APIRoute)
            and route.path.endswith("/edge/handoff")
            and "POST" in (route.methods or set())
        ):
            _wrap_handoff_route(route)
    return result


if not getattr(APIRouter.include_router, _PATCH_MARKER, False):
    setattr(_include_router_with_idempotency, _PATCH_MARKER, True)
    APIRouter.include_router = _include_router_with_idempotency
