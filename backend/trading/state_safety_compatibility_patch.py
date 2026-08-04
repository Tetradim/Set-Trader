"""Keep legacy state persistence ordering and minimal-test reconciliation support."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

import deps
from trading import broker_position_safety_patch as safety_state
from trading import broker_position_truth_patch as broker_truth
from trading.engine_state import EngineStateMixin


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


async def _save_state_with_engine_document_last(self):
    # Persist supplemental risk/broker state first. The canonical engine_state
    # write remains last for compatibility with existing tooling and tests.
    await deps.db.settings.update_one(
        {"key": safety_state._STATE_KEY},
        {
            "$set": {
                "value": {
                    "risk": self.risk_controls.export_state(),
                    "broker_positions": deepcopy(
                        getattr(self, "_broker_positions_by_broker", {}) or {}
                    ),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            }
        },
        upsert=True,
    )
    await safety_state._original_save_state(self)


async def _sync_with_minimal_db_compatibility(self, broker_id: str) -> dict:
    tickers = getattr(deps.db, "tickers", None)
    if tickers is not None and hasattr(tickers, "find"):
        return await broker_truth.sync_positions_from_broker(self, broker_id)

    # Minimal unit-test and legacy adapters expose only find_one(). Preserve the
    # old single-broker replacement behavior in that constrained environment.
    broker_positions = await deps.broker_mgr.reconcile_positions(broker_id)
    if broker_positions is None:
        raise RuntimeError(f"Broker {broker_id} returned no position evidence")

    previous = deepcopy(self._positions or {})
    synced: dict[str, dict[str, float]] = {}
    for symbol, raw in (broker_positions or {}).items():
        sym = str(symbol or "").upper()
        quantity = max(0.0, _number((raw or {}).get("quantity")))
        if quantity <= 0:
            continue
        avg_entry = max(0.0, _number((raw or {}).get("avg_entry")))
        current_price = max(
            0.0, _number((raw or {}).get("current_price"))
        )
        old_high = _number((previous.get(sym) or {}).get("high"))
        synced[sym] = {
            "qty": round(quantity, 8),
            "avg_entry": avg_entry,
            "high": max(old_high, avg_entry, current_price),
            "broker_positions": {
                str(broker_id): {
                    "qty": round(quantity, 8),
                    "avg_entry": avg_entry,
                    "current_price": current_price,
                }
            },
        }
        if current_price > 0:
            self._prices[sym] = current_price

    old_symbols = {
        symbol
        for symbol, position in previous.items()
        if _number((position or {}).get("qty")) > 0
    }
    new_symbols = set(synced)
    added = sorted(new_symbols - old_symbols)
    removed = sorted(old_symbols - new_symbols)
    updated = sorted(
        symbol
        for symbol in old_symbols & new_symbols
        if abs(
            _number((previous.get(symbol) or {}).get("qty"))
            - _number((synced.get(symbol) or {}).get("qty"))
        )
        > 1e-8
    )

    self._positions = synced
    self._broker_positions_by_broker = {
        str(broker_id): {
            symbol: {
                "qty": position["qty"],
                "avg_entry": position["avg_entry"],
                "current_price": _number(
                    position["broker_positions"][str(broker_id)].get(
                        "current_price"
                    )
                ),
            }
            for symbol, position in synced.items()
        }
    }

    now = datetime.now(timezone.utc)
    for symbol in removed:
        self._trailing_highs.pop(symbol, None)
        self._opening_bell_highs.pop(symbol, None)
        self._last_exit_ts[symbol] = now
    for symbol, position in synced.items():
        self._trailing_highs[symbol] = max(
            _number(self._trailing_highs.get(symbol)),
            _number(position.get("high")),
        )

    await safety_state.rebuild_risk_exposure(self)
    await self.save_state()
    return {
        "broker_id": broker_id,
        "synced": len(synced),
        "added": added,
        "updated": updated,
        "removed": removed,
        "skipped_external": [],
    }


EngineStateMixin.save_state = _save_state_with_engine_document_last
EngineStateMixin.sync_positions_from_broker = _sync_with_minimal_db_compatibility
