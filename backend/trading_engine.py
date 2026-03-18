"""Core trading engine — evaluates tickers, places orders, manages positions."""
from datetime import datetime, timezone, timedelta
from typing import Dict

import deps
from schemas import TradeRecord


class TradingEngine:
    TRADE_COOLDOWN_SECS = 30

    def __init__(self):
        self.running = False
        self.paused = False
        self.simulate_24_7 = False
        self._prices: Dict[str, float] = {}
        self._positions: Dict[str, dict] = {}
        self._trailing_highs: Dict[str, float] = {}
        self._last_trade_ts: Dict[str, datetime] = {}
        self._recent_prices: Dict[str, list] = {}
        self._last_rebracket_ts: Dict[str, datetime] = {}

    async def save_state(self):
        await deps.db.settings.update_one(
            {"key": "engine_state"},
            {"$set": {"value": {
                "running": self.running,
                "paused": self.paused,
                "simulate_24_7": self.simulate_24_7,
            }}},
            upsert=True,
        )

    async def load_state(self):
        doc = await deps.db.settings.find_one({"key": "engine_state"}, {"_id": 0})
        if doc and doc.get("value"):
            v = doc["value"]
            self.running = v.get("running", False)
            self.paused = v.get("paused", False)
            self.simulate_24_7 = v.get("simulate_24_7", False)
            deps.logger.info(f"Engine state restored: running={self.running}, paused={self.paused}, sim247={self.simulate_24_7}")

    def is_market_open(self) -> bool:
        if self.simulate_24_7:
            return True
        now = datetime.now(timezone(timedelta(hours=-5)))
        if now.weekday() >= 5:
            return False
        hour, minute = now.hour, now.minute
        if hour < 9 or (hour == 9 and minute < 30):
            return False
        if hour >= 16:
            return False
        return True

    # ------------------------------------------------------------------
    # evaluate_ticker — the heart of the trading logic
    # ------------------------------------------------------------------
    async def evaluate_ticker(self, ticker_doc: dict):
        sym = ticker_doc["symbol"]
        if not ticker_doc.get("enabled", False):
            return
        if ticker_doc.get("auto_stopped", False):
            return

        now = datetime.now(timezone.utc)
        last = self._last_trade_ts.get(sym)
        if last and (now - last).total_seconds() < self.TRADE_COOLDOWN_SECS:
            return

        with deps.tracer.start_as_current_span("ticker.evaluate", attributes={
            "ticker.symbol": sym,
            "ticker.buy_power": ticker_doc.get("base_power", 0),
            "ticker.enabled": ticker_doc.get("enabled", True),
        }):
            price = await deps.price_service.get_price(sym)
            self._prices[sym] = price
            avg = await deps.price_service.get_avg_price(sym, ticker_doc.get("avg_days", 30))

        buy_off = ticker_doc.get("buy_offset", -3.0)
        is_buy_pct = ticker_doc.get("buy_percent", True)
        buy_otype = ticker_doc.get("buy_order_type", "limit")
        sell_off = ticker_doc.get("sell_offset", 3.0)
        is_sell_pct = ticker_doc.get("sell_percent", True)
        sell_otype = ticker_doc.get("sell_order_type", "limit")
        stop_off = ticker_doc.get("stop_offset", -6.0)
        is_stop_pct = ticker_doc.get("stop_percent", True)
        stop_otype = ticker_doc.get("stop_order_type", "limit")
        trailing = ticker_doc.get("trailing_enabled", False)
        trail_pct = ticker_doc.get("trailing_percent", 2.0)
        trail_is_pct = ticker_doc.get("trailing_percent_mode", True)
        trail_otype = ticker_doc.get("trailing_order_type", "limit")
        compound = ticker_doc.get("compound_profits", True)
        base_power = ticker_doc.get("base_power", 100.0)

        buy_target = round(avg * (1 + buy_off / 100), 2) if is_buy_pct else round(buy_off, 2)
        pos = self._positions.get(sym, {"qty": 0, "avg_entry": 0})
        entry = pos.get("avg_entry", 0)

        if pos["qty"] > 0 and entry > 0:
            sell_target = round(entry * (1 + sell_off / 100), 2) if is_sell_pct else round(sell_off, 2)
            stop_target = round(entry * (1 + stop_off / 100), 2) if is_stop_pct else round(stop_off, 2)
        else:
            sell_target = round(avg * (1 + sell_off / 100), 2) if is_sell_pct else round(sell_off, 2)
            stop_target = round(avg * (1 + stop_off / 100), 2) if is_stop_pct else round(stop_off, 2)

        # --- BUY ---
        if pos["qty"] == 0:
            should_buy = (buy_otype == "market") or (price <= buy_target)
            if should_buy:
                exec_price = price
                qty = round(base_power / exec_price, 4)
                if qty > 0:
                    is_paper = self.simulate_24_7
                    broker_ids = ticker_doc.get("broker_ids", [])
                    broker_allocs = ticker_doc.get("broker_allocations", {})
                    broker_results = []

                    if not is_paper and broker_ids:
                        broker_results = await deps.broker_mgr.place_orders_for_ticker(
                            broker_ids=broker_ids, allocations=broker_allocs,
                            order_template={
                                "symbol": sym, "side": "BUY", "order_type": buy_otype.upper(),
                                "price": exec_price,
                                "limit_price": buy_target if buy_otype == "limit" else None,
                            },
                        )
                        any_success = any(r.get("status") not in ("error",) for r in broker_results)
                        if not any_success and broker_results:
                            deps.logger.warning(f"All broker orders failed for {sym} BUY — skipping position tracking")
                            return

                    self._positions[sym] = {"qty": qty, "avg_entry": exec_price}
                    order_label = "MKT" if buy_otype == "market" else "LMT"
                    trade = TradeRecord(
                        symbol=sym, side="BUY", price=exec_price, quantity=qty,
                        reason=f"[{order_label}] Price ${exec_price} {'(market)' if buy_otype == 'market' else f'<= buy target ${buy_target}'}",
                        order_type=buy_otype.upper(),
                        rule_mode="PERCENT" if is_buy_pct else "DOLLAR",
                        target_price=buy_target,
                        total_value=round(exec_price * qty, 2),
                        buy_power=base_power, avg_price=avg,
                        sell_target=sell_target, stop_target=stop_target,
                        trading_mode="paper" if is_paper or not broker_ids else "live",
                        broker_results=broker_results,
                    )
                    await self._record_trade(trade)

        # --- SELL / STOP / TRAILING ---
        elif pos["qty"] > 0:
            entry = pos["avg_entry"]

            wait_day = ticker_doc.get("wait_day_after_buy", False)
            if wait_day:
                last_buy = await deps.db.trades.find_one(
                    {"symbol": sym, "side": "BUY"}, {"_id": 0, "timestamp": 1}, sort=[("timestamp", -1)]
                )
                if last_buy:
                    buy_date = datetime.fromisoformat(last_buy["timestamp"]).date()
                    today = datetime.now(timezone.utc).date()
                    if buy_date >= today:
                        return

            if trailing:
                high = self._trailing_highs.get(sym, price)
                if price > high:
                    self._trailing_highs[sym] = price
                    high = price
                trail_stop = round(high * (1 - trail_pct / 100), 2) if trail_is_pct else round(high - trail_pct, 2)
                should_trail = (trail_otype == "market") or (price <= trail_stop)
                if should_trail:
                    exec_price = price
                    pnl = round((exec_price - entry) * pos["qty"], 2)
                    order_label = "MKT" if trail_otype == "market" else "LMT"
                    is_paper = self.simulate_24_7
                    broker_ids = ticker_doc.get("broker_ids", [])
                    broker_allocs = ticker_doc.get("broker_allocations", {})
                    broker_results = []
                    if not is_paper and broker_ids:
                        broker_results = await deps.broker_mgr.place_orders_for_ticker(
                            broker_ids=broker_ids, allocations=broker_allocs,
                            order_template={
                                "symbol": sym, "side": "SELL", "order_type": "STOP",
                                "price": exec_price, "quantity": pos["qty"], "stop_price": trail_stop,
                            },
                        )
                    trade = TradeRecord(
                        symbol=sym, side="TRAILING_STOP", price=exec_price,
                        quantity=pos["qty"],
                        reason=f"[{order_label}] Trailing stop hit ${trail_stop} (high ${high})",
                        pnl=pnl, order_type=trail_otype.upper(),
                        rule_mode="PERCENT" if is_sell_pct else "DOLLAR",
                        entry_price=entry, target_price=trail_stop,
                        total_value=round(exec_price * pos["qty"], 2),
                        buy_power=base_power, avg_price=avg,
                        sell_target=sell_target, stop_target=stop_target,
                        trail_high=high, trail_trigger=trail_stop, trail_value=trail_pct,
                        trail_mode="PERCENT" if trail_is_pct else "DOLLAR",
                        trading_mode="paper" if is_paper or not broker_ids else "live",
                        broker_results=broker_results,
                    )
                    await self._record_trade(trade)
                    self._positions[sym] = {"qty": 0, "avg_entry": 0}
                    self._trailing_highs.pop(sym, None)
                    await self._update_profit(sym, pnl, compound)
                    return

            should_sell = (sell_otype == "market") or (price >= sell_target)
            if should_sell:
                exec_price = price
                pnl = round((exec_price - entry) * pos["qty"], 2)
                order_label = "MKT" if sell_otype == "market" else "LMT"
                is_paper = self.simulate_24_7
                broker_ids = ticker_doc.get("broker_ids", [])
                broker_allocs = ticker_doc.get("broker_allocations", {})
                broker_results = []
                if not is_paper and broker_ids:
                    broker_results = await deps.broker_mgr.place_orders_for_ticker(
                        broker_ids=broker_ids, allocations=broker_allocs,
                        order_template={
                            "symbol": sym, "side": "SELL", "order_type": sell_otype.upper(),
                            "price": exec_price, "quantity": pos["qty"],
                            "limit_price": sell_target if sell_otype == "limit" else None,
                        },
                    )
                trade = TradeRecord(
                    symbol=sym, side="SELL", price=exec_price, quantity=pos["qty"],
                    reason=f"[{order_label}] Price ${exec_price} {'(market)' if sell_otype == 'market' else f'>= sell target ${sell_target}'}",
                    pnl=pnl, order_type=sell_otype.upper(),
                    rule_mode="PERCENT" if is_sell_pct else "DOLLAR",
                    entry_price=entry, target_price=sell_target,
                    total_value=round(exec_price * pos["qty"], 2),
                    buy_power=base_power, avg_price=avg,
                    sell_target=sell_target, stop_target=stop_target,
                    trading_mode="paper" if is_paper or not broker_ids else "live",
                    broker_results=broker_results,
                )
                await self._record_trade(trade)
                self._positions[sym] = {"qty": 0, "avg_entry": 0}
                self._trailing_highs.pop(sym, None)
                await self._update_profit(sym, pnl, compound)

            elif price <= stop_target or stop_otype == "market":
                should_stop = (stop_otype == "market") or (price <= stop_target)
                if should_stop:
                    exec_price = price
                    pnl = round((exec_price - entry) * pos["qty"], 2)
                    order_label = "MKT" if stop_otype == "market" else "LMT"
                    is_paper = self.simulate_24_7
                    broker_ids = ticker_doc.get("broker_ids", [])
                    broker_allocs = ticker_doc.get("broker_allocations", {})
                    broker_results = []
                    if not is_paper and broker_ids:
                        broker_results = await deps.broker_mgr.place_orders_for_ticker(
                            broker_ids=broker_ids, allocations=broker_allocs,
                            order_template={
                                "symbol": sym, "side": "SELL", "order_type": "STOP",
                                "price": exec_price, "quantity": pos["qty"], "stop_price": stop_target,
                            },
                        )
                    trade = TradeRecord(
                        symbol=sym, side="STOP", price=exec_price, quantity=pos["qty"],
                        reason=f"[{order_label}] Stop-loss hit ${exec_price} {'(market)' if stop_otype == 'market' else f'<= ${stop_target}'}",
                        pnl=pnl, order_type=stop_otype.upper(),
                        rule_mode="PERCENT" if is_stop_pct else "DOLLAR",
                        entry_price=entry, target_price=stop_target,
                        total_value=round(exec_price * pos["qty"], 2),
                        buy_power=base_power, avg_price=avg,
                        sell_target=sell_target, stop_target=stop_target,
                        trading_mode="paper" if is_paper or not broker_ids else "live",
                        broker_results=broker_results,
                    )
                    await self._record_trade(trade)
                    self._positions[sym] = {"qty": 0, "avg_entry": 0}
                    self._trailing_highs.pop(sym, None)
                    await self._update_profit(sym, pnl, compound)

        # --- AUTO REBRACKET ---
        rebracket_on = ticker_doc.get("auto_rebracket", False)
        if rebracket_on and pos["qty"] == 0:
            await self._auto_rebracket(sym, ticker_doc, price, buy_target, sell_target)

    # ------------------------------------------------------------------
    async def _auto_rebracket(self, sym, ticker_doc, price, buy_target, sell_target):
        threshold = ticker_doc.get("rebracket_threshold", 2.0)
        spread = ticker_doc.get("rebracket_spread", 0.80)
        cooldown = ticker_doc.get("rebracket_cooldown", 0)
        lookback = max(2, ticker_doc.get("rebracket_lookback", 10))
        buffer = ticker_doc.get("rebracket_buffer", 0.10)

        now = datetime.now(timezone.utc)
        if cooldown > 0:
            last_rb = self._last_rebracket_ts.get(sym)
            if last_rb and (now - last_rb).total_seconds() < cooldown:
                return

        hist = self._recent_prices.get(sym, [])
        hist.append(price)
        if len(hist) > lookback:
            hist = hist[-lookback:]
        self._recent_prices[sym] = hist

        drifted_up = price > sell_target + threshold
        drifted_down = price < buy_target - threshold
        if drifted_up or drifted_down:
            recent_low = min(hist)
            new_buy = round(recent_low - buffer, 2)
            new_sell = round(new_buy + spread, 2)
            old_buy = buy_target
            old_sell = sell_target

            await deps.db.tickers.update_one(
                {"symbol": sym},
                {"$set": {"buy_offset": new_buy, "buy_percent": False, "sell_offset": new_sell, "sell_percent": False}}
            )
            doc = await deps.db.tickers.find_one({"symbol": sym}, {"_id": 0})
            if doc:
                await deps.ws_manager.broadcast({"type": "TICKER_UPDATED", "ticker": doc})

            self._last_rebracket_ts[sym] = now
            direction = "UP" if drifted_up else "DOWN"
            deps.logger.info(
                f"REBRACKET: {sym} drifted {direction} — new bracket ${new_buy} / ${new_sell} "
                f"(was ${old_buy} / ${old_sell}) [lookback={lookback}, buffer=${buffer}, cooldown={cooldown}s]"
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

    # ------------------------------------------------------------------
    async def _record_trade(self, trade: TradeRecord):
        with deps.tracer.start_as_current_span("trade.execute", attributes={
            "trade.id": trade.id, "trade.symbol": trade.symbol, "trade.side": trade.side,
            "trade.order_type": trade.order_type, "trade.price": trade.price,
            "trade.quantity": trade.quantity, "trade.total_value": trade.total_value,
            "trade.pnl": trade.pnl, "trade.rule_mode": trade.rule_mode,
        }) as span:
            doc = trade.model_dump()
            await deps.db.trades.insert_one(doc)
            self._last_trade_ts[trade.symbol] = datetime.now(timezone.utc)
            pnl_str = f" P&L: ${trade.pnl:+.2f}" if trade.pnl != 0 else ""
            entry_str = f" entry=${trade.entry_price:.2f}" if trade.entry_price > 0 else ""
            deps.logger.info(
                f"TRADE: {trade.order_type} {trade.side} {trade.symbol} @ ${trade.price:.2f} x{trade.quantity:.4f}"
                f" | {trade.rule_mode} mode | target=${trade.target_price:.2f}{entry_str}"
                f" | value=${trade.total_value:.2f} | power=${trade.buy_power:.2f}{pnl_str}"
            )
            clean = {k: v for k, v in doc.items() if k != "_id"}
            await deps.ws_manager.broadcast({"type": "TRADE", "trade": clean})
            if trade.pnl < 0:
                span.set_attribute("trade.loss", True)
                span.add_event("loss_trade", {"pnl": trade.pnl, "symbol": trade.symbol})
            try:
                await deps.telegram_service.send_trade_alert(clean)
            except Exception:
                pass
            if trade.pnl < 0:
                self._write_loss_log(trade)

    def _write_loss_log(self, trade: TradeRecord):
        try:
            ts = datetime.fromisoformat(trade.timestamp)
            date_str = ts.strftime("%Y-%m-%d")
            time_str = ts.strftime("%H-%M-%S")
            log_dir = deps.ROOT_DIR / "trade_logs" / "losses" / date_str
            log_dir.mkdir(parents=True, exist_ok=True)

            filename = f"{trade.symbol}_{trade.side}_{time_str}_{trade.id[:8]}.txt"
            filepath = log_dir / filename
            pct_change = ((trade.price / trade.entry_price - 1) * 100) if trade.entry_price > 0 else 0

            lines = [
                f"{'='*60}", f"  LOSS TRADE LOG — {trade.symbol}", f"{'='*60}", "",
                f"Trade ID:       {trade.id}",
                f"Timestamp:      {ts.strftime('%Y-%m-%d %H:%M:%S UTC')}",
                f"Symbol:         {trade.symbol}", f"Side:           {trade.side}", "",
                "--- ORDER INFO ---", f"Order Type:     {trade.order_type}", f"Rule Mode:      {trade.rule_mode}", "",
                "--- PRICES ---",
                f"Fill Price:     ${trade.price:.2f}",
                f"Entry Price:    ${trade.entry_price:.2f}" if trade.entry_price > 0 else "Entry Price:    N/A (legacy trade)",
                f"Target Price:   ${trade.target_price:.2f}" if trade.target_price > 0 else "Target Price:   N/A",
                f"Avg Price (MA): ${trade.avg_price:.2f}" if trade.avg_price > 0 else "Avg Price (MA): N/A", "",
                "--- POSITION ---",
                f"Quantity:       {trade.quantity:.4f}", f"Total Value:    ${trade.total_value:.2f}",
                f"Buy Power:      ${trade.buy_power:.2f}", "",
                "--- TARGETS AT TIME OF TRADE ---",
                f"Sell Target:    ${trade.sell_target:.2f}" if trade.sell_target > 0 else "Sell Target:    N/A",
                f"Stop Target:    ${trade.stop_target:.2f}" if trade.stop_target > 0 else "Stop Target:    N/A", "",
                "--- P&L ---",
                f"P&L:            ${trade.pnl:+.2f}",
                f"% Change:       {pct_change:+.2f}%" if trade.entry_price > 0 else "% Change:       N/A", "",
            ]
            if trade.side == "TRAILING_STOP":
                lines += [
                    "--- TRAILING STOP DETAILS ---",
                    f"Trail High:     ${trade.trail_high:.2f}", f"Trail Trigger:  ${trade.trail_trigger:.2f}",
                    f"Trail Value:    {trade.trail_value}" + ("%" if trade.trail_mode == "PERCENT" else f" (${trade.trail_value:.2f})"),
                    f"Trail Mode:     {trade.trail_mode}", "",
                ]
            lines += ["--- REASON ---", f"{trade.reason}", "", f"{'='*60}"]
            filepath.write_text("\n".join(lines))
            deps.logger.info(f"LOSS LOG: Written to {filepath}")
        except Exception as e:
            deps.logger.error(f"Failed to write loss log for {trade.symbol}: {e}")

    async def _update_profit(self, symbol: str, pnl: float, compound: bool = False):
        await deps.db.profits.update_one(
            {"symbol": symbol},
            {"$inc": {"total_pnl": pnl, "trade_count": 1},
             "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )
        if compound and pnl > 0:
            await deps.db.tickers.update_one({"symbol": symbol}, {"$inc": {"base_power": round(pnl, 2)}})
            doc = await deps.db.tickers.find_one({"symbol": symbol}, {"_id": 0})
            if doc:
                await deps.ws_manager.broadcast({"type": "TICKER_UPDATED", "ticker": doc})
                deps.logger.info(f"COMPOUND: {symbol} buy power increased by ${pnl:.2f} to ${doc.get('base_power', 0):.2f}")
        if pnl < 0:
            await self._check_auto_stop(symbol)

    async def _check_auto_stop(self, symbol: str):
        ticker_doc = await deps.db.tickers.find_one({"symbol": symbol}, {"_id": 0})
        if not ticker_doc:
            return
        max_daily = ticker_doc.get("max_daily_loss", 0)
        max_consec = ticker_doc.get("max_consecutive_losses", 0)
        reason = ""

        if max_daily > 0:
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            pipeline = [
                {"$match": {"symbol": symbol, "pnl": {"$lt": 0}, "timestamp": {"$gte": today_start}}},
                {"$group": {"_id": None, "total_loss": {"$sum": "$pnl"}}},
            ]
            result = await deps.db.trades.aggregate(pipeline).to_list(1)
            if result:
                daily_loss = abs(result[0]["total_loss"])
                if daily_loss >= max_daily:
                    reason = f"Daily loss ${daily_loss:.2f} exceeded limit ${max_daily:.2f}"

        if not reason and max_consec > 0:
            recent = await deps.db.trades.find(
                {"symbol": symbol, "side": {"$ne": "BUY"}}, {"_id": 0, "pnl": 1}
            ).sort("timestamp", -1).limit(max_consec).to_list(max_consec)
            if len(recent) >= max_consec and all(t.get("pnl", 0) < 0 for t in recent):
                reason = f"{max_consec} consecutive losing trades"

        if reason:
            await deps.db.tickers.update_one(
                {"symbol": symbol}, {"$set": {"auto_stopped": True, "auto_stop_reason": reason, "enabled": False}}
            )
            doc = await deps.db.tickers.find_one({"symbol": symbol}, {"_id": 0})
            if doc:
                await deps.ws_manager.broadcast({"type": "TICKER_UPDATED", "ticker": doc})
            deps.logger.warning(f"AUTO-STOP: {symbol} — {reason}")
            try:
                await deps.telegram_service._broadcast_alert(
                    f"AUTO-STOP {symbol}\n{reason}\nTrading disabled. Manual re-enable required."
                )
            except Exception:
                pass
