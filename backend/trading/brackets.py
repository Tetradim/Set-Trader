from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Tuple
from zoneinfo import ZoneInfo

import deps
from schemas import TradeRecord
from resilience import CircuitOpenError
from trading.broker_execution import LiveOrderExecutionError


class BracketManagementMixin:
    def _previous_bracket_snapshot(self, ticker_doc, buy_target, sell_target, timestamp):
        return {
            "buy_target": buy_target,
            "sell_target": sell_target,
            "buy_offset": ticker_doc.get("buy_offset"),
            "sell_offset": ticker_doc.get("sell_offset"),
            "buy_percent": ticker_doc.get("buy_percent", True),
            "sell_percent": ticker_doc.get("sell_percent", True),
            "timestamp": timestamp.isoformat(),
        }

    async def _set_absolute_bracket(
        self, sym, ticker_doc, buy_target, sell_target, new_buy, new_sell, *, timestamp=None
    ):
        now = timestamp or datetime.now(timezone.utc)
        updates = {
            "buy_offset": round(new_buy, 2),
            "buy_percent": False,
            "sell_offset": round(new_sell, 2),
            "sell_percent": False,
            "prev_bracket": self._previous_bracket_snapshot(ticker_doc, buy_target, sell_target, now),
        }
        await deps.db.tickers.update_one({"symbol": sym}, {"$set": updates})
        doc = await deps.db.tickers.find_one({"symbol": sym}, {"_id": 0})
        if doc:
            await deps.ws_manager.broadcast({"type": "TICKER_UPDATED", "ticker": doc})
        return updates

    async def _auto_rebracket(self, sym, ticker_doc, price, buy_target, sell_target):
        """Auto-rebracket to current price when price drifts beyond threshold.
        
        Args:
            sym: Symbol
            ticker_doc: Full ticker config from DB
            price: Current market price
            buy_target: Current buy target (computed from offsets)
            sell_target: Current sell target (computed from offsets)
        
        Bugs fixed:
        - Now handles both percentage and absolute offsets correctly
        - Added minimum drift check to prevent micro-rebracketing
        - Added revert to previous bracket feature
        """
        threshold = ticker_doc.get("rebracket_threshold", 2.0)
        spread = ticker_doc.get("rebracket_spread", 0.80)
        cooldown = ticker_doc.get("rebracket_cooldown", 0)
        lookback = max(2, ticker_doc.get("rebracket_lookback", 10))
        buffer = ticker_doc.get("rebracket_buffer", 0.10)
        
        # Minimum price movement to trigger rebracket (prevent micro-rebracketing)
        min_drift = ticker_doc.get("rebracket_min_drift", 0.50)
        
        now = datetime.now(timezone.utc)
        
        # Cooldown check - since last rebracket
        if cooldown > 0:
            last_rb = self._last_rebracket_ts.get(sym)
            if last_rb and (now - last_rb).total_seconds() < cooldown:
                return
        
        # Get history for drift detection
        hist = self._recent_prices.get(sym, [])
        hist.append(price)
        if len(hist) > lookback:
            hist = hist[-lookback:]
        self._recent_prices[sym] = hist
        
        # Calculate drift from current bracket
        # Buy drift: how far price has moved UP from buy target
        # Sell drift: how far price has moved DOWN from sell target
        buy_drift = price - buy_target
        sell_drift = sell_target - price
        
        # Check if price has drifted enough (in either direction)
        # AND meets minimum drift requirement
        drifted_up = False
        drifted_down = False
        
        if buy_drift > threshold and buy_drift > min_drift:
            # Price moved up past buy target + threshold
            drifted_up = True
        elif sell_drift > threshold and sell_drift > min_drift:
            # Price moved down past sell target + threshold
            drifted_down = True
        
        if not (drifted_up or drifted_down):
            return
        
        # Calculate new bracket based on recent low/high
        old_buy = buy_target
        old_sell = sell_target
        
        if drifted_up:
            # Price moved UP - new bracket should be higher
            new_buy = round(min(hist) - buffer, 2)
            new_sell = round(new_buy + spread, 2)
            direction = "UP"
        else:
            # Price moved DOWN - new bracket should be lower  
            new_buy = round(max(hist) - buffer, 2)
            new_sell = round(new_buy + spread, 2)
            direction = "DOWN"
        
        await self._set_absolute_bracket(
            sym, ticker_doc, buy_target, sell_target, new_buy, new_sell, timestamp=now
        )
        
        self._last_rebracket_ts[sym] = now
        deps.logger.info(
            f"REBRACKET: {sym} drifted {direction} — new bracket ${new_buy} / ${new_sell} "
            f"(was ${old_buy} / ${old_sell}) [lookback={lookback}, buffer=${buffer}, min_drift=${min_drift}]"
        )

        with deps.tracer.start_as_current_span("ticker.rebracket", attributes={
            "rebracket.symbol": sym, "rebracket.direction": direction,
            "rebracket.old_buy": old_buy, "rebracket.old_sell": old_sell,
            "rebracket.new_buy": new_buy, "rebracket.new_sell": new_sell,
            "rebracket.price": price,
        }):
            pass

        try:
            await deps.telegram_service._broadcast_alert(
                f"REBRACKET {sym}\nPrice drifted {direction}: ${price:.2f}\n"
                f"Old bracket: ${old_buy:.2f} / ${old_sell:.2f}\n"
                f"New bracket: ${new_buy:.2f} / ${new_sell:.2f}\nSpread: ${spread:.2f}"
            )
        except Exception:
            pass

        self._recent_prices[sym] = []
        await self._persist_trade_state()

    async def revert_bracket(self, sym: str) -> dict:
        """Revert to previous bracket if available.
        
        Returns:
            dict with success status and message
        """
        ticker = await deps.db.tickers.find_one({"symbol": sym}, {"_id": 0})
        if not ticker:
            return {"success": False, "error": "Ticker not found"}
        
        prev = ticker.get("prev_bracket")
        if not prev:
            return {"success": False, "error": "No previous bracket to revert to"}
        
        if "buy_offset" in prev and "sell_offset" in prev:
            updates = {
                "buy_offset": prev.get("buy_offset"),
                "sell_offset": prev.get("sell_offset"),
                "buy_percent": prev.get("buy_percent", True),
                "sell_percent": prev.get("sell_percent", True),
            }
            old_buy = prev.get("buy_target", prev.get("buy_offset"))
            old_sell = prev.get("sell_target", prev.get("sell_offset"))
        else:
            # Legacy prev_bracket snapshots only stored target prices.
            old_buy = prev.get("buy_target")
            old_sell = prev.get("sell_target")
            if not old_buy or not old_sell:
                return {"success": False, "error": "Could not restore previous bracket"}
            price = await deps.price_service.get_price(sym)
            is_pct = ticker.get("sell_percent", True)
            if is_pct:
                updates = {
                    "buy_offset": round((old_buy / price - 1) * 100, 2),
                    "sell_offset": round((old_sell / price - 1) * 100, 2),
                }
            else:
                updates = {"buy_offset": old_buy, "sell_offset": old_sell}

        if old_buy and old_sell:
            await deps.db.tickers.update_one(
                {"symbol": sym},
                {"$set": updates, "$unset": {"prev_bracket": ""}},
            )
            doc = await deps.db.tickers.find_one({"symbol": sym}, {"_id": 0})
            if doc:
                await deps.ws_manager.broadcast({"type": "TICKER_UPDATED", "ticker": doc})
            
            deps.logger.info(f"REVERT: {sym} reverted to ${old_buy} / ${old_sell}")
            return {"success": True, "reverted_to": {"buy": old_buy, "sell": old_sell}}
        
        return {"success": False, "error": "Could not restore previous bracket"}

    async def _evaluate_partial_fills(
        self, ticker_doc, sym, price, avg, pos, entry,
        effective_power, broker_ids, broker_allocs,
        stop_target, is_stop_pct, stop_otype, compound,
    ):
        buy_legs = ticker_doc.get("buy_legs", [])
        sell_legs = ticker_doc.get("sell_legs", [])
        is_paper = self.is_paper_trading()

        filled_buy = pos.get("buy_legs_filled", [])
        filled_sell = pos.get("sell_legs_filled", [])
        buying_paused = ticker_doc.get("buying_paused", False)

        # --- PARTIAL BUY LEGS ---
        if buy_legs and not buying_paused and not self._is_reentry_cooldown_active(sym, ticker_doc):
            for i, leg in enumerate(buy_legs):
                if i in filled_buy:
                    continue
                leg_offset = leg.get("offset", 0)
                leg_is_pct = leg.get("is_percent", True)
                leg_alloc_pct = leg.get("alloc_pct", 0)
                if leg_alloc_pct <= 0:
                    continue

                trigger = round(avg * (1 + leg_offset / 100), 2) if leg_is_pct else round(leg_offset, 2)

                if price <= trigger:
                    leg_power = round(effective_power * leg_alloc_pct / 100, 2)
                    qty = round(leg_power / price, 4)
                    if qty <= 0:
                        continue

                    # Broker routing
                    broker_results = []
                    try:
                        broker_results = await self._place_live_order_or_raise(
                            sym=sym,
                            broker_ids=broker_ids,
                            broker_allocs=broker_allocs,
                            action_label=f"PARTIAL_BUY_LEG_{i+1}",
                            order_template={
                                "symbol": sym, "side": "BUY", "order_type": "LIMIT",
                                "price": price, "limit_price": trigger,
                            },
                        )
                    except LiveOrderExecutionError as exc:
                        deps.logger.warning(str(exc))
                        return

                    # Update position with weighted average
                    old_qty = pos.get("qty", 0)
                    old_entry = pos.get("avg_entry", 0)
                    new_qty = round(old_qty + qty, 4)
                    new_entry = round(((old_entry * old_qty) + (price * qty)) / new_qty, 2) if new_qty > 0 else price

                    filled_buy = list(filled_buy) + [i]
                    self._positions[sym] = {
                        "qty": new_qty, "avg_entry": new_entry,
                        "buy_legs_filled": filled_buy,
                        "sell_legs_filled": filled_sell,
                    }
                    pos = self._positions[sym]
                    entry = new_entry

                    trade = TradeRecord(
                        symbol=sym, side="BUY", price=price, quantity=qty,
                        reason=f"[PARTIAL {i+1}/{len(buy_legs)}] Leg {i+1} filled @ ${price:.2f} (trigger ${trigger:.2f}, {leg_alloc_pct}% of power)",
                        order_type="LIMIT", rule_mode="PERCENT" if leg_is_pct else "DOLLAR",
                        target_price=trigger,
                        total_value=round(price * qty, 2),
                        buy_power=leg_power, avg_price=avg,
                        trading_mode="paper" if is_paper or not broker_ids else "live",
                        broker_results=broker_results,
                    )
                    await self._record_trade(trade)

        # --- STOP LOSS (applies to entire remaining position) ---
        if pos.get("qty", 0) > 0 and entry > 0:
            current_stop = round(entry * (1 + ticker_doc.get("stop_offset", -6.0) / 100), 2) if is_stop_pct else round(ticker_doc.get("stop_offset", 0), 2)
            effective_stop = current_stop
            if ticker_doc.get("halve_stop_at_open", False) and self._is_opening_window(30, ticker_doc):
                stop_distance = entry - current_stop
                effective_stop = round(entry - (stop_distance * 0.5), 2)
            should_stop = price <= effective_stop
            if should_stop:
                pnl = round((price - entry) * pos["qty"], 2)
                broker_results = []
                try:
                    broker_results = await self._place_live_order_or_raise(
                        sym=sym,
                        broker_ids=broker_ids,
                        broker_allocs=broker_allocs,
                        action_label="PARTIAL_STOP",
                        order_template=self._triggered_exit_order_template(
                            symbol=sym,
                            order_type=stop_otype,
                            price=price,
                            quantity=pos["qty"],
                        ),
                    )
                except LiveOrderExecutionError as exc:
                    deps.logger.warning(str(exc))
                    return
                stop_note = f" [0.5x halved from ${current_stop:.2f}]" if effective_stop != current_stop else ""
                trade = TradeRecord(
                    symbol=sym, side="STOP", price=price, quantity=pos["qty"],
                    reason=f"[STOP] Full position stopped @ ${price:.2f} (stop ${effective_stop:.2f}){stop_note}",
                    pnl=pnl, order_type="STOP",
                    entry_price=entry, target_price=current_stop,
                    total_value=round(price * pos["qty"], 2),
                    buy_power=effective_power,
                    trading_mode="paper" if is_paper or not broker_ids else "live",
                    broker_results=broker_results,
                )
                await self._record_trade(trade)
                self._positions[sym] = {"qty": 0, "avg_entry": 0, "high": 0}
                self._trailing_highs.pop(sym, None)
                await self._update_profit(sym, pnl, compound)
                return

        # --- PARTIAL SELL LEGS ---
        if sell_legs and pos.get("qty", 0) > 0 and entry > 0:
            for i, leg in enumerate(sell_legs):
                if i in filled_sell:
                    continue
                leg_offset = leg.get("offset", 0)
                leg_is_pct = leg.get("is_percent", True)
                leg_alloc_pct = leg.get("alloc_pct", 0)
                if leg_alloc_pct <= 0:
                    continue

                trigger = round(entry * (1 + leg_offset / 100), 2) if leg_is_pct else round(leg_offset, 2)

                if price >= trigger:
                    current_qty = pos.get("qty", 0)
                    sell_qty = round(current_qty * leg_alloc_pct / 100, 4)
                    sell_qty = min(sell_qty, current_qty)
                    if sell_qty <= 0:
                        continue

                    pnl = round((price - entry) * sell_qty, 2)

                    broker_results = []
                    try:
                        broker_results = await self._place_live_order_or_raise(
                            sym=sym,
                            broker_ids=broker_ids,
                            broker_allocs=broker_allocs,
                            action_label=f"PARTIAL_SELL_LEG_{i+1}",
                            order_template={
                                "symbol": sym, "side": "SELL", "order_type": "LIMIT",
                                "price": price, "quantity": sell_qty, "limit_price": trigger,
                            },
                        )
                    except LiveOrderExecutionError as exc:
                        deps.logger.warning(str(exc))
                        return

                    remaining = round(current_qty - sell_qty, 4)
                    filled_sell = list(filled_sell) + [i]
                    self._positions[sym] = {
                        "qty": remaining, "avg_entry": entry,
                        "buy_legs_filled": filled_buy,
                        "sell_legs_filled": filled_sell,
                    }
                    pos = self._positions[sym]

                    trade = TradeRecord(
                        symbol=sym, side="SELL", price=price, quantity=sell_qty,
                        reason=f"[PARTIAL {i+1}/{len(sell_legs)}] Leg {i+1} filled @ ${price:.2f} (trigger ${trigger:.2f}, {leg_alloc_pct}% of position)",
                        pnl=pnl, order_type="LIMIT",
                        rule_mode="PERCENT" if leg_is_pct else "DOLLAR",
                        entry_price=entry, target_price=trigger,
                        total_value=round(price * sell_qty, 2),
                        buy_power=effective_power,
                        trading_mode="paper" if is_paper or not broker_ids else "live",
                        broker_results=broker_results,
                    )
                    await self._record_trade(trade)
                    await self._update_profit(sym, pnl, compound)

            # If all sell legs filled and no position remains, clear
            if pos.get("qty", 0) <= 0.0001:
                self._positions[sym] = {"qty": 0, "avg_entry": 0, "high": 0}
                self._trailing_highs.pop(sym, None)
                await self._persist_trade_state()

        # --- TRAILING STOP for remaining partial-fill position ---
        if ticker_doc.get("trailing_enabled", False) and pos.get("qty", 0) > 0 and entry > 0:
            trail_pct = ticker_doc.get("trailing_percent", 2.0)
            trail_is_pct = ticker_doc.get("trailing_percent_mode", True)
            trail_otype = ticker_doc.get("trailing_order_type", "limit")
            if ticker_doc.get("lock_trailing_at_open", False) and self._is_opening_window(30, ticker_doc):
                return

            if sym not in self._trailing_highs:
                self._trailing_highs[sym] = price
                high = price
                await self._persist_trade_state()
            else:
                high = self._trailing_highs[sym]
            if price > high:
                self._trailing_highs[sym] = price
                high = price
                await self._persist_trade_state()

            trail_stop = round(high * (1 - trail_pct / 100), 2) if trail_is_pct else round(high - trail_pct, 2)
            should_trail = price <= trail_stop
            if should_trail:
                exec_price = price
                pnl = round((exec_price - entry) * pos["qty"], 2)
                order_label = "MKT" if trail_otype == "market" else "LMT"
                broker_results = []
                try:
                    broker_results = await self._place_live_order_or_raise(
                        sym=sym,
                        broker_ids=broker_ids,
                        broker_allocs=broker_allocs,
                        action_label="PARTIAL_TRAILING_STOP",
                        order_template=self._triggered_exit_order_template(
                            symbol=sym,
                            order_type=trail_otype,
                            price=exec_price,
                            quantity=pos["qty"],
                        ),
                    )
                except LiveOrderExecutionError as exc:
                    deps.logger.warning(str(exc))
                    return

                trade = TradeRecord(
                    symbol=sym, side="TRAILING_STOP", price=exec_price,
                    quantity=pos["qty"],
                    reason=f"[{order_label}] Trailing stop hit ${trail_stop} (high ${high})",
                    pnl=pnl, order_type=trail_otype.upper(),
                    rule_mode="PERCENT" if trail_is_pct else "DOLLAR",
                    entry_price=entry, target_price=trail_stop,
                    total_value=round(exec_price * pos["qty"], 2),
                    buy_power=effective_power, avg_price=avg,
                    stop_target=stop_target,
                    trail_high=high, trail_trigger=trail_stop, trail_value=trail_pct,
                    trail_mode="PERCENT" if trail_is_pct else "DOLLAR",
                    trading_mode="paper" if is_paper or not broker_ids else "live",
                    broker_results=broker_results,
                )
                await self._record_trade(trade)
                self._positions[sym] = {"qty": 0, "avg_entry": 0, "high": 0}
                self._trailing_highs.pop(sym, None)
                await self._update_profit(sym, pnl, compound)
                return

        # --- AUTO REBRACKET for partial fills ---
        # Rebracket should still work when no position is held
        rebracket_on = ticker_doc.get("auto_rebracket", False)
        if rebracket_on and pos.get("qty", 0) == 0:
            # Need to compute buy_target for rebracket check
            avg_price = avg or price
            buy_off = ticker_doc.get("buy_offset", -3.0)
            is_buy_pct = ticker_doc.get("buy_percent", True)
            sell_off = ticker_doc.get("sell_offset", 2.0)
            is_sell_pct = ticker_doc.get("sell_percent", True)
            buy_target = round(avg_price * (1 + buy_off / 100), 2) if is_buy_pct else round(buy_off, 2)
            sell_target = round(avg_price * (1 + sell_off / 100), 2) if is_sell_pct else round(sell_off, 2)
            await self._auto_rebracket(sym, ticker_doc, price, buy_target, sell_target)
