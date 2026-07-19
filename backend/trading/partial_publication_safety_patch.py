"""Apply live partial fills to the authoritative position exactly once."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from trading import live_position_publication_patch as publication
from trading import live_truth_patch as live_truth
from trading.broker_execution import LiveOrderExecutionError
from trading.execution_order_safety_patch import partial_contexts
from trading.trade_accounting import TradeAccountingMixin


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


async def record_trade_with_partial_truth(self, trade):
    if str(getattr(trade, "trading_mode", "")).lower() != "live":
        return await live_truth._original_record_trade(self, trade)

    results = list(getattr(trade, "broker_results", None) or [])
    if not results or not all(
        live_truth._result_confirmed(self, result) for result in results
    ):
        raise LiveOrderExecutionError(
            f"Refusing to record live trade for {trade.symbol} "
            "without complete broker fill evidence"
        )

    filled_qty = round(live_truth._results_filled_qty(self, results), 8)
    fill_price = round(live_truth._results_weighted_price(self, results), 8)
    if filled_qty <= 0 or fill_price <= 0:
        raise LiveOrderExecutionError(
            f"Refusing to record live trade for {trade.symbol}: "
            "invalid fill quantity/price"
        )

    symbol = str(trade.symbol).upper()
    side = str(trade.side).upper()
    context_side = "BUY" if side == "BUY" else "SELL"
    context = partial_contexts(self).pop(
        f"{symbol}:{context_side}", None
    )
    previous = (
        deepcopy(context.get("position") or {})
        if context
        else publication._position_snapshot(self, symbol)
    )
    current_qty = _number(previous.get("qty"))
    current_entry = _number(previous.get("avg_entry"))
    current_high = _number(previous.get("high"))

    trade.quantity = filled_qty
    trade.price = fill_price
    trade.total_value = round(filled_qty * fill_price, 2)

    if context and context_side == "BUY":
        new_qty = round(current_qty + filled_qty, 8)
        new_entry = (
            ((current_qty * current_entry) + (filled_qty * fill_price))
            / new_qty
            if new_qty > 0
            else fill_price
        )
        filled_buy = list(previous.get("buy_legs_filled") or [])
        leg_index = int(context.get("leg_index", -1))
        if leg_index >= 0 and leg_index not in filled_buy:
            filled_buy.append(leg_index)
        self._positions[symbol] = {
            **{
                key: deepcopy(value)
                for key, value in previous.items()
                if key not in {"qty", "avg_entry", "high"}
            },
            "qty": new_qty,
            "avg_entry": round(new_entry, 8),
            "high": max(current_high, fill_price, new_entry),
            "buy_legs_filled": sorted(filled_buy),
            "sell_legs_filled": list(
                previous.get("sell_legs_filled") or []
            ),
        }
        trade.buy_power = trade.total_value
    elif context and context_side == "SELL":
        entry = current_entry or _number(getattr(trade, "entry_price", 0))
        trade.entry_price = entry
        trade.pnl = round((fill_price - entry) * filled_qty, 2)
        remaining = round(current_qty - filled_qty, 8)
        filled_sell = list(previous.get("sell_legs_filled") or [])
        leg_index = int(context.get("leg_index", -1))
        if leg_index >= 0 and leg_index not in filled_sell:
            filled_sell.append(leg_index)
        if remaining > 1e-8:
            self._positions[symbol] = {
                **{
                    key: deepcopy(value)
                    for key, value in previous.items()
                    if key not in {"qty", "avg_entry", "high"}
                },
                "qty": remaining,
                "avg_entry": entry,
                "high": current_high,
                "buy_legs_filled": list(
                    previous.get("buy_legs_filled") or []
                ),
                "sell_legs_filled": sorted(filled_sell),
            }
        else:
            self._positions[symbol] = {
                "qty": 0.0,
                "avg_entry": 0.0,
                "high": 0.0,
            }
            self._trailing_highs.pop(symbol, None)
    elif side == "BUY":
        trade.buy_power = trade.total_value
        self._positions[symbol] = {
            "qty": filled_qty,
            "avg_entry": fill_price,
            "high": max(fill_price, current_high),
        }
    else:
        entry = _number(getattr(trade, "entry_price", 0)) or current_entry
        trade.entry_price = entry
        trade.pnl = round((fill_price - entry) * filled_qty, 2)
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
                "excess_sell_quantity": (
                    abs(remaining) if remaining < -1e-8 else 0.0
                ),
            }
            self._trailing_highs.pop(symbol, None)

    previous_last = getattr(self, "_last_broker_truth_trade", None)
    self._last_broker_truth_trade = trade
    try:
        result = await live_truth._original_record_trade(self, trade)
    except Exception:
        publication._restore_position(self, symbol, previous)
        self._last_broker_truth_trade = previous_last
        raise

    await publication._mark_child_orders_applied(self, trade)
    return result


TradeAccountingMixin._record_trade = record_trade_with_partial_truth
