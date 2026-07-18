"""Apply Edge entry policy to the fresh broker quote used for live execution."""
from __future__ import annotations

from contextvars import ContextVar
import os
from typing import Any

from trading.broker_execution import BrokerExecutionMixin, LiveOrderExecutionError
from trading.edge_entry_policy import EdgeEntryPolicyError, finite, validate_long_entry
from trading import live_execution_quality_patch as quality


_original_place = BrokerExecutionMixin._place_live_order_or_raise
_original_validate_quote = quality._validated_quote
_PATCH_MARKER = "_pulse_edge_live_entry_profitability_v1"
_CONTEXT: ContextVar[dict[str, Any] | None] = ContextVar("pulse_edge_entry_policy", default=None)


def _runtime_policy(engine: Any, symbol: str) -> dict[str, Any] | None:
    policies = getattr(engine, "_edge_entry_policies", None)
    value = policies.get(symbol.upper()) if isinstance(policies, dict) else None
    return value if isinstance(value, dict) else None


def _as_live_error(error: EdgeEntryPolicyError) -> LiveOrderExecutionError:
    converted = LiveOrderExecutionError(str(error))
    converted.reason = error.reason
    converted.execution_code = error.execution_code
    converted.status = error.status
    converted.details = dict(error.details)
    return converted


def _validated_quote_with_edge_policy(snapshot: dict) -> dict:
    validated = _original_validate_quote(snapshot)
    context = _CONTEXT.get()
    if not isinstance(context, dict):
        return validated
    runtime = context.get("runtime")
    policy = runtime.get("policy") if isinstance(runtime, dict) else None
    if not isinstance(policy, dict):
        return validated

    try:
        metrics = validate_long_entry(
            policy,
            observed_price=validated.get("ask") or validated.get("mid"),
            bid=validated.get("bid"),
            ask=validated.get("ask"),
            fee_bps=finite(os.getenv("PULSE_ESTIMATED_ROUND_TRIP_FEES_BPS"), 0.0),
            slippage_buffer_bps=finite(os.getenv("PULSE_EXECUTION_SLIPPAGE_BUFFER_BPS"), 0.0),
        )
    except EdgeEntryPolicyError as exc:
        rejection = {
            "status": exc.status,
            "reason": exc.reason,
            "execution_code": exc.execution_code,
            "message": str(exc),
            "details": {**exc.details, "broker_id": validated.get("broker_id")},
        }
        runtime["rejection"] = rejection
        raise _as_live_error(exc) from exc

    metrics["broker_id"] = validated.get("broker_id")
    runtime.setdefault("execution_checks", []).append(metrics)
    return {**validated, "edge_entry_policy": policy, "edge_execution_quality": metrics}


async def _place_with_edge_policy_context(self: Any, **kwargs: Any):
    order_template = kwargs.get("order_template") if isinstance(kwargs.get("order_template"), dict) else {}
    side = str(order_template.get("side") or "").upper()
    runtime = _runtime_policy(self, str(kwargs.get("sym") or "")) if side == "BUY" else None
    if runtime is None:
        return await _original_place(self, **kwargs)

    token = _CONTEXT.set({"engine": self, "symbol": str(kwargs.get("sym") or "").upper(), "runtime": runtime})
    try:
        return await _original_place(self, **kwargs)
    finally:
        _CONTEXT.reset(token)


if not getattr(quality._validated_quote, _PATCH_MARKER, False):
    setattr(_validated_quote_with_edge_policy, _PATCH_MARKER, True)
    quality._validated_quote = _validated_quote_with_edge_policy

if not getattr(BrokerExecutionMixin._place_live_order_or_raise, _PATCH_MARKER, False):
    setattr(_place_with_edge_policy_context, _PATCH_MARKER, True)
    BrokerExecutionMixin._place_live_order_or_raise = _place_with_edge_policy_context
