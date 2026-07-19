"""Decimal-aware price normalization for bracket and passive-limit trading.

Trading prices must not use Python's binary ``round`` for order construction.
The helpers in this module convert through :class:`decimal.Decimal`, apply a
configured or conservative inferred tick size, and only convert back to float
at the broker boundary.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP, ROUND_UP
from typing import Any, Literal


PriceRounding = Literal["nearest", "down", "up"]


def as_decimal(value: Any, *, default: str = "0") -> Decimal:
    """Convert values to ``Decimal`` without inheriting binary-float noise."""
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def infer_tick_size(price: Any, configured_tick: Any = 0) -> Decimal:
    """Return the configured tick or a conservative US-equity default.

    Pulse deliberately keeps the inference simple and operator-overridable:
    sub-dollar instruments default to ``0.0001`` and instruments at or above
    one dollar default to ``0.01``. Broker/venue validation remains the final
    authority and callers should set ``price_tick_size`` when a symbol differs.
    """
    configured = as_decimal(configured_tick)
    if configured > 0:
        return configured
    return Decimal("0.0001") if as_decimal(price) < Decimal("1") else Decimal("0.01")


def normalize_price(
    price: Any,
    tick_size: Any,
    *,
    rounding: PriceRounding = "nearest",
) -> Decimal:
    """Normalize a price to an exact tick multiple."""
    raw = as_decimal(price)
    tick = as_decimal(tick_size)
    if tick <= 0:
        raise ValueError("tick_size must be positive")

    rounding_mode = {
        "nearest": ROUND_HALF_UP,
        "down": ROUND_DOWN,
        "up": ROUND_UP,
    }.get(rounding)
    if rounding_mode is None:
        raise ValueError(f"Unsupported rounding mode: {rounding}")

    ticks = (raw / tick).quantize(Decimal("1"), rounding=rounding_mode)
    return (ticks * tick).quantize(tick)


def bracket_target(
    anchor: Any,
    offset: Any,
    *,
    is_percent: bool,
    tick_size: Any,
    side: Literal["buy", "sell", "stop"] = "buy",
) -> Decimal:
    """Build a normalized bracket target from an anchor and offset.

    Buy limits round down so Pulse never bids above the configured target.
    Sell limits round up so Pulse never offers below the configured target.
    Stop triggers use nearest-tick rounding.
    """
    anchor_dec = as_decimal(anchor)
    offset_dec = as_decimal(offset)
    raw = (
        anchor_dec * (Decimal("1") + offset_dec / Decimal("100"))
        if is_percent
        else offset_dec
    )
    rounding: PriceRounding = "nearest"
    if side == "buy":
        rounding = "down"
    elif side == "sell":
        rounding = "up"
    return normalize_price(raw, tick_size, rounding=rounding)


def decimal_to_float(value: Decimal) -> float:
    """Convert a normalized Decimal for APIs that still require floats."""
    return float(value)
