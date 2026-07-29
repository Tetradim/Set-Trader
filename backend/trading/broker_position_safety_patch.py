"""Persist risk configuration and aggregate broker positions across accounts."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import deps
from trading.engine_state import EngineStateMixin


_ET = ZoneInfo("America/New_York")
_STATE_KEY = "execution_safety_state"


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


_original_save_state = EngineStateMixin.save_state
_original_load_state = EngineStateMixin.load_state


async def rebuild_risk_exposure(self) -> None:
    controls = self.risk_controls
    for limit in controls._exposure_limits.values():
        limit.current_notional = 0.0
        limit.current_position = 0.0
        limit.daily_pnl = 0.0
        limit.orders_count = 0
    controls._order_windows_by_limit = {}

    for symbol, position in (self._positions or {}).items():
        quantity = max(0.0, _number((position or {}).get("qty")))
        if quantity <= 0:
            continue
        if hasattr(self, "ensure_symbol_exposure_limit"):
            self.ensure_symbol_exposure_limit(symbol)
        price = max(
            0.0,
            _number((position or {}).get("avg_entry")),
            _number((self._prices or {}).get(symbol)),
        )
        notional = quantity * price
        controls.update_exposure(
            "portfolio", "global",
            notional_delta=notional,
            position_delta=quantity,
        )
        controls.update_exposure(
            "symbol", str(symbol).upper(),
            notional_delta=notional,
            position_delta=quantity,
        )

    try:
        start_et = datetime.now(_ET).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        start_utc = start_et.astimezone(timezone.utc).isoformat()
        rows = await deps.db.trades.find(
            {"timestamp": {"$gte": start_utc}},
            {"_id": 0, "symbol": 1, "pnl": 1},
        ).to_list(5000)
        for row in rows:
            pnl = _number(row.get("pnl"))
            symbol = str(row.get("symbol") or "").upper()
            if pnl == 0:
                continue
            controls.update_exposure("portfolio", "global", pnl_delta=pnl)
            if symbol:
                if hasattr(self, "ensure_symbol_exposure_limit"):
                    self.ensure_symbol_exposure_limit(symbol)
                controls.update_exposure("symbol", symbol, pnl_delta=pnl)
    except Exception as exc:
        deps.logger.warning("Could not rebuild current-day risk P&L: %s", exc)


async def save_state(self):
    await _original_save_state(self)
    await deps.db.settings.update_one(
        {"key": _STATE_KEY},
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


async def load_state(self):
    await _original_load_state(self)
    try:
        doc = await deps.db.settings.find_one(
            {"key": _STATE_KEY}, {"_id": 0}
        )
    except Exception as exc:
        deps.logger.warning("Could not load execution safety state: %s", exc)
        doc = None
    payload = (doc or {}).get("value") or {}
    self.risk_controls.load_state(payload.get("risk"))
    self._broker_positions_by_broker = deepcopy(
        payload.get("broker_positions") or {}
    )
    await rebuild_risk_exposure(self)


async def sync_positions_from_broker(self, broker_id: str) -> dict:
    broker_positions = await deps.broker_mgr.reconcile_positions(broker_id)
    if broker_positions is None:
        raise RuntimeError(f"Broker {broker_id} returned no position evidence")

    ticker_docs = await deps.db.tickers.find(
        {},
        {"_id": 0, "symbol": 1, "broker_ids": 1},
    ).to_list(1000)
    allowed_symbols = {
        str(doc.get("symbol") or "").upper()
        for doc in ticker_docs
        if doc.get("symbol")
    }
    broker_managed_symbols = {
        str(doc.get("symbol") or "").upper()
        for doc in ticker_docs
        if doc.get("symbol") and list(doc.get("broker_ids") or [])
    }

    normalized: dict[str, dict[str, float]] = {}
    skipped_external: list[str] = []
    for symbol, raw in (broker_positions or {}).items():
        sym = str(symbol or "").upper()
        if allowed_symbols and sym not in allowed_symbols:
            skipped_external.append(sym)
            continue
        quantity = max(0.0, _number((raw or {}).get("quantity")))
        if quantity <= 0:
            continue
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
    snapshots[str(broker_id)] = normalized

    previous = deepcopy(self._positions or {})
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
        merged[symbol] = {
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
        "skipped_external": sorted(skipped_external),
    }


EngineStateMixin.save_state = save_state
EngineStateMixin.load_state = load_state
EngineStateMixin.sync_positions_from_broker = sync_positions_from_broker
EngineStateMixin.rebuild_risk_exposure = rebuild_risk_exposure
