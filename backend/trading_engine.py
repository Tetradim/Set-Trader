"""Core trading engine — evaluates tickers, places orders, manages positions."""
from datetime import datetime, timezone
from typing import Dict
from zoneinfo import ZoneInfo

import deps
from schemas import TradeRecord
from resilience import CircuitOpenError

_ET = ZoneInfo("America/New_York")   # US Eastern — DST-aware (EDT/EST auto)


class TradingEngine:
    TRADE_COOLDOWN_SECS = 30

    def __init__(self):
        self.running = False
        self.paused = False
        self.simulate_24_7 = False
        self.market_hours_only = True
        # Auto mode switching
        self.live_during_market_hours = False
        self.paper_after_hours = False
        self._last_mode_check: datetime = None
        self._last_market_state: bool = None  # Track market open/close transitions
        
        self._prices: Dict[str, float] = {}
        self._positions: Dict[str, dict] = {}
        self._trailing_highs: Dict[str, float] = {}
        self._last_trade_ts: Dict[str, datetime] = {}
        self._recent_prices: Dict[str, list] = {}
        self._last_rebracket_ts: Dict[str, datetime] = {}
        self._pending_sells: Dict[str, dict] = {}  # symbol -> {limit_price, qty, entry}
        # Opening Bell Mode tracking
        self._opening_bell_highs: Dict[str, float] = {}  # symbol -> opening session high
        self._opening_bell_rebracket_done: Dict[str, str] = {}  # symbol -> date string when rebracket was done

    async def save_state(self):
        await deps.db.settings.update_one(
            {"key": "engine_state"},
            {"$set": {"value": {
                "running": self.running,
                "paused": self.paused,
                "simulate_24_7": self.simulate_24_7,
                "market_hours_only": self.market_hours_only,
                "live_during_market_hours": self.live_during_market_hours,
                "paper_after_hours": self.paper_after_hours,
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
            self.market_hours_only = v.get("market_hours_only", True)
            self.live_during_market_hours = v.get("live_during_market_hours", False)
            self.paper_after_hours = v.get("paper_after_hours", False)
            deps.logger.info(f"Engine state restored: running={self.running}, paused={self.paused}, sim247={self.simulate_24_7}, mkt_hrs={self.market_hours_only}, live_mkt={self.live_during_market_hours}, paper_ah={self.paper_after_hours}")

    def check_auto_mode_switch(self) -> bool:
        """Check and apply auto mode switching based on market hours. 
        Only switches on market open/close TRANSITIONS, not continuously.
        Returns True if mode changed."""
        if not self.live_during_market_hours and not self.paper_after_hours:
            return False
        
        market_open = self._is_actual_market_hours()
        
        # Only switch on transition (market state changed)
        if self._last_market_state is not None and market_open == self._last_market_state:
            return False  # No transition, don't override
        
        self._last_market_state = market_open
        mode_changed = False
        
        if market_open and self.live_during_market_hours:
            # Market just opened and user wants live trading during market hours
            if self.simulate_24_7:
                self.simulate_24_7 = False
                mode_changed = True
                deps.logger.info("AUTO MODE: Switched to LIVE trading (market opened)")
        elif not market_open and self.paper_after_hours:
            # Market just closed and user wants paper trading after hours
            if not self.simulate_24_7:
                self.simulate_24_7 = True
                mode_changed = True
                deps.logger.info("AUTO MODE: Switched to PAPER trading (market closed)")
        
        return mode_changed

    def _is_actual_market_hours(self) -> bool:
        """Check if we're in actual US market hours (ignoring simulate_24_7). DST-aware."""
        now = datetime.now(_ET)
        if now.weekday() >= 5:
            return False
        hour, minute = now.hour, now.minute
        if hour < 9 or (hour == 9 and minute < 30):
            return False
        if hour >= 16:
            return False
        return True

    # ------------------------------------------------------------------
    # Market-aware helpers (support international exchanges)
    # ------------------------------------------------------------------

    def _get_market(self, ticker_doc: dict):
        """Get the MarketConfig for a ticker (auto-detected from symbol suffix if not set)."""
        from markets import MARKETS, detect_market_from_symbol
        market_code = ticker_doc.get("market") or detect_market_from_symbol(ticker_doc.get("symbol", ""))
        return MARKETS.get(market_code, MARKETS["US"])

    def _is_ticker_market_open(self, ticker_doc: dict) -> bool:
        """Check if the market for this specific ticker is currently open.

        simulate_24_7 bypasses the "market closed" gate (paper trading runs 24/7)
        but still blocks structured lunch breaks for markets that have them
        (CN_SS, CN_SZ, HK). No broker would fill an order during Shanghai/HK
        lunch regardless of mode, so we guard against those misfires.
        """
        market = self._get_market(ticker_doc)

        if self.simulate_24_7:
            # Respect lunch breaks even in simulate mode
            if market.lunch_break and market.is_in_lunch_break():
                return False
            return True

        if not self.market_hours_only:
            return True

        return market.is_open_now()

    def _is_opening_window(self, minutes: int = 30, ticker_doc: dict = None) -> bool:
        """True during the first `minutes` after market open (DST-aware).
        Uses the ticker's specific market when ticker_doc is provided."""
        if ticker_doc is not None:
            return self._get_market(ticker_doc).is_opening_window(minutes)
        # Legacy fallback: US ET (DST-aware)
        now = datetime.now(_ET)
        if now.weekday() >= 5:
            return False
        market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
        elapsed = (now - market_open).total_seconds()
        return 0 <= elapsed <= minutes * 60

    def _is_past_opening_window(self, minutes: int = 30, ticker_doc: dict = None) -> bool:
        """True when past the opening window but still within market hours (DST-aware)."""
        if ticker_doc is not None:
            return self._get_market(ticker_doc).is_past_opening_window(minutes)
        # Legacy fallback: US ET (DST-aware)
        now = datetime.now(_ET)
        if now.weekday() >= 5:
            return False
        market_open  = now.replace(hour=9,  minute=30, second=0, microsecond=0)
        market_close = now.replace(hour=16, minute=0,  second=0, microsecond=0)
        elapsed = (now - market_open).total_seconds()
        return elapsed > minutes * 60 and now < market_close

    async def manual_sell(self, symbol: str, order_type: str, limit_price: float = 0) -> dict:
        """Execute a manual sell from the Positions tab.
        order_type: 'market' (immediate) or 'limit' (pending).
        Returns trade result dict."""
        sym = symbol.upper()
        pos = self._positions.get(sym)
        if not pos or pos["qty"] <= 0:
            return {"error": f"No open position for {sym}"}

        qty = pos["qty"]
        entry = pos["avg_entry"]

        if order_type == "limit" and limit_price > 0:
            # Store as pending limit sell — engine will execute when price >= limit_price
            self._pending_sells[sym] = {
                "limit_price": limit_price,
                "qty": qty,
                "entry": entry,
            }
            await deps.ws_manager.broadcast({
                "type": "PENDING_SELL",
                "symbol": sym,
                "limit_price": limit_price,
                "qty": qty,
            })
            deps.logger.info(f"PENDING LIMIT SELL: {sym} @ ${limit_price:.2f} x{qty:.4f}")
            return {
                "status": "pending",
                "symbol": sym,
                "order_type": "limit",
                "limit_price": limit_price,
                "quantity": qty,
            }

        # Market sell — execute immediately
        price = self._prices.get(sym) or await deps.price_service.get_price(sym)
        return await self._execute_sell(sym, price, qty, entry, "MARKET", "Manual market sell")

    async def cancel_pending_sell(self, symbol: str) -> dict:
        """Cancel a pending limit sell order."""
        sym = symbol.upper()
        removed = self._pending_sells.pop(sym, None)
        if removed:
            await deps.ws_manager.broadcast({"type": "PENDING_SELL_CANCELLED", "symbol": sym})
            return {"status": "cancelled", "symbol": sym}
        return {"error": f"No pending sell for {sym}"}

    async def check_pending_sells(self):
        """Called by the trading loop — execute pending limit sells when price is reached."""
        to_remove = []
        for sym, order in self._pending_sells.items():
            price = self._prices.get(sym, 0)
            if price >= order["limit_price"]:
                await self._execute_sell(
                    sym, price, order["qty"], order["entry"],
                    "LIMIT", f"Manual limit sell filled @ ${price:.2f} (target ${order['limit_price']:.2f})"
                )
                to_remove.append(sym)
        for sym in to_remove:
            self._pending_sells.pop(sym, None)

    async def _execute_sell(self, sym: str, price: float, qty: float, entry: float, order_type: str, reason: str) -> dict:
        """Shared sell execution logic for both manual and engine-driven sells."""
        pnl = round((price - entry) * qty, 2)
        is_paper = self.simulate_24_7
        ticker_doc = await deps.db.tickers.find_one({"symbol": sym}, {"_id": 0})
        broker_ids = ticker_doc.get("broker_ids", []) if ticker_doc else []
        broker_allocs = ticker_doc.get("broker_allocations", {}) if ticker_doc else {}
        broker_results = []

        if not is_paper and broker_ids:
            broker_results = await deps.broker_mgr.place_orders_for_ticker(
                broker_ids=broker_ids, allocations=broker_allocs,
                order_template={
                    "symbol": sym, "side": "SELL", "order_type": order_type,
                    "price": price, "quantity": qty,
                },
            )

        trade = TradeRecord(
            symbol=sym, side="SELL", price=price, quantity=qty,
            reason=reason, pnl=pnl,
            order_type=order_type,
            entry_price=entry,
            total_value=round(price * qty, 2),
            buy_power=ticker_doc.get("base_power", 0) if ticker_doc else 0,
            trading_mode="paper" if is_paper or not broker_ids else "live",
            broker_results=broker_results,
        )
        await self._record_trade(trade)
        self._positions[sym] = {"qty": 0, "avg_entry": 0}
        self._trailing_highs.pop(sym, None)
        compound = ticker_doc.get("compound_profits", True) if ticker_doc else True
        await self._update_profit(sym, pnl, compound)

        return {
            "status": "executed",
            "symbol": sym,
            "order_type": order_type.lower(),
            "price": price,
            "quantity": qty,
            "pnl": pnl,
            "total_value": round(price * qty, 2),
            "trading_mode": trade.trading_mode,
        }

    def is_market_open(self) -> bool:
        # In paper mode, always allow trading (24/7 simulation)
        if self.simulate_24_7:
            return True
        # In live mode, respect market_hours_only setting
        if not self.market_hours_only:
            return True
        # Check actual US market hours (9:30 AM - 4:00 PM ET, weekdays) — DST-aware
        now = datetime.now(_ET)
        if now.weekday() >= 5:
            return False
        hour, minute = now.hour, now.minute
        if hour < 9 or (hour == 9 and minute < 30):
            return False
        if hour >= 16:
            return False
        return True

    def _get_today_str(self) -> str:
        """Get today's date string in US Eastern Time for tracking daily operations."""
        return datetime.now(_ET).strftime("%Y-%m-%d")

    # ------------------------------------------------------------------
    # evaluate_ticker — the heart of the trading logic
    # ------------------------------------------------------------------
    async def evaluate_ticker(self, ticker_doc: dict):
        sym = ticker_doc["symbol"]
        if not ticker_doc.get("enabled", False):
            return
        if ticker_doc.get("auto_stopped", False):
            return

        # Per-ticker market hours check (handles US, HK, AU, UK, CA, CN, etc.)
        if not self._is_ticker_market_open(ticker_doc):
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

        # Effective buy power: sum of broker allocations if brokers assigned, else base_power
        broker_ids = ticker_doc.get("broker_ids", [])
        broker_allocs = ticker_doc.get("broker_allocations", {})
        alloc_total = sum(broker_allocs.get(bid, 0) for bid in broker_ids) if broker_ids else 0
        effective_power = alloc_total if alloc_total > 0 else base_power

        buy_target = round(avg * (1 + buy_off / 100), 2) if is_buy_pct else round(buy_off, 2)
        pos = self._positions.get(sym, {"qty": 0, "avg_entry": 0})
        entry = pos.get("avg_entry", 0)

        if pos["qty"] > 0 and entry > 0:
            sell_target = round(entry * (1 + sell_off / 100), 2) if is_sell_pct else round(sell_off, 2)
            stop_target = round(entry * (1 + stop_off / 100), 2) if is_stop_pct else round(stop_off, 2)
        else:
            sell_target = round(avg * (1 + sell_off / 100), 2) if is_sell_pct else round(sell_off, 2)
            stop_target = round(avg * (1 + stop_off / 100), 2) if is_stop_pct else round(stop_off, 2)

        # --- SIGNAL STRATEGY ROUTING ---
        # If the ticker uses a registered signal strategy (not a preset / "custom"),
        # ask it to generate a signal. On a concrete BUY/SELL the engine executes and
        # returns; on HOLD or None it falls through to the existing bracket logic below.
        from strategies.presets import PRESET_STRATEGIES
        from strategies.loader import STRATEGY_REGISTRY

        strategy_name = ticker_doc.get("strategy", "custom")
        if strategy_name not in ("custom", "", *PRESET_STRATEGIES.keys()):
            signal_strategy = STRATEGY_REGISTRY.get(strategy_name)
            if signal_strategy and signal_strategy.metadata.is_signal_strategy:
                handled = await self._run_strategy_signal(
                    signal_strategy, ticker_doc, sym, price, pos, entry,
                    effective_power, broker_ids, broker_allocs,
                    sell_target, stop_target, compound, avg,
                )
                if handled:
                    return  # signal was executed — skip bracket logic

        # --- PARTIAL FILLS BRANCH ---
        if ticker_doc.get("partial_fills_enabled") and (ticker_doc.get("buy_legs") or ticker_doc.get("sell_legs")):
            await self._evaluate_partial_fills(
                ticker_doc, sym, price, avg, pos, entry,
                effective_power, broker_ids, broker_allocs,
                stop_target, is_stop_pct, stop_otype, compound,
            )
            return

        # --- BUY ---
        if pos["qty"] == 0:
            should_buy = (buy_otype == "market") or (price <= buy_target)
            if should_buy:
                exec_price = price
                qty = round(effective_power / exec_price, 4)
                if qty > 0:
                    is_paper = self.simulate_24_7
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
                        buy_power=effective_power, avg_price=avg,
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

            # --- OPENING BELL MODE ---
            # During first 30 min: force trailing stop, override normal sell rules
            # After 30 min: auto-rebracket to current price and resume normal trading
            opening_bell_on = ticker_doc.get("opening_bell_enabled", False)
            if opening_bell_on:
                ob_trail_val = ticker_doc.get("opening_bell_trail_value", 1.0)
                ob_trail_is_pct = ticker_doc.get("opening_bell_trail_is_percent", True)
                today_str = self._get_today_str()

                if self._is_opening_window(30, ticker_doc):
                    # During opening window: force trailing stop
                    ob_high = self._opening_bell_highs.get(sym, price)
                    if price > ob_high:
                        self._opening_bell_highs[sym] = price
                        ob_high = price

                    ob_trail_stop = round(ob_high * (1 - ob_trail_val / 100), 2) if ob_trail_is_pct else round(ob_high - ob_trail_val, 2)

                    if price <= ob_trail_stop:
                        # Opening bell trailing stop triggered - SELL
                        exec_price = price
                        pnl = round((exec_price - entry) * pos["qty"], 2)
                        is_paper = self.simulate_24_7
                        broker_results = []
                        if not is_paper and broker_ids:
                            broker_results = await deps.broker_mgr.place_orders_for_ticker(
                                broker_ids=broker_ids, allocations=broker_allocs,
                                order_template={
                                    "symbol": sym, "side": "SELL", "order_type": "STOP",
                                    "price": exec_price, "quantity": pos["qty"], "stop_price": ob_trail_stop,
                                },
                            )
                        trade = TradeRecord(
                            symbol=sym, side="TRAILING_STOP", price=exec_price,
                            quantity=pos["qty"],
                            reason=f"[OPENING BELL] Trailing stop hit ${ob_trail_stop} (high ${ob_high})",
                            pnl=pnl, order_type="MARKET",
                            rule_mode="PERCENT" if ob_trail_is_pct else "DOLLAR",
                            entry_price=entry, target_price=ob_trail_stop,
                            total_value=round(exec_price * pos["qty"], 2),
                            buy_power=effective_power, avg_price=avg,
                            sell_target=sell_target, stop_target=stop_target,
                            trail_high=ob_high, trail_trigger=ob_trail_stop, trail_value=ob_trail_val,
                            trail_mode="PERCENT" if ob_trail_is_pct else "DOLLAR",
                            trading_mode="paper" if is_paper or not broker_ids else "live",
                            broker_results=broker_results,
                        )
                        await self._record_trade(trade)
                        self._positions[sym] = {"qty": 0, "avg_entry": 0}
                        self._opening_bell_highs.pop(sym, None)
                        self._trailing_highs.pop(sym, None)
                        await self._update_profit(sym, pnl, compound)
                        return
                    # Still in opening window, skip normal sell/stop rules
                    return

                elif self._is_past_opening_window(30, ticker_doc):
                    # Past opening window - auto-rebracket once per day
                    if self._opening_bell_rebracket_done.get(sym) != today_str:
                        ob_high = self._opening_bell_highs.get(sym, price)
                        # Rebracket: use the opening high as new base for brackets
                        # Update the ticker's bracket center to the opening high
                        await deps.db.tickers.update_one(
                            {"symbol": sym},
                            {"$set": {"avg_days": 1}}  # Short lookback so avg converges to recent price
                        )
                        self._opening_bell_rebracket_done[sym] = today_str
                        self._opening_bell_highs.pop(sym, None)
                        deps.logger.info(f"OPENING BELL REBRACKET: {sym} brackets reset after opening window (high was ${ob_high:.2f})")
                        # Broadcast update
                        doc = await deps.db.tickers.find_one({"symbol": sym}, {"_id": 0})
                        if doc:
                            await deps.ws_manager.broadcast({"type": "TICKER_UPDATED", "ticker": doc})
                    # Continue to normal trading logic below

            if trailing:
                # TIME RULE: Lock trailing stop for first 30 min after market open
                lock_trailing = ticker_doc.get("lock_trailing_at_open", False)
                if lock_trailing and self._is_opening_window(30, ticker_doc):
                    pass  # Skip trailing stop evaluation during opening window
                else:
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
                            buy_power=effective_power, avg_price=avg,
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
                    buy_power=effective_power, avg_price=avg,
                    sell_target=sell_target, stop_target=stop_target,
                    trading_mode="paper" if is_paper or not broker_ids else "live",
                    broker_results=broker_results,
                )
                await self._record_trade(trade)
                self._positions[sym] = {"qty": 0, "avg_entry": 0}
                self._trailing_highs.pop(sym, None)
                await self._update_profit(sym, pnl, compound)

            elif price <= stop_target or stop_otype == "market":
                # TIME RULE: Halve stop loss (0.5x) during first 30 min after open
                # This tightens the stop to prevent being dragged down by opening volatility
                effective_stop = stop_target
                halve_stop = ticker_doc.get("halve_stop_at_open", False)
                if halve_stop and self._is_opening_window(30, ticker_doc) and entry > 0:
                    stop_distance = entry - stop_target
                    effective_stop = round(entry - (stop_distance * 0.5), 2)

                should_stop = (stop_otype == "market") or (price <= effective_stop)
                if should_stop:
                    exec_price = price
                    pnl = round((exec_price - entry) * pos["qty"], 2)
                    order_label = "MKT" if stop_otype == "market" else "LMT"
                    is_paper = self.simulate_24_7
                    broker_results = []
                    if not is_paper and broker_ids:
                        broker_results = await deps.broker_mgr.place_orders_for_ticker(
                            broker_ids=broker_ids, allocations=broker_allocs,
                            order_template={
                                "symbol": sym, "side": "SELL", "order_type": "STOP",
                                "price": exec_price, "quantity": pos["qty"], "stop_price": effective_stop,
                            },
                        )
                    stop_note = f" [0.5x halved from ${stop_target}]" if effective_stop != stop_target else ""
                    trade = TradeRecord(
                        symbol=sym, side="STOP", price=exec_price, quantity=pos["qty"],
                        reason=f"[{order_label}] Stop-loss hit ${exec_price} {'(market)' if stop_otype == 'market' else f'<= ${effective_stop}'}{stop_note}",
                        pnl=pnl, order_type=stop_otype.upper(),
                        rule_mode="PERCENT" if is_stop_pct else "DOLLAR",
                        entry_price=entry, target_price=stop_target,
                        total_value=round(exec_price * pos["qty"], 2),
                        buy_power=effective_power, avg_price=avg,
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
    # Pluggable strategy signal routing
    # ------------------------------------------------------------------

    async def _run_strategy_signal(
        self,
        strategy,
        ticker_doc: dict,
        sym: str,
        price: float,
        pos: dict,
        entry: float,
        effective_power: float,
        broker_ids: list,
        broker_allocs: dict,
        sell_target: float,
        stop_target: float,
        compound: bool,
        avg: float,
    ) -> bool:
        """
        Call a signal strategy and execute the resulting action.
        Returns True if the signal was handled (caller should skip bracket logic).
        Returns False to fall through to bracket logic.
        """
        if not await strategy.validate_ticker(ticker_doc):
            return False

        params = strategy.get_params(ticker_doc)

        try:
            market_data   = await deps.price_service.get_enriched_market_data(ticker_doc)
            market_status = self._get_market(ticker_doc).to_dict()
            signal = await strategy.generate_signals(
                ticker_doc, price, market_data, market_status, broker_allocs, params
            )
        except Exception as exc:
            deps.logger.error(
                f"Strategy '{strategy.metadata.name}' error on {sym}: {exc}", exc_info=True
            )
            return False  # safe fallback to bracket logic

        if signal is None:
            return False  # strategy deferred — use brackets

        if signal.action == "HOLD":
            deps.logger.debug(f"[{sym}] Strategy HOLD (confidence={signal.confidence:.2f})")
            return True   # explicitly hold — skip everything this cycle

        is_paper = self.simulate_24_7

        # --- BUY ---
        if signal.action == "BUY" and pos["qty"] == 0:
            qty = round(effective_power / price, 4) if price > 0 else 0
            if qty <= 0:
                return False
            broker_results = []
            if not is_paper and broker_ids:
                broker_results = await deps.broker_mgr.place_orders_for_ticker(
                    broker_ids=broker_ids, allocations=broker_allocs,
                    order_template={"symbol": sym, "side": "BUY", "order_type": "MARKET", "price": price},
                )
                if any(r.get("status") == "error" for r in broker_results) and broker_results:
                    all_failed = all(r.get("status") == "error" for r in broker_results)
                    if all_failed:
                        return False
            self._positions[sym] = {"qty": qty, "avg_entry": price}
            trade = TradeRecord(
                symbol=sym, side="BUY", price=price, quantity=qty,
                reason=f"[STRATEGY:{strategy.metadata.name}] {signal.reason} (conf={signal.confidence:.0%})",
                order_type="MARKET", rule_mode="STRATEGY",
                target_price=price, total_value=round(price * qty, 2),
                buy_power=effective_power, avg_price=avg,
                sell_target=sell_target, stop_target=stop_target,
                trading_mode="paper" if is_paper or not broker_ids else "live",
                broker_results=broker_results,
            )
            await self._record_trade(trade)
            return True

        # --- SELL / STOP_LOSS ---
        if signal.action in ("SELL", "STOP_LOSS", "TAKE_PROFIT") and pos["qty"] > 0:
            pnl = round((price - entry) * pos["qty"], 2)
            broker_results = []
            if not is_paper and broker_ids:
                broker_results = await deps.broker_mgr.place_orders_for_ticker(
                    broker_ids=broker_ids, allocations=broker_allocs,
                    order_template={
                        "symbol": sym, "side": "SELL", "order_type": "MARKET",
                        "price": price, "quantity": pos["qty"],
                    },
                )
            trade = TradeRecord(
                symbol=sym, side=signal.action if signal.action != "STOP_LOSS" else "STOP",
                price=price, quantity=pos["qty"],
                reason=f"[STRATEGY:{strategy.metadata.name}] {signal.reason} (conf={signal.confidence:.0%})",
                pnl=pnl, order_type="MARKET", rule_mode="STRATEGY",
                entry_price=entry, target_price=price,
                total_value=round(price * pos["qty"], 2),
                buy_power=effective_power, avg_price=avg,
                sell_target=sell_target, stop_target=stop_target,
                trading_mode="paper" if is_paper or not broker_ids else "live",
                broker_results=broker_results,
            )
            await self._record_trade(trade)
            self._positions[sym] = {"qty": 0, "avg_entry": 0}
            self._trailing_highs.pop(sym, None)
            await self._update_profit(sym, pnl, compound)
            return True

        # Unrecognised action — fall through to brackets
        deps.logger.warning(f"[{sym}] Unknown signal action '{signal.action}' from {strategy.metadata.name}")
        return False


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
    # Partial Fills — scale in/out with multiple legs
    # ------------------------------------------------------------------
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
                self._positions[sym] = {"qty": 0, "avg_entry": 0}
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
                self._positions[sym] = {"qty": 0, "avg_entry": 0}

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
