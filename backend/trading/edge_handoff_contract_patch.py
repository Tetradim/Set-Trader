"""Runtime integration for Edge execution-intent contracts.

The public handoff envelope remains ``edge.pulse.handoff.v1`` for rollout
compatibility. New supervisory behavior is carried in the nested
``edge.execution_intent.v3`` object and is processed inside Pulse's durable
idempotency wrapper before any broker order is submitted.
"""
from __future__ import annotations

import functools
import math
import time
from typing import Any

from fastapi.routing import APIRoute, APIRouter

from trading.order_lifecycle import OrderLifecycleMixin


_original_include_router = APIRouter.include_router
_original_shared_sell = OrderLifecycleMixin._execute_sell
_PATCH_MARKER = "_pulse_edge_execution_intent_v3"
_POSITION_EPSILON = 1e-8


def _finite_positive(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return number


def _finite_nonnegative(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) and number >= 0 else default


def _execution_intent(body: Any) -> dict:
    metadata = getattr(body, "metadata", None)
    if not isinstance(metadata, dict):
        return {}
    intent = metadata.get("execution_intent")
    return intent if isinstance(intent, dict) else {}


def _position_quantity(position: Any) -> float:
    if not isinstance(position, dict):
        return 0.0
    return _finite_nonnegative(position.get("qty", position.get("quantity", 0)))


def _position_entry(position: Any) -> float:
    if not isinstance(position, dict):
        return 0.0
    return _finite_nonnegative(position.get("avg_entry", position.get("entry_price", 0)))


def _effective_stop_price(ticker: dict, position: dict) -> float:
    raw_stop = ticker.get("stop_offset")
    try:
        stop = float(raw_stop)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(stop):
        return 0.0
    if bool(ticker.get("stop_percent", True)):
        entry = _position_entry(position)
        return entry * (1 + stop / 100.0) if entry > 0 else 0.0
    return stop if stop > 0 else 0.0


def _handoff_response(edge_module: Any, body: Any, *, accepted: bool, status: str, reason: str, message: str = "", **extra: Any) -> dict:
    response = edge_module._handoff_response(
        body,
        accepted=accepted,
        status=status,
        reason=reason,
        message=message,
    )
    response.update(extra)
    return response


def _validate_intent_identity(edge_module: Any, body: Any, intent: dict) -> dict | None:
    intent_id = str(intent.get("intent_id") or "").strip()
    if intent_id and intent_id != body.idempotency_key:
        return _handoff_response(
            edge_module,
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
            return _handoff_response(
                edge_module,
                body,
                accepted=False,
                status="rejected",
                reason="invalid_execution_expiry",
                message="Execution intent expiry must be a positive Unix timestamp.",
            )
        if time.time() >= expiry:
            return _handoff_response(
                edge_module,
                body,
                accepted=False,
                status="rejected",
                reason="execution_intent_expired",
                message="Edge execution intent expired before Pulse could submit it.",
            )
    return None


async def _apply_v2_buy_intent(edge_module: Any, body: Any, intent: dict) -> dict | None:
    quantity_policy = intent.get("quantity_policy")
    if not isinstance(quantity_policy, dict):
        quantity_policy = {}
    raw_target = quantity_policy.get("target_notional")
    raw_maximum = intent.get("max_notional")
    target_notional = None if raw_target is None else _finite_positive(raw_target)
    max_notional = None if raw_maximum is None else _finite_positive(raw_maximum)

    if raw_target is not None and target_notional is None:
        return _handoff_response(
            edge_module,
            body,
            accepted=False,
            status="rejected",
            reason="invalid_target_notional",
            message="target_notional must be finite and greater than zero.",
        )
    if raw_maximum is not None and max_notional is None:
        return _handoff_response(
            edge_module,
            body,
            accepted=False,
            status="rejected",
            reason="invalid_max_notional",
            message="max_notional must be finite and greater than zero.",
        )
    if target_notional is not None and max_notional is not None and target_notional > max_notional + _POSITION_EPSILON:
        return _handoff_response(
            edge_module,
            body,
            accepted=False,
            status="rejected",
            reason="target_notional_exceeds_maximum",
            message=f"Requested target notional {target_notional:.2f} exceeds maximum {max_notional:.2f}.",
        )

    if getattr(body.action, "value", str(body.action)) != "buy":
        return None

    symbol = body.symbol
    ticker = await edge_module.deps.db.tickers.find_one({"symbol": symbol}, {"_id": 0})
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
        "edge_max_notional": round(max_notional, 8) if max_notional is not None else None,
        "edge_execution_intent_expires_at": intent.get("expires_at"),
    }

    broker_ids = list((ticker or {}).get("broker_ids") or [])
    allocations = dict((ticker or {}).get("broker_allocations") or {})
    positive_allocations = {
        broker_id: _finite_positive(allocations.get(broker_id)) or 0.0
        for broker_id in broker_ids
    }
    allocation_total = sum(positive_allocations.values())
    if allocation_total > 0:
        updates["broker_allocations"] = {
            broker_id: round(effective_target * (allocation / allocation_total), 8)
            for broker_id, allocation in positive_allocations.items()
            if allocation > 0
        }

    await edge_module.deps.db.tickers.update_one({"symbol": symbol}, {"$set": updates})
    return None


async def _apply_set_stop(edge_module: Any, body: Any, intent: dict) -> dict:
    if getattr(body.action, "value", str(body.action)) != "tighten_stop":
        return _handoff_response(
            edge_module,
            body,
            accepted=False,
            status="rejected",
            reason="directive_action_mismatch",
            message="set_stop requires the tighten_stop handoff action.",
        )

    symbol = body.symbol
    ticker = await edge_module.deps.db.tickers.find_one({"symbol": symbol}, {"_id": 0})
    position = edge_module._current_position(symbol)
    if not ticker:
        return _handoff_response(edge_module, body, accepted=False, status="rejected", reason="ticker_not_found")
    if _position_quantity(position) <= 0:
        return _handoff_response(edge_module, body, accepted=False, status="rejected", reason="no_position")

    stop_policy = intent.get("stop_policy")
    if not isinstance(stop_policy, dict):
        stop_policy = {}
    stop_price = _finite_positive(stop_policy.get("stop_price"))
    if stop_policy.get("type") != "absolute" or stop_price is None:
        return _handoff_response(
            edge_module,
            body,
            accepted=False,
            status="rejected",
            reason="invalid_stop_policy",
            message="set_stop requires a finite positive absolute stop_price.",
        )

    current_price = await edge_module._handoff_price(symbol, body)
    if current_price <= 0:
        return _handoff_response(edge_module, body, accepted=False, status="rejected", reason="price_unavailable")
    if stop_price >= current_price:
        return _handoff_response(
            edge_module,
            body,
            accepted=False,
            status="rejected",
            reason="stop_not_below_market",
            message=f"Long-position stop {stop_price:.4f} must be below current price {current_price:.4f}.",
        )

    previous_stop = _effective_stop_price(ticker, position)
    tighten_only = bool(stop_policy.get("tighten_only", True))
    if tighten_only and previous_stop > 0 and stop_price + 1e-8 < previous_stop:
        return _handoff_response(
            edge_module,
            body,
            accepted=False,
            status="rejected",
            reason="stop_widening_blocked",
            message=f"Requested stop {stop_price:.4f} is below existing stop {previous_stop:.4f}.",
            previous_stop_price=round(previous_stop, 8),
        )

    updates = {
        "stop_offset": round(stop_price, 8),
        "stop_percent": False,
        "auto_stop_reason": body.reason or "edge_set_stop",
        "edge_stop_price": round(stop_price, 8),
        "edge_stop_intent_id": body.idempotency_key,
        "edge_stop_updated_at": time.time(),
    }
    await edge_module.deps.db.tickers.update_one({"symbol": symbol}, {"$set": updates})
    return _handoff_response(
        edge_module,
        body,
        accepted=True,
        status="accepted",
        reason="pulse_accepted",
        message=f"Absolute stop set to {stop_price:.4f} for {symbol}.",
        directive="set_stop",
        stop_price=round(stop_price, 8),
        previous_stop_price=round(previous_stop, 8) if previous_stop > 0 else None,
    )


async def _apply_reduce_position(edge_module: Any, body: Any, intent: dict) -> dict:
    if getattr(body.action, "value", str(body.action)) != "sell":
        return _handoff_response(
            edge_module,
            body,
            accepted=False,
            status="rejected",
            reason="directive_action_mismatch",
            message="reduce_position requires the sell handoff action.",
        )

    symbol = body.symbol
    position = edge_module._current_position(symbol)
    position_qty = _position_quantity(position)
    if position_qty <= 0:
        return _handoff_response(edge_module, body, accepted=False, status="rejected", reason="no_position")

    guard = intent.get("position_guard")
    if not isinstance(guard, dict):
        guard = {}
    expected_qty = _finite_positive(guard.get("expected_quantity"))
    drift_pct = _finite_nonnegative(guard.get("max_quantity_drift_percent"), 2.0)
    if expected_qty is not None:
        allowed_drift = max(0.0001, expected_qty * drift_pct / 100.0)
        if abs(position_qty - expected_qty) > allowed_drift:
            return _handoff_response(
                edge_module,
                body,
                accepted=False,
                status="rejected",
                reason="position_guard_mismatch",
                message=(
                    f"Pulse position {position_qty:.8f} differs from Edge expectation "
                    f"{expected_qty:.8f} by more than {drift_pct:.2f}%.",
                ),
                current_quantity=position_qty,
                expected_quantity=expected_qty,
            )

    quantity_policy = intent.get("quantity_policy")
    if not isinstance(quantity_policy, dict):
        quantity_policy = {}
    policy_type = str(quantity_policy.get("type") or "").strip()
    if policy_type == "reduce_percent":
        reduce_percent = _finite_positive(quantity_policy.get("reduce_percent"))
        if reduce_percent is None or reduce_percent >= 100:
            return _handoff_response(
                edge_module,
                body,
                accepted=False,
                status="rejected",
                reason="invalid_reduce_percent",
                message="reduce_percent must be finite, greater than 0, and less than 100.",
            )
        requested_qty = position_qty * reduce_percent / 100.0
    elif policy_type == "reduce_quantity":
        requested_qty = _finite_positive(quantity_policy.get("reduce_quantity")) or 0.0
        if requested_qty <= 0 or requested_qty >= position_qty - _POSITION_EPSILON:
            return _handoff_response(
                edge_module,
                body,
                accepted=False,
                status="rejected",
                reason="invalid_reduce_quantity",
                message="reduce_quantity must be positive and smaller than the open position.",
            )
    else:
        return _handoff_response(
            edge_module,
            body,
            accepted=False,
            status="rejected",
            reason="invalid_quantity_policy",
            message="reduce_position requires reduce_percent or reduce_quantity policy.",
        )

    requested_qty = round(min(requested_qty, position_qty), 8)
    if requested_qty <= 0 or requested_qty >= position_qty - _POSITION_EPSILON:
        return _handoff_response(
            edge_module,
            body,
            accepted=False,
            status="rejected",
            reason="reduction_rounds_to_full_exit",
            message="Resolved reduction must leave a positive position; use sell for a full exit.",
        )

    price = await edge_module._handoff_price(symbol, body)
    if price <= 0:
        return _handoff_response(edge_module, body, accepted=False, status="rejected", reason="price_unavailable")

    executor = getattr(edge_module.deps.engine, "execute_reduce_position", None)
    if not callable(executor):
        return _handoff_response(
            edge_module,
            body,
            accepted=False,
            status="failed",
            reason="reduce_execution_unavailable",
            message="Pulse runtime does not expose partial position reduction.",
        )
    result = await executor(
        symbol,
        requested_qty,
        price,
        body.reason or "Edge supervisory position reduction",
    )
    executed_qty = _finite_nonnegative((result or {}).get("quantity"), requested_qty)
    remaining_qty = _finite_nonnegative((result or {}).get("remaining_quantity"), position_qty - executed_qty)
    return _handoff_response(
        edge_module,
        body,
        accepted=True,
        status="accepted",
        reason="pulse_accepted",
        message=f"Reduced {symbol} by {executed_qty:.8f}; {remaining_qty:.8f} remains.",
        directive="reduce_position",
        requested_quantity=requested_qty,
        executed_quantity=executed_qty,
        remaining_quantity=remaining_qty,
        execution_result=result,
    )


async def _apply_execution_intent(edge_module: Any, body: Any) -> dict | None:
    intent = _execution_intent(body)
    if not intent:
        return None

    version = str(intent.get("contract_version") or "").strip()
    if version not in {"edge.execution_intent.v2", "edge.execution_intent.v3"}:
        return _handoff_response(
            edge_module,
            body,
            accepted=False,
            status="rejected",
            reason="unsupported_execution_intent",
            message=f"Unsupported Edge execution intent: {version or 'missing'}",
        )

    identity_rejection = _validate_intent_identity(edge_module, body, intent)
    if identity_rejection is not None:
        return identity_rejection

    if version == "edge.execution_intent.v2":
        return await _apply_v2_buy_intent(edge_module, body, intent)

    directive = str(intent.get("directive") or "").strip().lower()
    if directive == "set_stop":
        return await _apply_set_stop(edge_module, body, intent)
    if directive == "reduce_position":
        return await _apply_reduce_position(edge_module, body, intent)
    return _handoff_response(
        edge_module,
        body,
        accepted=False,
        status="rejected",
        reason="unsupported_supervisory_directive",
        message=f"Unsupported Edge supervisory directive: {directive or 'missing'}",
    )


async def _shared_sell_with_remaining_position(
    self: Any,
    sym: str,
    price: float,
    qty: float,
    entry: float,
    order_type: str,
    reason: str,
) -> dict:
    """Preserve unsold shares when the shared sell reducer is called partially."""
    current = getattr(self, "_positions", {}).get(sym, {})
    total_before = _position_quantity(current)
    requested = min(_finite_nonnegative(qty), total_before or _finite_nonnegative(qty))
    result = await _original_shared_sell(self, sym, price, requested, entry, order_type, reason)
    executed = _finite_nonnegative((result or {}).get("quantity"), requested)
    remaining = round(max(0.0, total_before - executed), 8) if total_before > 0 else 0.0
    if remaining > _POSITION_EPSILON:
        latest = getattr(self, "_positions", {}).get(sym, {})
        self._positions[sym] = {
            "qty": remaining,
            "avg_entry": entry,
            "high": latest.get("high", current.get("high", price)),
        }
    if isinstance(result, dict):
        result["remaining_quantity"] = remaining
        result["position_quantity_before"] = total_before
    return result


async def _execute_reduce_position(
    self: Any,
    symbol: str,
    quantity: float,
    price: float | None = None,
    reason: str = "Edge supervisory position reduction",
) -> dict:
    sym = str(symbol or "").upper()
    position = getattr(self, "_positions", {}).get(sym)
    total = _position_quantity(position)
    requested = _finite_positive(quantity)
    if total <= 0:
        raise ValueError(f"No open position for {sym}")
    if requested is None or requested >= total - _POSITION_EPSILON:
        raise ValueError(f"Reduction quantity for {sym} must be positive and smaller than {total:.8f}")
    if price is None:
        exec_price = getattr(self, "_prices", {}).get(sym) or await __import__("deps").price_service.get_price(sym)
    else:
        exec_price = _finite_positive(price)
    if exec_price is None or exec_price <= 0:
        raise ValueError(f"Invalid reduction price for {sym}")
    self._prices[sym] = exec_price
    return await self._execute_sell(
        sym,
        exec_price,
        round(requested, 8),
        _position_entry(position),
        "MARKET",
        reason,
    )


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
        result = await _apply_execution_intent(edge_module, body)
        if result is not None:
            return result
        response = await original_endpoint(*args, **kwargs)
        if isinstance(response, dict):
            intent = _execution_intent(body)
            response.setdefault("execution_intent_id", body.idempotency_key)
            response.setdefault("execution_intent_version", intent.get("contract_version") if intent else None)
        return response

    setattr(wrapped, _PATCH_MARKER, True)
    route.endpoint = wrapped


def _include_router_with_edge_contract(self: APIRouter, router: APIRouter, *args: Any, **kwargs: Any):
    for route in getattr(router, "routes", []):
        if isinstance(route, APIRoute) and route.path == "/edge/handoff" and "POST" in (route.methods or set()):
            _wrap_edge_handoff(route)
    return _original_include_router(self, router, *args, **kwargs)


if not getattr(APIRouter.include_router, _PATCH_MARKER, False):
    setattr(_include_router_with_edge_contract, _PATCH_MARKER, True)
    APIRouter.include_router = _include_router_with_edge_contract

if not getattr(OrderLifecycleMixin._execute_sell, _PATCH_MARKER, False):
    setattr(_shared_sell_with_remaining_position, _PATCH_MARKER, True)
    OrderLifecycleMixin._execute_sell = _shared_sell_with_remaining_position
    OrderLifecycleMixin.execute_reduce_position = _execute_reduce_position
