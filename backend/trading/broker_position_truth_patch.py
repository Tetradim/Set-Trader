"""Final broker reconciliation with broker-scoped aggregation and metadata preservation."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

import deps
from trading.broker_position_safety_patch import rebuild_risk_exposure
from trading.engine_state import EngineStateMixin


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


async def sync_positions_from_broker(self, broker_id: str) -> dict:
    broker_positions = await deps.broker_mgr.reconcile_positions(broker_id)
    if broker_positions is None:
        raise RuntimeError(f"Broker {broker_id} returned no position evidence")

    ticker_docs = await deps.db.tickers.find(
        {},
        {"_id": 0, "symbol": 1, "broker_id": 1, "broker_ids": 1},
    ).to_list(1000)
    broker_managed_symbols = {
        str(doc.get("symbol") or "").upper()
        for doc in ticker_docs
        if doc.get("symbol")
        and (
            list(doc.get("broker_ids") or [])
            or str(doc.get("broker_id") or "").strip()
        )
    }

    previous = deepcopy(self._positions or {})
    broker_managed_symbols.update(
        symbol
        for symbol, position in previous.items()
        if _number((position or {}).get("qty")) > 0
    )

    normalized: dict[str, dict[str, float]] = {}
    for symbol, raw in (broker_positions or {}).items():
        sym = str(symbol or "").upper()
        quantity = max(0.0, _number((raw or {}).get("quantity")))
        if quantity <= 0:
            continue
        broker_managed_symbols.add(sym)
        normalized[sym] = {
            "qty": round(quantity, 8),
            "avg_entry": max(0.0, _number((raw or {}).get("avg_entry"))),
            "current_price": max(
                0.0, _number((raw or {}).get("current_price"))
            ),
        }

    snapshots = getattr(self, "_broker_positions_by_broker", None)
    if snapshots is None:
        snapshots = {}
        self._broker_positions_by_broker = snapshots
    # A successful empty response is authoritative zero holdings for this broker.
    snapshots[str(broker_id)] = normalized
    for source_positions in snapshots.values():
        broker_managed_symbols.update(str(symbol).upper() for symbol in source_positions)

    aggregate: dict[str, dict[str, Any]] = {}
    for source_broker, source_positions in snapshots.items():
        for symbol, raw in (source_positions or {}).items():
            quantity = max(0.0, _number(raw.get("qty")))
            if quantity <= 0:
                continue
            entry = max(0.0, _number(raw.get("avg_entry")))
            current_price = max(0.0, _number(raw.get("current_price")))
            item = aggregate.setdefault(
                symbol,
                {
                    "qty": 0.0,
                    "notional": 0.0,
                    "high": 0.0,
                    "broker_positions": {},
                },
            )
            item["qty"] += quantity
            item["notional"] += quantity * entry
            item["high"] = max(
                item["high"],
                current_price,
                entry,
                _number((previous.get(symbol) or {}).get("high")),
            )
            item["broker_positions"][source_broker] = {
                "qty": quantity,
                "avg_entry": entry,
                "current_price": current_price,
            }
            if current_price > 0:
                self._prices[symbol] = current_price

    # Broker reconciliation is authoritative in live mode. Rebuild any open
    # position from broker snapshots so stale internal-only holdings disappear.
    merged = {
        symbol: deepcopy(position)
        for symbol, position in previous.items()
        if symbol not in broker_managed_symbols
    }
    for symbol, raw in aggregate.items():
        quantity = round(raw["qty"], 8)
        avg_entry = (
            round(raw["notional"] / quantity, 8) if quantity > 0 else 0.0
        )
        prior = previous.get(symbol) or {}
        metadata = {
            key: deepcopy(value)
            for key, value in prior.items()
            if key not in {
                "qty",
                "avg_entry",
                "high",
                "broker_positions",
                "reconciliation_required",
                "excess_sell_quantity",
            }
        }
        merged[symbol] = {
            **metadata,
            "qty": quantity,
            "avg_entry": avg_entry,
            "high": raw["high"],
            "broker_positions": raw["broker_positions"],
        }

    old_symbols = {
        symbol
        for symbol, position in previous.items()
        if symbol in broker_managed_symbols
        and _number((position or {}).get("qty")) > 0
    }
    new_symbols = {
        symbol
        for symbol, position in merged.items()
        if symbol in broker_managed_symbols
        and _number((position or {}).get("qty")) > 0
    }
    added = sorted(new_symbols - old_symbols)
    removed = sorted(old_symbols - new_symbols)
    updated = sorted(
        symbol
        for symbol in old_symbols & new_symbols
        if abs(
            _number((previous.get(symbol) or {}).get("qty"))
            - _number((merged.get(symbol) or {}).get("qty"))
        )
        > 1e-8
    )

    self._positions = merged
    now = datetime.now(timezone.utc)
    for symbol in removed:
        self._trailing_highs.pop(symbol, None)
        self._opening_bell_highs.pop(symbol, None)
        self._last_exit_ts[symbol] = now
    for symbol in new_symbols:
        position = self._positions[symbol]
        self._trailing_highs[symbol] = max(
            _number(self._trailing_highs.get(symbol)),
            _number(position.get("high")),
        )

    await rebuild_risk_exposure(self)
    await self.save_state()
    return {
        "broker_id": broker_id,
        "synced": len(normalized),
        "added": added,
        "updated": updated,
        "removed": removed,
        "skipped_external": [],
    }


EngineStateMixin.sync_positions_from_broker = sync_positions_from_broker
