"""Select and materialize Edge-authorized BUY execution styles."""
from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Dict


_ALLOWED = {"passive_limit", "timed_limit", "breakout_stop_limit"}


class EdgeExecutionStyleError(ValueError):
    pass


def finite(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def positive(value: Any) -> float | None:
    number = finite(value)
    return number if number > 0 else None


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalise_style_policy(value: Any) -> Dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    allowed = raw.get("allowed_styles") if isinstance(raw.get("allowed_styles"), list) else []
    allowed = [str(item).strip().lower() for item in allowed if str(item).strip().lower() in _ALLOWED]
    if not allowed:
        allowed = ["passive_limit", "timed_limit", "breakout_stop_limit"]
    preferred = str(raw.get("preferred_style") or "timed_limit").strip().lower()
    if preferred not in allowed:
        preferred = "timed_limit" if "timed_limit" in allowed else allowed[0]
    horizons = raw.get("post_fill_horizons_seconds") if isinstance(raw.get("post_fill_horizons_seconds"), list) else [30, 60, 300]
    return {
        "contract_version": "edge.execution_style.v1",
        "preferred_style": preferred,
        "allowed_styles": allowed,
        "timeout_seconds": max(1, int(finite(raw.get("timeout_seconds"), 8.0))),
        "passive_offset_bps": max(0.0, finite(raw.get("passive_offset_bps"), 2.0)),
        "aggressive_limit_buffer_bps": max(0.0, finite(raw.get("aggressive_limit_buffer_bps"), 4.0)),
        "stop_trigger_price": positive(raw.get("stop_trigger_price")),
        "post_fill_horizons_seconds": sorted({max(1, int(finite(item))) for item in horizons if finite(item) > 0}),
        "strategy": str(raw.get("strategy") or "unknown"),
        "orb_confirmation": raw.get("orb_confirmation") if isinstance(raw.get("orb_confirmation"), dict) else {},
        "squeeze_state": str(raw.get("squeeze_state") or ""),
    }


def select_execution_style(
    entry_policy: Dict[str, Any],
    *,
    bid: float | None = None,
    ask: float | None = None,
    observed_price: float | None = None,
) -> Dict[str, Any]:
    """Select the style and exact broker prices without exceeding Edge limits."""
    policy = entry_policy if isinstance(entry_policy, dict) else {}
    style_policy = normalise_style_policy(policy.get("execution_style_policy"))
    preferred = style_policy["preferred_style"]
    reference = positive(policy.get("ideal_entry_price")) or positive(policy.get("reference_price")) or positive(observed_price)
    bid_value = positive(bid)
    ask_value = positive(ask) or positive(observed_price) or reference
    maximum = positive(policy.get("maximum_entry_price"))
    if reference is None or ask_value is None:
        raise EdgeExecutionStyleError("Execution style requires a positive reference and executable price")
    if maximum is not None and ask_value > maximum:
        raise EdgeExecutionStyleError("Executable price exceeds Edge maximum entry price")

    spread_pct = 0.0
    if bid_value is not None and ask_value is not None:
        mid = (bid_value + ask_value) / 2.0
        spread_pct = ((ask_value - bid_value) / mid) * 100.0 if mid > 0 else 0.0

    style = preferred
    reason = "edge_preferred_style"
    orb = style_policy.get("orb_confirmation") or {}
    squeeze_state = style_policy.get("squeeze_state")
    breakout_confirmed = (
        style_policy.get("stop_trigger_price") is not None
        and (orb.get("direction") == "bullish" or squeeze_state in {"triggering", "active"})
    )
    if style == "breakout_stop_limit" and not breakout_confirmed:
        style = "timed_limit"
        reason = "breakout_trigger_missing_fallback"
    if style == "passive_limit" and bid_value is None:
        style = "timed_limit"
        reason = "passive_quote_missing_fallback"

    limit_price: float
    stop_price: float | None = None
    timeout_seconds: int | None = None
    if style == "passive_limit":
        offset = style_policy["passive_offset_bps"] / 10000.0
        limit_price = min(ask_value, bid_value * (1.0 + offset)) if bid_value is not None else reference
        limit_price = min(limit_price, reference)
        order_type = "LIMIT"
    elif style == "breakout_stop_limit":
        stop_price = positive(style_policy.get("stop_trigger_price")) or reference
        buffer_pct = style_policy["aggressive_limit_buffer_bps"] / 10000.0
        limit_price = max(ask_value, stop_price * (1.0 + buffer_pct))
        timeout_seconds = style_policy["timeout_seconds"]
        order_type = "STOP_LIMIT"
    else:
        buffer_pct = style_policy["aggressive_limit_buffer_bps"] / 10000.0
        limit_price = ask_value * (1.0 + buffer_pct)
        timeout_seconds = style_policy["timeout_seconds"]
        order_type = "LIMIT"

    if maximum is not None:
        limit_price = min(limit_price, maximum)
    if limit_price <= 0 or (stop_price is not None and maximum is not None and stop_price > maximum):
        raise EdgeExecutionStyleError("Execution style cannot satisfy Edge price boundaries")

    return {
        "contract_version": "pulse.execution_style.selection.v1",
        "style": style,
        "selection_reason": reason,
        "selected_at": _iso_now(),
        "order_type": order_type,
        "time_in_force": "day",
        "reference_price": round(reference, 8),
        "arrival_bid": round(bid_value, 8) if bid_value is not None else None,
        "arrival_ask": round(ask_value, 8),
        "arrival_spread_pct": round(spread_pct, 6),
        "limit_price": round(limit_price, 8),
        "stop_price": round(stop_price, 8) if stop_price is not None else None,
        "timeout_seconds": timeout_seconds,
        "maximum_entry_price": maximum,
        "post_fill_horizons_seconds": style_policy["post_fill_horizons_seconds"],
        "strategy": style_policy["strategy"],
        "squeeze_state": squeeze_state,
        "orb_confirmation": orb,
    }


def apply_execution_style(order_template: Dict[str, Any], selection: Dict[str, Any]) -> Dict[str, Any]:
    template = dict(order_template or {})
    template.update(
        {
            "order_type": selection["order_type"],
            "price": selection["arrival_ask"],
            "limit_price": selection["limit_price"],
            "stop_price": selection.get("stop_price"),
            "time_in_force": selection.get("time_in_force", "day"),
            "timeout_seconds": selection.get("timeout_seconds"),
            "execution_style": selection["style"],
            "execution_style_selection": selection,
        }
    )
    return template


def execution_attribution(
    selection: Dict[str, Any],
    *,
    status: str,
    fill_price: float = 0.0,
    filled_quantity: float = 0.0,
    post_fill_prices: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    arrival = positive(selection.get("arrival_ask")) or positive(selection.get("reference_price")) or 0.0
    fill = positive(fill_price) or 0.0
    slippage_bps = ((fill - arrival) / arrival) * 10000.0 if fill > 0 and arrival > 0 else None
    post_fill: Dict[str, Any] = {}
    for horizon, value in (post_fill_prices or {}).items():
        marked = positive(value)
        if fill > 0 and marked is not None:
            post_fill[str(horizon)] = {
                "price": round(marked, 8),
                "move_bps": round(((marked - fill) / fill) * 10000.0, 4),
            }
    normalized_status = str(status or "unknown").lower()
    return {
        "contract_version": "pulse.execution_attribution.v1",
        "style": selection.get("style"),
        "order_type": selection.get("order_type"),
        "selected_at": selection.get("selected_at"),
        "arrival_price": arrival or None,
        "limit_price": selection.get("limit_price"),
        "stop_price": selection.get("stop_price"),
        "fill_price": fill or None,
        "filled_quantity": round(max(0.0, finite(filled_quantity)), 8),
        "fill_slippage_bps": round(slippage_bps, 4) if slippage_bps is not None else None,
        "missed_fill": fill <= 0 and normalized_status in {"cancelled", "canceled", "expired", "rejected", "deferred", "failed"},
        "status": normalized_status,
        "post_fill_movement": post_fill,
        "post_fill_horizons_seconds": selection.get("post_fill_horizons_seconds", []),
        "recorded_at": _iso_now(),
    }
