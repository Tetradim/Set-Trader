"""Runtime integration for Edge execution-intent v2.

Sentinel Edge sends structured notional and expiry metadata inside the existing
``edge.pulse.handoff.v1`` envelope. Pulse historically accepted that envelope
but ignored the nested execution intent. This patch wraps the handoff endpoint
when FastAPI registers the Edge router so the notional contract is applied
before any broker order is submitted.
"""
from __future__ import annotations

import functools
import math
import time
from typing import Any

from fastapi.routing import APIRoute, APIRouter


_original_include_router = APIRouter.include_router
_PATCH_MARKER = "_pulse_edge_execution_intent_v2"


def _finite_positive(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return number


def _execution_intent(body: Any) -> dict:
    metadata = getattr(body, "metadata", None)
    if not isinstance(metadata, dict):
        return {}
    intent = metadata.get("execution_intent")
    return intent if isinstance(intent, dict) else {}


async def _apply_execution_intent(edge_module: Any, body: Any) -> dict | None:
    intent = _execution_intent(body)
    if not intent:
        return None

    version = str(intent.get("contract_version") or "").strip()
    if version != "edge.execution_intent.v2":
        return edge_module._handoff_response(
            body,
            accepted=False,
            status="rejected",
            reason="unsupported_execution_intent",
            message=f"Unsupported Edge execution intent: {version or 'missing'}",
        )

    intent_id = str(intent.get("intent_id") or "").strip()
    if intent_id and intent_id != body.idempotency_key:
        return edge_module._handoff_response(
            body,
            accepted=False,
            status="rejected",
            reason="execution_intent_id_mismatch",
            message="Nested execution intent ID does not match the handoff idempotency key.",
        )

    expires_at = intent.get("expires_at")
    if expires_at is not None:
        try:
            expiry = float(expires_at)
        except (TypeError, ValueError):
            expiry = 0.0
        if not math.isfinite(expiry) or expiry <= 0:
            return edge_module._handoff_response(
                body,
                accepted=False,
                status="rejected",
                reason="invalid_execution_expiry",
                message="Execution intent expiry must be a positive Unix timestamp.",
            )
        if time.time() >= expiry:
            return edge_module._handoff_response(
                body,
                accepted=False,
                status="rejected",
                reason="execution_intent_expired",
                message="Edge execution intent expired before Pulse could submit it.",
            )

    quantity_policy = intent.get("quantity_policy")
    if not isinstance(quantity_policy, dict):
        quantity_policy = {}
    raw_target = quantity_policy.get("target_notional")
    raw_maximum = intent.get("max_notional")
    target_notional = None if raw_target is None else _finite_positive(raw_target)
    max_notional = None if raw_maximum is None else _finite_positive(raw_maximum)

    if raw_target is not None and target_notional is None:
        return edge_module._handoff_response(
            body,
            accepted=False,
            status="rejected",
            reason="invalid_target_notional",
            message="target_notional must be finite and greater than zero.",
        )
    if raw_maximum is not None and max_notional is None:
        return edge_module._handoff_response(
            body,
            accepted=False,
            status="rejected",
            reason="invalid_max_notional",
            message="max_notional must be finite and greater than zero.",
        )
    if (
        target_notional is not None
        and max_notional is not None
        and target_notional > max_notional + 1e-8
    ):
        return edge_module._handoff_response(
            body,
            accepted=False,
            status="rejected",
            reason="target_notional_exceeds_maximum",
            message=(
                f"Requested target notional {target_notional:.2f} exceeds "
                f"maximum {max_notional:.2f}."
            ),
        )

    if getattr(body.action, "value", str(body.action)) != "buy":
        return None

    symbol = body.symbol
    ticker = await edge_module.deps.db.tickers.find_one(
        {"symbol": symbol},
        {"_id": 0},
    )
    if not ticker:
        ticker = await edge_module._create_ticker_from_edge_buy(symbol)

    current_power = _finite_positive((ticker or {}).get("base_power")) or 100.0
    effective_target = target_notional or current_power
    if max_notional is not None:
        effective_target = min(effective_target, max_notional)

    updates: dict[str, Any] = {
        "base_power": round(effective_target, 8),
        "compound_profits": True,
        "edge_execution_intent_id": body.idempotency_key,
        "edge_target_notional": round(effective_target, 8),
        "edge_max_notional": (
            round(max_notional, 8) if max_notional is not None else None
        ),
        "edge_execution_intent_expires_at": expires_at,
    }

    broker_ids = list((ticker or {}).get("broker_ids") or [])
    allocations = dict((ticker or {}).get("broker_allocations") or {})
    positive_allocations = {
        broker_id: _finite_positive(allocations.get(broker_id)) or 0.0
        for broker_id in broker_ids
    }
    allocation_total = sum(positive_allocations.values())
    if allocation_total > 0:
        scaled = {
            broker_id: round(
                effective_target * (allocation / allocation_total),
                8,
            )
            for broker_id, allocation in positive_allocations.items()
            if allocation > 0
        }
        updates["broker_allocations"] = scaled

    await edge_module.deps.db.tickers.update_one(
        {"symbol": symbol},
        {"$set": updates},
    )
    return None


def _wrap_edge_handoff(route: APIRoute) -> None:
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
        rejection = await _apply_execution_intent(edge_module, body)
        if rejection is not None:
            return rejection
        response = await original_endpoint(*args, **kwargs)
        if isinstance(response, dict):
            intent = _execution_intent(body)
            response.setdefault("execution_intent_id", body.idempotency_key)
            response.setdefault(
                "execution_intent_version",
                intent.get("contract_version") if intent else None,
            )
        return response

    setattr(wrapped, _PATCH_MARKER, True)
    route.endpoint = wrapped


def _include_router_with_edge_contract(self: APIRouter, router: APIRouter, *args: Any, **kwargs: Any):
    for route in getattr(router, "routes", []):
        if (
            isinstance(route, APIRoute)
            and route.path == "/edge/handoff"
            and "POST" in (route.methods or set())
        ):
            _wrap_edge_handoff(route)
    return _original_include_router(self, router, *args, **kwargs)


if not getattr(APIRouter.include_router, _PATCH_MARKER, False):
    setattr(_include_router_with_edge_contract, _PATCH_MARKER, True)
    APIRouter.include_router = _include_router_with_edge_contract
