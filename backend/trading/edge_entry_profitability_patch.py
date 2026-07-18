"""Pre-mutation Edge entry profitability guard for Pulse handoffs."""
from __future__ import annotations

import functools
import os
from typing import Any

from fastapi.routing import APIRoute, APIRouter

from trading.edge_entry_policy import (
    EdgeEntryPolicyError,
    finite,
    normalise_entry_policy,
    validate_long_entry,
)


_original_include_router = APIRouter.include_router
_PATCH_MARKER = "_pulse_edge_entry_profitability_v1"


def _metadata(body: Any) -> dict[str, Any]:
    value = getattr(body, "metadata", None)
    return value if isinstance(value, dict) else {}


def _execution_intent(body: Any) -> dict[str, Any]:
    value = _metadata(body).get("execution_intent")
    return value if isinstance(value, dict) else {}


def _action(body: Any) -> str:
    value = getattr(body, "action", "")
    return str(getattr(value, "value", value) or "").lower()


def _runtime_policies(engine: Any) -> dict[str, dict[str, Any]]:
    value = getattr(engine, "_edge_entry_policies", None)
    if not isinstance(value, dict):
        value = {}
        setattr(engine, "_edge_entry_policies", value)
    return value


def _quote_values(metadata: dict[str, Any]) -> tuple[float | None, float | None]:
    quote = metadata.get("quote") if isinstance(metadata.get("quote"), dict) else {}
    bid = finite(metadata.get("bid", quote.get("bid")))
    ask = finite(metadata.get("ask", quote.get("ask")))
    return (bid if bid > 0 else None, ask if ask > 0 else None)


def _rejection_response(edge_module: Any, body: Any, error: EdgeEntryPolicyError) -> dict[str, Any]:
    response = edge_module._handoff_response(
        body,
        accepted=False,
        status=error.status,
        reason=error.reason,
        message=str(error),
    )
    response.update(
        {
            "execution_code": error.execution_code,
            "entry_policy": normalise_entry_policy(_execution_intent(body), _metadata(body)),
            "execution_quality": error.details,
        }
    )
    return response


async def _prepare_policy(edge_module: Any, body: Any) -> dict[str, Any] | None:
    if _action(body) != "buy":
        return None
    intent = _execution_intent(body)
    if str(intent.get("contract_version") or "") != "edge.execution_intent.v2":
        return None

    metadata = _metadata(body)
    policy = normalise_entry_policy(intent, metadata)
    price = await edge_module._handoff_price(body.symbol, body)
    bid, ask = _quote_values(metadata)
    try:
        preflight = validate_long_entry(
            policy,
            observed_price=price,
            bid=bid,
            ask=ask,
            fee_bps=finite(os.getenv("PULSE_ESTIMATED_ROUND_TRIP_FEES_BPS"), 0.0),
            slippage_buffer_bps=finite(os.getenv("PULSE_EXECUTION_SLIPPAGE_BUFFER_BPS"), 0.0),
        )
    except EdgeEntryPolicyError as exc:
        return _rejection_response(edge_module, body, exc)

    _runtime_policies(edge_module.deps.engine)[body.symbol] = {
        "intent_id": str(getattr(body, "idempotency_key", "") or ""),
        "policy": policy,
        "preflight": preflight,
        "execution_checks": [],
        "rejection": None,
    }
    return None


async def _persist_audit(edge_module: Any, body: Any, response: Any, runtime: dict[str, Any] | None) -> None:
    if not isinstance(runtime, dict):
        return
    audit = {
        "intent_id": runtime.get("intent_id"),
        "policy": runtime.get("policy"),
        "preflight": runtime.get("preflight"),
        "execution_checks": list(runtime.get("execution_checks") or []),
        "rejection": runtime.get("rejection"),
        "response_status": response.get("status") if isinstance(response, dict) else None,
        "response_reason": response.get("reason") if isinstance(response, dict) else None,
    }
    try:
        await edge_module.deps.db.tickers.update_one(
            {"symbol": body.symbol},
            {"$set": {"edge_entry_policy_audit": audit}},
        )
    except Exception:
        # Audit persistence must not turn a correctly vetoed order into a retry.
        pass


def _normalise_live_rejection(response: Any, runtime: dict[str, Any] | None) -> Any:
    if not isinstance(response, dict) or not isinstance(runtime, dict):
        return response
    rejection = runtime.get("rejection")
    if not isinstance(rejection, dict):
        response.setdefault("entry_policy", runtime.get("policy"))
        response.setdefault("execution_quality", list(runtime.get("execution_checks") or []))
        return response
    response.update(
        {
            "accepted": False,
            "sent": False,
            "status": rejection.get("status") or "rejected",
            "reason": rejection.get("reason") or "entry_rejected_slippage_limit",
            "message": rejection.get("message") or response.get("message") or "Pulse rejected the entry policy.",
            "execution_code": rejection.get("execution_code"),
            "entry_policy": runtime.get("policy"),
            "execution_quality": rejection.get("details") or list(runtime.get("execution_checks") or []),
        }
    )
    return response


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
        rejection = await _prepare_policy(edge_module, body)
        if rejection is not None:
            return rejection

        policies = _runtime_policies(edge_module.deps.engine)
        runtime = policies.get(body.symbol)
        try:
            response = await original_endpoint(*args, **kwargs)
            response = _normalise_live_rejection(response, runtime)
            await _persist_audit(edge_module, body, response, runtime)
            return response
        finally:
            if runtime is not None and policies.get(body.symbol) is runtime:
                policies.pop(body.symbol, None)

    setattr(wrapped, _PATCH_MARKER, True)
    route.endpoint = wrapped


def _include_router_with_entry_profitability(self: APIRouter, router: APIRouter, *args: Any, **kwargs: Any):
    for route in getattr(router, "routes", []):
        if isinstance(route, APIRoute) and route.path == "/edge/handoff" and "POST" in (route.methods or set()):
            _wrap_edge_handoff(route)
    return _original_include_router(self, router, *args, **kwargs)


if not getattr(APIRouter.include_router, _PATCH_MARKER, False):
    setattr(_include_router_with_entry_profitability, _PATCH_MARKER, True)
    APIRouter.include_router = _include_router_with_entry_profitability
