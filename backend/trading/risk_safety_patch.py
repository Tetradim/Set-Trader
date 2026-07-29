"""Durable, rolling-window risk controls for live execution."""
from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any

import deps
from risk_controls import (
    ExposureLimit,
    KillSwitchLevel,
    OrderRestriction,
    RiskCheckResult,
    RiskControls,
)


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def schedule_engine_state_save() -> None:
    engine = getattr(deps, "engine", None)
    if engine is None or not hasattr(engine, "save_state"):
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(engine.save_state())


_original_add_exposure_limit = RiskControls.add_exposure_limit
_original_add_kill_switch = RiskControls.add_kill_switch
_original_activate_kill_switch = RiskControls.activate_kill_switch
_original_deactivate_kill_switch = RiskControls.deactivate_kill_switch
_original_set_restriction = RiskControls.set_restriction
_original_add_restricted_symbol = RiskControls.add_restricted_symbol
_original_remove_restricted_symbol = RiskControls.remove_restricted_symbol
_original_set_fat_finger_limit = RiskControls.set_fat_finger_limit


def _windows(self: RiskControls) -> dict[str, deque[datetime]]:
    value = getattr(self, "_order_windows_by_limit", None)
    if value is None:
        value = {}
        self._order_windows_by_limit = value
    return value


def prune_order_window(self: RiskControls, level: str, level_id: str) -> int:
    key = f"{level}:{level_id}"
    window = _windows(self).setdefault(key, deque())
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=60)
    while window and window[0] < cutoff:
        window.popleft()
    limit = self.get_exposure_limit(level, level_id)
    if limit is not None:
        limit.orders_count = len(window)
    return len(window)


def update_exposure(
    self: RiskControls,
    level: str,
    level_id: str,
    notional_delta: float = 0.0,
    position_delta: float = 0.0,
    pnl_delta: float = 0.0,
    order_count: int = 0,
):
    limit = self.get_exposure_limit(level, level_id)
    if limit is None:
        return
    limit.current_notional = max(
        0.0, _number(limit.current_notional) + _number(notional_delta)
    )
    limit.current_position = max(
        0.0, _number(limit.current_position) + _number(position_delta)
    )
    limit.daily_pnl = _number(limit.daily_pnl) + _number(pnl_delta)
    if order_count > 0:
        window = _windows(self).setdefault(f"{level}:{level_id}", deque())
        now = datetime.now(timezone.utc)
        for _ in range(int(order_count)):
            window.append(now)
    prune_order_window(self, level, level_id)


def effective_notional_limit(limit: ExposureLimit) -> float:
    if _number(limit.max_notional) > 0:
        return _number(limit.max_notional)
    # Legacy symbol limits stored dollar values in max_position_size.
    if str(limit.level).lower() == "symbol":
        return max(0.0, _number(limit.max_position_size))
    return 0.0


def check_exposure_limit(
    self: RiskControls, level: str, level_id: str
) -> RiskCheckResult:
    limit = self.get_exposure_limit(level, level_id)
    if not limit or not limit.is_enabled:
        return RiskCheckResult(is_allowed=True)

    order_count = prune_order_window(self, level, level_id)
    max_notional = effective_notional_limit(limit)
    if max_notional > 0 and _number(limit.current_notional) > max_notional:
        return RiskCheckResult(
            is_allowed=False,
            restriction=OrderRestriction.HARD_BLOCK,
            message=(
                f"Notional limit exceeded: ${limit.current_notional:.2f} "
                f"> ${max_notional:.2f}"
            ),
            rejected_fields={"notional": limit.current_notional},
        )

    max_quantity = max(0.0, _number(getattr(limit, "max_quantity", 0)))
    if max_quantity > 0 and abs(_number(limit.current_position)) > max_quantity:
        return RiskCheckResult(
            is_allowed=False,
            restriction=OrderRestriction.HARD_BLOCK,
            message=(
                f"Quantity limit exceeded: {limit.current_position:.8f} "
                f"> {max_quantity:.8f}"
            ),
            rejected_fields={"position": limit.current_position},
        )

    if limit.max_daily_loss > 0 and _number(limit.daily_pnl) < -_number(limit.max_daily_loss):
        return RiskCheckResult(
            is_allowed=False,
            restriction=OrderRestriction.HARD_BLOCK,
            message=(
                f"Daily loss limit exceeded: ${limit.daily_pnl:.2f} "
                f"< -${limit.max_daily_loss:.2f}"
            ),
            rejected_fields={"daily_pnl": limit.daily_pnl},
        )

    if limit.max_orders_per_minute > 0 and order_count >= limit.max_orders_per_minute:
        return RiskCheckResult(
            is_allowed=False,
            restriction=OrderRestriction.CANCEL_ALL,
            message=(
                f"Order rate limit exceeded: {order_count} "
                f">= {limit.max_orders_per_minute}/min"
            ),
            rejected_fields={"orders_count": order_count},
        )
    return RiskCheckResult(is_allowed=True)


def get_all_limits(self: RiskControls) -> list[dict[str, Any]]:
    return [
        {
            "limit_id": limit.limit_id,
            "level": limit.level,
            "level_id": limit.level_id,
            "max_notional": effective_notional_limit(limit),
            "max_daily_loss": limit.max_daily_loss,
            "max_position_size": _number(getattr(limit, "max_quantity", 0)),
            "soft_limit": limit.soft_limit,
            "current_notional": limit.current_notional,
            "current_position": limit.current_position,
            "daily_pnl": limit.daily_pnl,
            "orders_count": prune_order_window(self, limit.level, limit.level_id),
            "is_enabled": limit.is_enabled,
        }
        for limit in self._exposure_limits.values()
    ]


def export_state(self: RiskControls) -> dict[str, Any]:
    return {
        "limits": [
            {
                "limit_id": limit.limit_id,
                "level": limit.level,
                "level_id": limit.level_id,
                "max_notional": limit.max_notional,
                "max_daily_loss": limit.max_daily_loss,
                "max_position_size": limit.max_position_size,
                "max_orders_per_minute": limit.max_orders_per_minute,
                "soft_limit": limit.soft_limit,
                "is_enabled": limit.is_enabled,
                "max_quantity": _number(getattr(limit, "max_quantity", 0)),
            }
            for limit in self._exposure_limits.values()
        ],
        "kill_switches": [
            {
                "level": switch.level.value,
                "target_id": switch.target_id,
                "is_active": switch.is_active,
                "triggered_by": switch.triggered_by,
                "triggered_at": (
                    switch.triggered_at.isoformat() if switch.triggered_at else None
                ),
                "reason": switch.reason,
            }
            for switch in self._kill_switches.values()
        ],
        "order_restrictions": {
            key: value.value for key, value in self._order_restrictions.items()
        },
        "restricted_symbols": sorted(self._symbol_restrictions),
        "fat_finger_limits": dict(self._fat_finger_limits),
    }


def load_state(self: RiskControls, state: dict[str, Any] | None) -> None:
    state = state or {}
    for raw in state.get("limits") or []:
        try:
            limit = ExposureLimit(
                limit_id=str(raw.get("limit_id") or ""),
                level=str(raw.get("level") or ""),
                level_id=str(raw.get("level_id") or ""),
                max_notional=_number(raw.get("max_notional")),
                max_daily_loss=_number(raw.get("max_daily_loss")),
                max_position_size=_number(raw.get("max_position_size")),
                max_orders_per_minute=int(raw.get("max_orders_per_minute") or 0),
                soft_limit=_number(raw.get("soft_limit")),
                is_enabled=bool(raw.get("is_enabled", True)),
            )
            setattr(limit, "max_quantity", _number(raw.get("max_quantity")))
            _original_add_exposure_limit(self, limit)
        except Exception as exc:
            deps.logger.warning("Ignoring invalid persisted exposure limit: %s", exc)

    self._kill_switches.clear()
    for raw in state.get("kill_switches") or []:
        try:
            level = KillSwitchLevel(str(raw.get("level") or ""))
            switch = _original_add_kill_switch(
                self, level, str(raw.get("target_id") or "")
            )
            if raw.get("is_active"):
                switch.is_active = True
                switch.triggered_by = str(raw.get("triggered_by") or "")
                if raw.get("triggered_at"):
                    switch.triggered_at = datetime.fromisoformat(
                        str(raw["triggered_at"]).replace("Z", "+00:00")
                    )
                switch.reason = str(raw.get("reason") or "")
        except Exception as exc:
            deps.logger.warning("Ignoring invalid persisted kill switch: %s", exc)

    self._order_restrictions = {}
    for target, value in (state.get("order_restrictions") or {}).items():
        try:
            self._order_restrictions[str(target)] = OrderRestriction(str(value))
        except ValueError:
            continue
    self._symbol_restrictions = {
        str(symbol).upper() for symbol in (state.get("restricted_symbols") or [])
    }
    self._fat_finger_limits = {
        str(symbol).upper(): _number(value)
        for symbol, value in (state.get("fat_finger_limits") or {}).items()
    }
    self._order_windows_by_limit = {}


def _wrap_persist(original):
    def wrapped(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        schedule_engine_state_save()
        return result
    return wrapped


RiskControls.update_exposure = update_exposure
RiskControls.check_exposure_limit = check_exposure_limit
RiskControls.get_all_limits = get_all_limits
RiskControls.export_state = export_state
RiskControls.load_state = load_state
RiskControls.add_exposure_limit = _wrap_persist(_original_add_exposure_limit)
RiskControls.add_kill_switch = _wrap_persist(_original_add_kill_switch)
RiskControls.activate_kill_switch = _wrap_persist(_original_activate_kill_switch)
RiskControls.deactivate_kill_switch = _wrap_persist(_original_deactivate_kill_switch)
RiskControls.set_restriction = _wrap_persist(_original_set_restriction)
RiskControls.add_restricted_symbol = _wrap_persist(_original_add_restricted_symbol)
RiskControls.remove_restricted_symbol = _wrap_persist(_original_remove_restricted_symbol)
RiskControls.set_fat_finger_limit = _wrap_persist(_original_set_fat_finger_limit)
