from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Tuple
from zoneinfo import ZoneInfo

import deps
from schemas import TradeRecord
from resilience import CircuitOpenError
from trading.broker_execution import LiveOrderExecutionError


_ET = ZoneInfo("America/New_York")


class TickerEvaluationMixin:
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
        buying_paused = ticker_doc.get("buying_paused", False)

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
        has_partial_legs = ticker_doc.get("buy_legs") or ticker_doc.get("sell_legs")
        has_partial_position = pos.get("qty", 0) > 0
        if ticker_doc.get("partial_fills_enabled") and (has_partial_legs or has_partial_position):
            await self._evaluate_partial_fills(
                ticker_doc, sym, price, avg, pos, entry,
                effective_power, broker_ids, broker_allocs,
                stop_target, is_stop_pct, stop_otype, compound,
            )
            return

        # --- BUY ---
        if pos["qty"] == 0 and not buying_paused:
            should_buy = (buy_otype == "market") or (price <= buy_target)
            if should_buy and not self._is_reentry_cooldown_active(sym, ticker_doc):
                exec_price = price
                qty = round(effective_power / exec_price, 4)
                if qty > 0:
                    is_paper = self.is_paper_trading()
                    broker_results = []
                    try:
                        broker_results = await self._place_live_order_or_raise(
                            sym=sym,
                            broker_ids=broker_ids,
                            broker_allocs=broker_allocs,
                            action_label="BUY",
                            order_template={
                                "symbol": sym, "side": "BUY", "order_type": buy_otype.upper(),
                                "price": exec_price,
                                "limit_price": buy_target if buy_otype == "limit" else None,
                            },
                        )
                    except LiveOrderExecutionError as exc:
                        deps.logger.warning(str(exc))
                        return

                    self._positions[sym] = {"qty": qty, "avg_entry": exec_price, "high": exec_price}
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

            defer_profit_sell = False
            wait_day = ticker_doc.get("wait_day_after_buy", False)
            if wait_day:
                last_buy = await deps.db.trades.find_one(
                    {"symbol": sym, "side": "BUY"}, {"_id": 0, "timestamp": 1}, sort=[("timestamp", -1)]
                )
                if last_buy:
                    # Use ET (DST-aware) for trading day calculation, not UTC
                    # Pattern Day Trader rule: wait one trading day, not calendar day
                    buy_dt = datetime.fromisoformat(last_buy["timestamp"]).astimezone(_ET)
                    buy_date = buy_dt.date()
                    today_et = datetime.now(_ET).date()
                    if buy_date >= today_et:
                        defer_profit_sell = True

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
                    ob_high = self._opening_bell_highs.get(sym)
                    if ob_high is None or price > ob_high:
                        self._opening_bell_highs[sym] = price
                        ob_high = price
                        await self._persist_trade_state()

                    ob_trail_stop = round(ob_high * (1 - ob_trail_val / 100), 2) if ob_trail_is_pct else round(ob_high - ob_trail_val, 2)

                    if price <= ob_trail_stop:
                        # Opening bell trailing stop triggered - SELL
                        exec_price = price
                        pnl = round((exec_price - entry) * pos["qty"], 2)
                        is_paper = self.is_paper_trading()
                        broker_results = []
                        try:
                            broker_results = await self._place_live_order_or_raise(
                                sym=sym,
                                broker_ids=broker_ids,
                                broker_allocs=broker_allocs,
                                action_label="OPENING_BELL_TRAILING_STOP",
                                order_template={
                                    "symbol": sym, "side": "SELL", "order_type": "STOP",
                                    "price": exec_price, "quantity": pos["qty"], "stop_price": ob_trail_stop,
                                },
                            )
                        except LiveOrderExecutionError as exc:
                            deps.logger.warning(str(exc))
                            return
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
                        self._positions[sym] = {"qty": 0, "avg_entry": 0, "high": 0}
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
                        # Rebracket: use the opening high as a real absolute bracket anchor.
                        spread = ticker_doc.get("rebracket_spread", 0.80)
                        buffer = ticker_doc.get("rebracket_buffer", 0.10)
                        new_buy = round(ob_high - buffer, 2)
                        new_sell = round(new_buy + spread, 2)
                        await self._set_absolute_bracket(
                            sym, ticker_doc, buy_target, sell_target, new_buy, new_sell,
                            timestamp=datetime.now(timezone.utc),
                        )
                        self._opening_bell_rebracket_done[sym] = today_str
                        self._opening_bell_highs.pop(sym, None)
                        await self._persist_trade_state()
                        deps.logger.info(f"OPENING BELL REBRACKET: {sym} brackets reset after opening window (high was ${ob_high:.2f})")
                    # Continue to normal trading logic below

            if trailing:
                # TIME RULE: Lock trailing stop for first 30 min after market open
                lock_trailing = ticker_doc.get("lock_trailing_at_open", False)
                if lock_trailing and self._is_opening_window(30, ticker_doc):
                    pass  # Skip trailing stop evaluation during opening window
                else:
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
                        is_paper = self.is_paper_trading()
                        broker_results = []
                        try:
                            broker_results = await self._place_live_order_or_raise(
                                sym=sym,
                                broker_ids=broker_ids,
                                broker_allocs=broker_allocs,
                                action_label="TRAILING_STOP",
                                order_template={
                                    "symbol": sym, "side": "SELL", "order_type": "STOP",
                                    "price": exec_price, "quantity": pos["qty"], "stop_price": trail_stop,
                                },
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
                            sell_target=sell_target, stop_target=stop_target,
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

            should_sell = price >= sell_target and not defer_profit_sell
            if should_sell:
                exec_price = price
                pnl = round((exec_price - entry) * pos["qty"], 2)
                order_label = "MKT" if sell_otype == "market" else "LMT"
                is_paper = self.is_paper_trading()
                broker_results = []
                try:
                    broker_results = await self._place_live_order_or_raise(
                        sym=sym,
                        broker_ids=broker_ids,
                        broker_allocs=broker_allocs,
                        action_label="SELL",
                        order_template={
                            "symbol": sym, "side": "SELL", "order_type": sell_otype.upper(),
                            "price": exec_price, "quantity": pos["qty"],
                            "limit_price": sell_target if sell_otype == "limit" else None,
                        },
                    )
                except LiveOrderExecutionError as exc:
                    deps.logger.warning(str(exc))
                    return
                trade = TradeRecord(
                    symbol=sym, side="SELL", price=exec_price, quantity=pos["qty"],
                    reason=f"[{order_label}] Price ${exec_price} >= sell target ${sell_target}",
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
                self._positions[sym] = {"qty": 0, "avg_entry": 0, "high": 0}
                self._trailing_highs.pop(sym, None)
                await self._update_profit(sym, pnl, compound)

            else:
                # TIME RULE: Halve stop loss (0.5x) during first 30 min after open.
                # The tightened stop is the actual trigger; order type only controls execution style.
                effective_stop = stop_target
                halve_stop = ticker_doc.get("halve_stop_at_open", False)
                if halve_stop and self._is_opening_window(30, ticker_doc) and entry > 0:
                    stop_distance = entry - stop_target
                    effective_stop = round(entry - (stop_distance * 0.5), 2)

                if price <= effective_stop:
                    exec_price = price
                    pnl = round((exec_price - entry) * pos["qty"], 2)
                    order_label = "MKT" if stop_otype == "market" else "LMT"
                    is_paper = self.is_paper_trading()
                    broker_results = []
                    try:
                        broker_results = await self._place_live_order_or_raise(
                            sym=sym,
                            broker_ids=broker_ids,
                            broker_allocs=broker_allocs,
                            action_label="STOP",
                            order_template={
                                "symbol": sym, "side": "SELL", "order_type": "STOP",
                                "price": exec_price, "quantity": pos["qty"], "stop_price": effective_stop,
                            },
                        )
                    except LiveOrderExecutionError as exc:
                        deps.logger.warning(str(exc))
                        return
                    stop_note = f" [0.5x halved from ${stop_target}]" if effective_stop != stop_target else ""
                    trade = TradeRecord(
                        symbol=sym, side="STOP", price=exec_price, quantity=pos["qty"],
                        reason=f"[{order_label}] Stop-loss hit ${exec_price} <= ${effective_stop}{stop_note}",
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
                    self._positions[sym] = {"qty": 0, "avg_entry": 0, "high": 0}
                    self._trailing_highs.pop(sym, None)
                    await self._update_profit(sym, pnl, compound)

        # --- AUTO REBRACKET ---
        rebracket_on = ticker_doc.get("auto_rebracket", False)
        current_pos = self._positions.get(sym, {"qty": 0})
        if rebracket_on and current_pos.get("qty", 0) == 0:
            await self._auto_rebracket(sym, ticker_doc, price, buy_target, sell_target)
