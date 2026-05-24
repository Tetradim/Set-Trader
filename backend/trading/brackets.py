from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Tuple
from zoneinfo import ZoneInfo

import deps
from schemas import TradeRecord
from resilience import CircuitOpenError


class BracketManagementMixin:
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
        
        # Save previous bracket for potential revert
        prev_bracket = {
            "buy_target": buy_target,
            "sell_target": sell_target,
            "timestamp": now.isoformat(),
        }
        
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
        
        # Handle offset mode (percentage vs absolute)
        is_pct = ticker_doc.get("sell_percent", True)
        
        if is_pct:
            # Store as percentage offsets relative to current price
            new_buy_pct = round((new_buy / price - 1) * 100, 2)
            new_sell_pct = round((new_sell / price - 1) * 100, 2)
            updates = {
                "buy_offset": new_buy_pct,
                "buy_percent": True,
                "sell_offset": new_sell_pct,
                "sell_percent": True,
            }
        else:
            # Store as absolute prices
            updates = {
                "buy_offset": new_buy,
                "buy_percent": False,
                "sell_offset": new_sell,
                "sell_percent": False,
            }
        
        # Also add previous bracket for revert capability
        updates["prev_bracket"] = prev_bracket
        
        await deps.db.tickers.update_one(
            {"symbol": sym},
            {"$set": updates}
        )
        doc = await deps.db.tickers.find_one({"symbol": sym}, {"_id": 0})
        if doc:
            await deps.ws_manager.broadcast({"type": "TICKER_UPDATED", "ticker": doc})
        
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
        
        # Restore previous bracket
        old_buy = prev.get("buy_target")
        old_sell = prev.get("sell_target")
        
        if old_buy and old_sell:
            price = await deps.price_service.get_price(sym)
            is_pct = ticker.get("sell_percent", True)
            
            if is_pct:
                buy_pct = round((old_buy / price - 1) * 100, 2)
                sell_pct = round((old_sell / price - 1) * 100, 2)
                updates = {"buy_offset": buy_pct, "sell_offset": sell_pct}
            else:
                updates = {"buy_offset": old_buy, "sell_offset": old_sell}
            
            # Clear prev_bracket
            updates.pop("prev_bracket", None)
            
            await deps.db.tickers.update_one({"symbol": sym}, {"$set": updates})
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
        is_paper = self.simulate_24_7

        filled_buy = pos.get("buy_legs_filled", [])
        filled_sell = pos.get("sell_legs_filled", [])

        # --- PARTIAL BUY LEGS ---
        if buy_legs:
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
                    if not is_paper and broker_ids:
                        broker_results = await deps.broker_mgr.place_orders_for_ticker(
                            broker_ids=broker_ids, allocations=broker_allocs,
                            order_template={
                                "symbol": sym, "side": "BUY", "order_type": "LIMIT",
                                "price": price, "limit_price": trigger,
                            },
                        )

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
            should_stop = (stop_otype == "market") or (price <= current_stop)
            if should_stop:
                pnl = round((price - entry) * pos["qty"], 2)
                broker_results = []
                if not is_paper and broker_ids:
                    broker_results = await deps.broker_mgr.place_orders_for_ticker(
                        broker_ids=broker_ids, allocations=broker_allocs,
                        order_template={
                            "symbol": sym, "side": "SELL", "order_type": "STOP",
                            "price": price, "quantity": pos["qty"], "stop_price": current_stop,
                        },
                    )
                trade = TradeRecord(
                    symbol=sym, side="STOP", price=price, quantity=pos["qty"],
                    reason=f"[STOP] Full position stopped @ ${price:.2f} (stop ${current_stop:.2f})",
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
                    if not is_paper and broker_ids:
                        broker_results = await deps.broker_mgr.place_orders_for_ticker(
                            broker_ids=broker_ids, allocations=broker_allocs,
                            order_template={
                                "symbol": sym, "side": "SELL", "order_type": "LIMIT",
                                "price": price, "quantity": sell_qty, "limit_price": trigger,
                            },
                        )

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

        # --- AUTO REBRACKET for partial fills ---
        # Rebracket should still work when no position is held
        rebracket_on = ticker_doc.get("auto_rebracket", False)
        if rebracket_on and pos.get("qty", 0) == 0:
            # Need to compute buy_target for rebracket check
            avg = ticker_doc.get("avg_price", price)
            buy_off = ticker_doc.get("buy_offset", -3.0)
            is_buy_pct = ticker_doc.get("buy_percent", True)
            sell_off = ticker_doc.get("sell_offset", 2.0)
            is_sell_pct = ticker_doc.get("sell_percent", True)
            buy_target = round(avg * (1 + buy_off / 100), 2) if is_buy_pct else round(buy_off, 2)
            sell_target = round(avg * (1 + sell_off / 100), 2) if is_sell_pct else round(sell_off, 2)
            await self._auto_rebracket(sym, ticker_doc, price, buy_target, sell_target)
