"""Resilience for post-persistence publication and order-marker failures.

The durable trade collection is the final idempotency source. A broker fill must
not be replayed merely because an Edge/WebSocket notification or the secondary
``broker_orders.applied_*`` update failed after the trade was inserted.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

import deps
from trading import live_order_reconciliation_patch as reconciliation
from trading import live_position_publication_patch as publication
from trading.live_truth_patch import (
    _number,
    _results_filled_qty,
    _results_weighted_price,
)
from trading.trade_accounting import TradeAccountingMixin


_current_record_trade = TradeAccountingMixin._record_trade
_current_apply_fill_delta = publication._apply_fill_delta_before_publication


def _snapshot(self, symbol: str) -> dict:
    return deepcopy(dict(getattr(self, "_positions", {}).get(symbol, {}) or {}))


async def _trade_is_persisted(trade_id: str) -> bool:
    collection = getattr(deps.db, "trades", None)
    if collection is None or not hasattr(collection, "find_one"):
        return False
    try:
        return bool(await collection.find_one({"id": trade_id}, {"_id": 1}))
    except Exception as exc:
        deps.logger.error(
            "Could not verify whether trade %s was persisted: %s",
            trade_id,
            exc,
        )
        return False


async def _recorded_order_fill_totals(
    broker_order_id: str,
    broker_id: str = "",
) -> tuple[float, float]:
    collection = getattr(deps.db, "trades", None)
    if (
        not broker_order_id
        or collection is None
        or not hasattr(collection, "find")
    ):
        return 0.0, 0.0

    try:
        cursor = collection.find(
            {"broker_results.broker_order_id": broker_order_id},
            {"_id": 0, "broker_results": 1},
        )
        rows = await cursor.to_list(1000)
    except Exception as exc:
        deps.logger.warning(
            "Could not derive applied fill totals for broker order %s: %s",
            broker_order_id,
            exc,
        )
        return 0.0, 0.0

    quantity = 0.0
    notional = 0.0
    for row in rows:
        for result in list((row or {}).get("broker_results") or []):
            order_id = str(
                result.get("broker_order_id")
                or result.get("order_id")
                or result.get("external_id")
                or ""
            )
            if order_id != broker_order_id:
                continue
            if broker_id and str(result.get("broker_id") or "") != broker_id:
                continue
            filled_qty = _number(
                result.get("filled_quantity") or result.get("filled_qty")
            )
            filled_price = _number(
                result.get("filled_price")
                or result.get("avg_fill_price")
                or result.get("average_fill_price")
            )
            if filled_qty <= 0 or filled_price <= 0:
                continue
            quantity += filled_qty
            notional += filled_qty * filled_price
    return round(quantity, 8), notional


def _reapply_persisted_position(self, trade, previous: dict) -> None:
    if str(getattr(trade, "trading_mode", "")).lower() != "live":
        return
    results = list(getattr(trade, "broker_results", None) or [])
    if any(bool(result.get("ledger_reconciliation")) for result in results):
        # Reconciliation updates the position before it calls _record_trade, so
        # the outer snapshot already represents the broker fill.
        self._positions[str(trade.symbol).upper()] = previous
        return

    symbol = str(trade.symbol).upper()
    side = str(trade.side).upper()
    filled_qty = round(_results_filled_qty(self, results), 8)
    fill_price = round(_results_weighted_price(self, results), 8)
    previous_qty = _number(previous.get("qty"))
    previous_entry = _number(previous.get("avg_entry"))
    previous_high = _number(previous.get("high"))

    if side == "BUY":
        self._positions[symbol] = {
            "qty": filled_qty,
            "avg_entry": fill_price,
            "high": max(previous_high, fill_price),
        }
        return

    remaining = round(previous_qty - filled_qty, 8)
    if remaining > 1e-8:
        self._positions[symbol] = {
            "qty": remaining,
            "avg_entry": previous_entry or _number(getattr(trade, "entry_price", 0)),
            "high": previous_high,
        }
    else:
        self._positions[symbol] = {
            "qty": 0.0,
            "avg_entry": 0.0,
            "high": 0.0,
            "reconciliation_required": remaining < -1e-8,
            "excess_sell_quantity": abs(remaining) if remaining < -1e-8 else 0.0,
        }
        self._trailing_highs.pop(symbol, None)


async def _record_trade_without_replaying_persisted_fill(self, trade):
    symbol = str(getattr(trade, "symbol", "")).upper()
    previous = _snapshot(self, symbol)
    try:
        return await _current_record_trade(self, trade)
    except Exception as exc:
        if not await _trade_is_persisted(str(getattr(trade, "id", ""))):
            raise

        # The broker fill and trade row are durable. Preserve matching position
        # state and turn downstream publication failure into an incident instead
        # of telling callers to resubmit the order.
        _reapply_persisted_position(self, trade, previous)
        self._last_broker_truth_trade = trade
        try:
            await self.save_state()
        except Exception as state_exc:
            deps.logger.critical(
                "Trade %s persisted but engine state could not be saved: %s",
                trade.id,
                state_exc,
                exc_info=True,
            )
        try:
            await deps.db.trades.update_one(
                {"id": trade.id},
                {
                    "$set": {
                        "publication_error": str(exc),
                        "publication_failed_at": datetime.now(timezone.utc).isoformat(),
                        "reconciliation_required": True,
                    }
                },
            )
        except Exception as update_exc:
            deps.logger.error(
                "Could not annotate persisted trade %s after publication failure: %s",
                trade.id,
                update_exc,
            )
        try:
            await publication._mark_child_orders_applied(self, trade)
        except Exception as marker_exc:
            deps.logger.critical(
                "Trade %s persisted but broker order marker update failed: %s",
                trade.id,
                marker_exc,
                exc_info=True,
            )
        deps.logger.critical(
            "Trade %s persisted after broker fill, but downstream publication failed; "
            "position was preserved and resubmission was suppressed: %s",
            trade.id,
            exc,
            exc_info=True,
        )
        return None


async def _apply_fill_delta_with_trade_dedup(
    self,
    order_doc: dict,
    broker_update: dict,
) -> float:
    broker_order_id = str(order_doc.get("broker_order_id") or "")
    broker_id = str(order_doc.get("broker_id") or "")
    recorded_qty, recorded_notional = await _recorded_order_fill_totals(
        broker_order_id,
        broker_id,
    )

    enriched = dict(order_doc)
    if recorded_qty > _number(enriched.get("applied_quantity")):
        enriched["applied_quantity"] = recorded_qty
        enriched["applied_notional"] = recorded_notional

    cumulative_qty = _number(broker_update.get("filled_quantity"))
    if cumulative_qty <= recorded_qty + 1e-8:
        collection = getattr(deps.db, "broker_orders", None)
        if collection is not None:
            try:
                await collection.update_one(
                    {
                        "intent_key": order_doc.get("intent_key"),
                        "broker_id": broker_id,
                        "durable_order_id": order_doc.get("durable_order_id"),
                    },
                    {
                        "$set": {
                            "applied_quantity": recorded_qty,
                            "applied_notional": recorded_notional,
                            "last_applied_at": datetime.now(timezone.utc).isoformat(),
                        }
                    },
                )
            except Exception as exc:
                deps.logger.warning(
                    "Broker order %s is already represented by durable trades, "
                    "but its applied marker still could not be repaired: %s",
                    broker_order_id,
                    exc,
                )
        return 0.0

    return await _current_apply_fill_delta(self, enriched, broker_update)


TradeAccountingMixin._record_trade = _record_trade_without_replaying_persisted_fill
publication._apply_fill_delta_before_publication = _apply_fill_delta_with_trade_dedup
reconciliation._apply_fill_delta = _apply_fill_delta_with_trade_dedup
