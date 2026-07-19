"""Cancel/replace controls for working passive range orders.

A working order must not remain at an obsolete price after an operator changes
its ticker configuration. This patch fingerprints the settings used to arm each
buy and sell. When the fingerprint changes, Pulse confirms cancellation of the
old live order (paper orders are removed locally), persists the reset state, and
lets the passive evaluator immediately arm the replacement.
"""

from __future__ import annotations

from typing import Any

import deps
from trading import passive_range_patch as passive


_ORIGINAL_ARM_BUY = passive._arm_buy
_ORIGINAL_ARM_SELL = passive._arm_sell
_ORIGINAL_EVALUATE = passive._evaluate_passive_range


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _allocation_signature(ticker_doc: dict) -> tuple:
    broker_ids = tuple(str(value) for value in (ticker_doc.get("broker_ids") or []))
    allocations = ticker_doc.get("broker_allocations") or {}
    return tuple(
        (broker_id, round(_number(allocations.get(broker_id)), 8))
        for broker_id in broker_ids
    )


def _buy_config_key(ticker_doc: dict) -> tuple:
    return (
        bool(ticker_doc.get("buy_percent", True)),
        round(_number(ticker_doc.get("buy_offset", -3.0)), 8),
        int(ticker_doc.get("avg_days", 30) or 30),
        round(_number(ticker_doc.get("price_tick_size", 0)), 8),
        round(_number(ticker_doc.get("base_power", 100)), 8),
        bool(ticker_doc.get("passive_fractional_shares", False)),
        _allocation_signature(ticker_doc),
    )


def _sell_config_key(ticker_doc: dict) -> tuple:
    return (
        bool(ticker_doc.get("sell_percent", True)),
        round(_number(ticker_doc.get("sell_offset", 3.0)), 8),
        round(_number(ticker_doc.get("price_tick_size", 0)), 8),
    )


def _same_key(stored: Any, current: tuple) -> bool:
    # MongoDB restores tuples as lists. Normalize recursively through repr-safe
    # primitive containers before comparing.
    def normalize(value: Any):
        if isinstance(value, (list, tuple)):
            return tuple(normalize(item) for item in value)
        return value

    return normalize(stored) == normalize(current)


async def _cancel_for_replace(self, ticker_doc: dict, order: dict, label: str) -> bool:
    if passive._is_paper(self, ticker_doc):
        return True
    broker_id, _ = passive._active_broker(ticker_doc)
    if not broker_id:
        deps.logger.error("Passive %s replacement blocked: no single active broker", label)
        return False
    if not order.get("broker_order_id"):
        deps.logger.error("Passive %s replacement blocked: working order has no broker ID", label)
        return False
    cancelled = await passive._cancel_live_order(self, broker_id, order)
    if not cancelled:
        deps.logger.error(
            "Passive %s replacement blocked: broker cancellation was not confirmed",
            label,
        )
    return cancelled


async def _arm_buy_with_config_key(
    self,
    *,
    ticker_doc: dict,
    state: dict,
    buy_target: float,
    effective_power: float,
) -> None:
    state["buy_config_key"] = _buy_config_key(ticker_doc)
    await _ORIGINAL_ARM_BUY(
        self,
        ticker_doc=ticker_doc,
        state=state,
        buy_target=buy_target,
        effective_power=effective_power,
    )


async def _arm_sell_with_config_key(
    self,
    *,
    ticker_doc: dict,
    state: dict,
    sell_target: float,
) -> None:
    state["sell_config_key"] = _sell_config_key(ticker_doc)
    await _ORIGINAL_ARM_SELL(
        self,
        ticker_doc=ticker_doc,
        state=state,
        sell_target=sell_target,
    )


async def _evaluate_with_cancel_replace(self, ticker_doc: dict) -> None:
    symbol = str(ticker_doc.get("symbol") or "").upper()
    if not symbol:
        return await _ORIGINAL_EVALUATE(self, ticker_doc)

    state = await passive._load_state(self, symbol)
    phase = str(state.get("phase") or "IDLE")

    if phase == "BUY_WORKING" and not _same_key(
        state.get("buy_config_key"), _buy_config_key(ticker_doc)
    ):
        order = state.get("buy_order") or {}
        if not await _cancel_for_replace(self, ticker_doc, order, f"BUY {symbol}"):
            return
        state.update(
            {
                "phase": "IDLE",
                "buy_order": None,
                "touch_count": 0,
                "replace_reason": "buy_configuration_changed",
            }
        )
        await passive._persist_state(state)

    elif phase == "SELL_WORKING" and not _same_key(
        state.get("sell_config_key"), _sell_config_key(ticker_doc)
    ):
        order = state.get("sell_order") or {}
        if not await _cancel_for_replace(self, ticker_doc, order, f"SELL {symbol}"):
            return
        state.update(
            {
                "phase": "LONG",
                "sell_order": None,
                "touch_count": 0,
                "replace_reason": "sell_configuration_changed",
            }
        )
        await passive._persist_state(state)

    await _ORIGINAL_EVALUATE(self, ticker_doc)


passive._arm_buy = _arm_buy_with_config_key
passive._arm_sell = _arm_sell_with_config_key
passive._evaluate_passive_range = _evaluate_with_cancel_replace
