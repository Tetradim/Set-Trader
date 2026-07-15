"""Final live position/fill publication ordering.

A broker fill is not fully useful to the ecosystem unless the position snapshot
published with it reflects that same fill. This module makes position mutation
happen before ``pulse.trade.recorded`` and Edge ``ORDER_FILLED`` publication,
while rolling memory back if trade persistence fails.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

import deps
from schemas import TradeRecord
from trading import live_order_reconciliation_patch as reconciliation
from trading.broker_execution import BrokerExecutionMixin, LiveOrderExecutionError
from trading.live_truth_patch import (
    _number,
    _original_record_trade,
    _result_confirmed,
    _results_filled_qty,
    _results_weighted_price,
)
from trading.trade_accounting import TradeAccountingMixin


def _position_snapshot(self, symbol: str) -> dict:
    return deepcopy(dict(getattr(self, "_positions", {}).get(symbol, {}) or {}))


def _restore_position(self, symbol: str, previous: dict) -> None:
    if previous:
        self._positions[symbol] = previous
    else:
        self._positions.pop(symbol, None)


async def _mark_child_orders_applied(self, trade: TradeRecord) -> None:
    collection = getattr(deps.db, "broker_orders", None)
    if collection is None:
        return
    now = datetime.now(timezone.utc).isoformat()
    for result in list(getattr(trade, "broker_results", None) or []):
        if result.get("ledger_reconciliation"):
            continue
        order_id = str(
            result.get("broker_order_id")
            or result.get("order_id")
            or result.get("external_id")
            or ""
        )
        if not order_id:
            continue
        qty = _number(result.get("filled_quantity") or result.get("filled_qty"))
        price = _number(
            result.get("filled_price")
            or result.get("avg_fill_price")
            or result.get("average_fill_price")
        )
        await collection.update_many(
            {"broker_order_id": order_id},
            {
                "$set": {
                    "applied_quantity": qty,
                    "applied_notional": qty * price,
                    "last_applied_at": now,
                }
            },
        )


async def _record_trade_with_position_truth(self, trade: TradeRecord):
    if str(getattr(trade, "trading_mode", "")).lower() != "live":
        return await _original_record_trade(self, trade)

    results = list(getattr(trade, "broker_results", None) or [])
    if not results or not all(_result_confirmed(self, result) for result in results):
        raise LiveOrderExecutionError(
            f"Refusing to record live trade for {trade.symbol} without complete broker fill evidence"
        )

    filled_qty = round(_results_filled_qty(self, results), 8)
    fill_price = round(_results_weighted_price(self, results), 8)
    if filled_qty <= 0 or fill_price <= 0:
        raise LiveOrderExecutionError(
            f"Refusing to record live trade for {trade.symbol}: invalid fill quantity/price"
        )

    symbol = str(trade.symbol).upper()
    side = str(trade.side).upper()
    ledger_reconciliation = any(
        bool(result.get("ledger_reconciliation")) for result in results
    )
    previous = _position_snapshot(self, symbol)
    current_qty = _number(previous.get("qty"))
    current_entry = _number(previous.get("avg_entry"))
    current_high = _number(previous.get("high"))

    trade.quantity = filled_qty
    trade.price = fill_price
    trade.total_value = round(filled_qty * fill_price, 2)

    if side == "BUY":
        trade.buy_power = trade.total_value
        if not ledger_reconciliation:
            # Normal buy callers set an optimistic quote-based position before
            # recording. Replace it with the broker's complete fill, do not add
            # the optimistic quantity a second time.
            self._positions[symbol] = {
                "qty": filled_qty,
                "avg_entry": fill_price,
                "high": max(fill_price, current_high),
            }
    else:
        entry = _number(getattr(trade, "entry_price", 0)) or current_entry
        trade.entry_price = entry
        trade.pnl = round((fill_price - entry) * filled_qty, 2)
        if not ledger_reconciliation:
            remaining = round(current_qty - filled_qty, 8)
            if remaining > 1e-8:
                self._positions[symbol] = {
                    "qty": remaining,
                    "avg_entry": current_entry or entry,
                    "high": current_high,
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

    previous_last = getattr(self, "_last_broker_truth_trade", None)
    self._last_broker_truth_trade = trade
    try:
        result = await _original_record_trade(self, trade)
    except Exception:
        _restore_position(self, symbol, previous)
        self._last_broker_truth_trade = previous_last
        raise

    await _mark_child_orders_applied(self, trade)
    return result


async def _apply_fill_delta_before_publication(
    self,
    order_doc: dict,
    broker_update: dict,
) -> float:
    cumulative_qty = _number(broker_update.get("filled_quantity"))
    cumulative_avg = _number(
        broker_update.get("filled_price") or broker_update.get("avg_fill_price")
    )
    applied_qty = _number(order_doc.get("applied_quantity"))
    applied_notional = _number(order_doc.get("applied_notional"))
    delta_qty = round(max(0.0, cumulative_qty - applied_qty), 8)
    if delta_qty <= 0:
        return 0.0

    cumulative_notional = cumulative_qty * cumulative_avg
    delta_notional = cumulative_notional - applied_notional
    if cumulative_avg <= 0 or delta_notional <= 0:
        raise RuntimeError(
            f"Broker fill for {order_doc.get('symbol')} has quantity but no usable fill price"
        )
    delta_price = delta_notional / delta_qty

    symbol = str(order_doc.get("symbol") or "").upper()
    side = str(order_doc.get("side") or "").upper()
    broker_id = str(order_doc.get("broker_id") or "")
    broker_order_id = str(order_doc.get("broker_order_id") or "")
    previous = _position_snapshot(self, symbol)
    current_qty = _number(previous.get("qty"))
    current_entry = _number(previous.get("avg_entry"))
    current_high = _number(previous.get("high"))

    result = {
        "broker_id": broker_id,
        "status": "filled",
        "broker_order_id": broker_order_id,
        "filled_quantity": delta_qty,
        "filled_price": delta_price,
        "ledger_reconciliation": True,
    }

    if side == "BUY":
        new_qty = round(current_qty + delta_qty, 8)
        new_entry = (
            ((current_qty * current_entry) + (delta_qty * delta_price)) / new_qty
            if new_qty > 0
            else delta_price
        )
        self._positions[symbol] = {
            "qty": new_qty,
            "avg_entry": round(new_entry, 8),
            "high": max(current_high, delta_price, new_entry),
        }
        trade = TradeRecord(
            symbol=symbol,
            side="BUY",
            price=delta_price,
            quantity=delta_qty,
            reason="Broker reconciliation fill",
            order_type=str(order_doc.get("order_type") or ""),
            rule_mode="BROKER_RECONCILIATION",
            total_value=round(delta_qty * delta_price, 2),
            buy_power=round(delta_qty * delta_price, 2),
            trading_mode="live",
            broker_results=[result],
        )
    elif side == "SELL":
        if current_qty + 1e-8 < delta_qty:
            raise RuntimeError(
                f"Broker sell fill exceeds local reconciled position for {symbol}: "
                f"{delta_qty} > {current_qty}"
            )
        remaining = round(max(0.0, current_qty - delta_qty), 8)
        if remaining > 0:
            self._positions[symbol] = {
                "qty": remaining,
                "avg_entry": current_entry,
                "high": current_high,
            }
        else:
            self._positions[symbol] = {"qty": 0.0, "avg_entry": 0.0, "high": 0.0}
            self._trailing_highs.pop(symbol, None)
        pnl = round((delta_price - current_entry) * delta_qty, 2)
        trade = TradeRecord(
            symbol=symbol,
            side="SELL",
            price=delta_price,
            quantity=delta_qty,
            reason="Broker reconciliation fill",
            pnl=pnl,
            order_type=str(order_doc.get("order_type") or ""),
            rule_mode="BROKER_RECONCILIATION",
            entry_price=current_entry,
            total_value=round(delta_qty * delta_price, 2),
            trading_mode="live",
            broker_results=[result],
        )
    else:
        raise RuntimeError(f"Unsupported broker-order side: {side}")

    try:
        await self._record_trade(trade)
    except Exception:
        _restore_position(self, symbol, previous)
        raise

    if side == "SELL":
        ticker = await deps.db.tickers.find_one({"symbol": symbol}, {"_id": 0})
        await self._update_profit(
            symbol,
            trade.pnl,
            bool((ticker or {}).get("compound_profits", True)),
        )

    await deps.db.broker_orders.update_one(
        {
            "intent_key": order_doc.get("intent_key"),
            "broker_id": broker_id,
            "durable_order_id": order_doc.get("durable_order_id"),
        },
        {
            "$set": {
                "applied_quantity": cumulative_qty,
                "applied_notional": cumulative_notional,
                "last_applied_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )
    await self.save_state()
    return delta_qty


async def _reconcile_all_fill_deltas(self, symbol: str | None = None) -> dict:
    collection = getattr(deps.db, "broker_orders", None)
    if collection is None:
        return {"checked": 0, "applied": 0, "unresolved": 0}

    query: dict = {
        "$or": [
            {
                "status": {
                    "$in": sorted(
                        self._BROKER_PENDING_STATUSES | self._BROKER_PARTIAL_STATUSES
                    )
                }
            },
            {
                "$expr": {
                    "$gt": [
                        {"$ifNull": ["$filled_quantity", 0]},
                        {"$ifNull": ["$applied_quantity", 0]},
                    ]
                }
            },
        ]
    }
    if symbol:
        query["symbol"] = symbol.upper()

    docs = await collection.find(query, {"_id": 0}).sort("created_at", 1).to_list(500)
    applied = 0.0
    unresolved = 0

    for doc in docs:
        broker_id = str(doc.get("broker_id") or "")
        order_id = str(doc.get("broker_order_id") or "")
        adapter = (
            deps.broker_mgr.get_adapter(broker_id)
            if hasattr(deps.broker_mgr, "get_adapter")
            else None
        )
        update = {
            "status": str(doc.get("status") or "unknown").lower(),
            "broker_order_id": order_id,
            "filled_quantity": _number(doc.get("filled_quantity")),
            "filled_price": _number(doc.get("avg_fill_price")),
            "error": str(doc.get("error") or ""),
        }

        if update["status"] in (
            self._BROKER_PENDING_STATUSES | self._BROKER_PARTIAL_STATUSES
        ):
            if not adapter or not hasattr(adapter, "get_order_status"):
                unresolved += 1
                continue
            update = await adapter.get_order_status(order_id)
            await collection.update_one(
                {
                    "intent_key": doc.get("intent_key"),
                    "broker_id": broker_id,
                    "durable_order_id": doc.get("durable_order_id"),
                },
                {
                    "$set": {
                        "status": str(update.get("status") or "unknown").lower(),
                        "filled_quantity": _number(update.get("filled_quantity")),
                        "avg_fill_price": _number(
                            update.get("filled_price") or update.get("avg_fill_price")
                        ),
                        "error": str(update.get("error") or ""),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                },
            )

        cumulative_qty = _number(update.get("filled_quantity"))
        if cumulative_qty > _number(doc.get("applied_quantity")):
            applied += await _apply_fill_delta_before_publication(self, doc, update)

        status = str(update.get("status") or "").lower()
        if status in self._BROKER_PENDING_STATUSES | self._BROKER_PARTIAL_STATUSES:
            unresolved += 1

    return {"checked": len(docs), "applied": applied, "unresolved": unresolved}


TradeAccountingMixin._record_trade = _record_trade_with_position_truth
reconciliation._apply_fill_delta = _apply_fill_delta_before_publication
reconciliation._reconcile_live_orders = _reconcile_all_fill_deltas
BrokerExecutionMixin.reconcile_live_orders = _reconcile_all_fill_deltas
