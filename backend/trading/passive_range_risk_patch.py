"""Range-break protection for passive range scalping.

A passive sell can remain unfilled while the market moves lower. This wrapper
uses the ticker's existing stop configuration as a mandatory exit trigger for
an open passive-range position. It cancels the resting sell before submitting a
live market exit and refuses to send the exit if cancellation cannot be
confirmed, preventing an accidental double-sell.
"""

from __future__ import annotations

from datetime import datetime, timezone

import deps
from schemas import TradeRecord
from trading.broker_execution import LiveOrderExecutionError
from trading.price_precision import bracket_target, decimal_to_float, infer_tick_size
from trading import passive_range_patch as passive


_ORIGINAL_EVALUATE_PASSIVE_RANGE = passive._evaluate_passive_range


def _number(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


async def _stop_exit(self, ticker_doc: dict, state: dict, current_price: float, stop_target: float) -> bool:
    symbol = state["symbol"]
    quantity = _number(state.get("position_qty"))
    entry = _number(state.get("entry_price"))
    if quantity <= 0 or entry <= 0:
        return False

    is_paper = passive._is_paper(self, ticker_doc)
    broker_result = {
        "broker_id": "paper",
        "broker_order_id": f"paper-stop:{state.get('cycle_id', symbol)}",
        "order_id": "",
        "status": "filled",
        "filled_price": current_price,
        "filled_quantity": quantity,
        "error": "",
    }
    exit_price = current_price
    exit_quantity = quantity

    if not is_paper:
        broker_id, _ = passive._active_broker(ticker_doc)
        if not broker_id:
            return False
        sell_order = state.get("sell_order") or {}
        if sell_order.get("broker_order_id"):
            cancelled = await passive._cancel_live_order(self, broker_id, sell_order)
            if not cancelled:
                deps.logger.error(
                    "Passive stop for %s blocked: resting sell cancellation was not confirmed",
                    symbol,
                )
                return False

        try:
            results = await self._place_live_order_or_raise(
                sym=symbol,
                broker_ids=[broker_id],
                broker_allocs=ticker_doc.get("broker_allocations") or {},
                action_label="PASSIVE_RANGE_STOP",
                order_template={
                    "symbol": symbol,
                    "side": "SELL",
                    "order_type": "MARKET",
                    "price": current_price,
                    "quantity": quantity,
                },
            )
        except LiveOrderExecutionError as exc:
            deps.logger.error("Passive stop execution failed for %s: %s", symbol, exc)
            state.update({"phase": "LONG", "sell_order": None})
            await passive._persist_state(state)
            return False
        if not results:
            return False
        broker_result = dict(results[0])
        exit_quantity = _number(
            broker_result.get("filled_quantity") or broker_result.get("filled_qty")
        )
        exit_price = _number(
            broker_result.get("filled_price") or broker_result.get("avg_fill_price")
        )
        if exit_quantity <= 0 or exit_price <= 0:
            deps.logger.error("Passive stop for %s lacked terminal fill evidence", symbol)
            return False

    sold = min(quantity, exit_quantity)
    pnl = (exit_price - entry) * sold
    trade = TradeRecord(
        symbol=symbol,
        side="STOP",
        price=exit_price,
        quantity=sold,
        reason=f"[PASSIVE RANGE] Stop triggered at ${current_price} <= ${stop_target}",
        pnl=round(pnl, 2),
        order_type="MARKET",
        rule_mode="PASSIVE_RANGE",
        entry_price=entry,
        target_price=stop_target,
        total_value=round(exit_price * sold, 2),
        buy_power=_number(ticker_doc.get("base_power")),
        stop_target=stop_target,
        trading_mode="paper" if is_paper else "live",
        broker_results=[] if is_paper else [broker_result],
    )
    await self._record_trade(trade)
    await self._update_profit(symbol, round(pnl, 2), ticker_doc.get("compound_profits", True))

    remaining = round(max(0.0, quantity - sold), 8)
    self._positions[symbol] = {
        "qty": remaining,
        "avg_entry": entry if remaining > 0 else 0.0,
        "high": entry if remaining > 0 else 0.0,
    }
    state.update(
        {
            "position_qty": remaining,
            "sell_order": None,
            "last_exit_at": datetime.now(timezone.utc).isoformat(),
            "touch_count": 0,
        }
    )
    if remaining > 0:
        state["phase"] = "LONG"
        await passive._persist_state(state)
        return True

    await passive._complete_cycle(
        self,
        ticker_doc=ticker_doc,
        state=state,
        exit_price=exit_price,
        exit_quantity=sold,
        pnl=pnl,
        exit_reason="stop",
    )
    state.update({"phase": "COOLDOWN", "entry_price": 0.0})
    self._last_exit_ts[symbol] = datetime.now(timezone.utc)
    await passive._persist_state(state)
    return True


async def _evaluate_passive_range_with_stop(self, ticker_doc: dict) -> None:
    # Let the passive evaluator obtain and store the current price once. Stop
    # protection then evaluates that same observation, avoiding a second quote
    # request and ensuring paper tests/live decisions share one market snapshot.
    await _ORIGINAL_EVALUATE_PASSIVE_RANGE(self, ticker_doc)

    symbol = str(ticker_doc.get("symbol") or "").upper()
    if not symbol:
        return
    state = await passive._load_state(self, symbol)
    if state.get("phase") not in {"LONG", "SELL_WORKING"} or _number(state.get("position_qty")) <= 0:
        return

    current_price = _number(getattr(self, "_prices", {}).get(symbol))
    entry = _number(state.get("entry_price"))
    if current_price <= 0 or entry <= 0:
        return

    tick = infer_tick_size(current_price, ticker_doc.get("price_tick_size", 0))
    stop_target = decimal_to_float(
        bracket_target(
            entry,
            ticker_doc.get("stop_offset", -6.0),
            is_percent=bool(ticker_doc.get("stop_percent", True)),
            tick_size=tick,
            side="stop",
        )
    )
    if stop_target > 0 and current_price <= stop_target:
        await _stop_exit(self, ticker_doc, state, current_price, stop_target)


passive._evaluate_passive_range = _evaluate_passive_range_with_stop
