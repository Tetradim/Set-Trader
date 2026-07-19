"""Enrich completed passive-range cycles with execution research metrics."""

from __future__ import annotations

from typing import Any

import deps
from trading import passive_range_patch as passive


_ORIGINAL_COMPLETE_CYCLE = passive._complete_cycle


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


async def _complete_cycle_with_excursions(
    self,
    *,
    ticker_doc: dict,
    state: dict,
    exit_price: float,
    exit_quantity: float,
    pnl: float,
    exit_reason: str,
) -> None:
    entry = _number(state.get("entry_price"))
    minimum = _number(state.get("min_observed_price")) or entry
    maximum = _number(state.get("max_observed_price")) or entry
    if exit_price > 0:
        minimum = min(minimum, exit_price) if minimum > 0 else exit_price
        maximum = max(maximum, exit_price)

    await _ORIGINAL_COMPLETE_CYCLE(
        self,
        ticker_doc=ticker_doc,
        state=state,
        exit_price=exit_price,
        exit_quantity=exit_quantity,
        pnl=pnl,
        exit_reason=exit_reason,
    )

    cycle_id = str(state.get("cycle_id") or "")
    if not cycle_id or entry <= 0:
        return
    metrics = {
        "min_observed_price": minimum,
        "max_observed_price": maximum,
        "max_adverse_excursion": round((minimum - entry) * exit_quantity, 4),
        "max_favorable_excursion": round((maximum - entry) * exit_quantity, 4),
        "return_pct": round(((exit_price - entry) / entry) * 100, 6),
    }
    try:
        await deps.db.passive_range_cycles.update_one(
            {"cycle_id": cycle_id},
            {"$set": metrics},
        )
    except Exception as exc:
        deps.logger.warning(
            "Could not enrich passive range cycle %s: %s", cycle_id, exc
        )


passive._complete_cycle = _complete_cycle_with_excursions
