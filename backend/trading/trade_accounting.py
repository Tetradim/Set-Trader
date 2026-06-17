from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Tuple
from zoneinfo import ZoneInfo

import deps
from schemas import TradeRecord
from resilience import CircuitOpenError


class TradeAccountingMixin:
    async def _persist_trade_state(self):
        try:
            await self.save_state()
        except Exception as exc:
            deps.logger.error(f"Failed to persist engine state after trade update: {exc}")

    def _reentry_cooldown_seconds(self, ticker_doc: Optional[dict] = None) -> float:
        configured = None
        if ticker_doc:
            configured = ticker_doc.get("reentry_cooldown_seconds")
        if configured is None:
            configured = getattr(self, "REENTRY_COOLDOWN_SECS", 300)
        try:
            return max(0.0, float(configured))
        except (TypeError, ValueError):
            return float(getattr(self, "REENTRY_COOLDOWN_SECS", 300))

    def _reentry_cooldown_remaining(
        self,
        symbol: str,
        ticker_doc: Optional[dict] = None,
        now: Optional[datetime] = None,
    ) -> float:
        cooldown = self._reentry_cooldown_seconds(ticker_doc)
        if cooldown <= 0:
            return 0.0

        last_exit = getattr(self, "_last_exit_ts", {}).get(symbol)
        if not last_exit:
            return 0.0
        if last_exit.tzinfo is None:
            last_exit = last_exit.replace(tzinfo=timezone.utc)

        current = now or datetime.now(timezone.utc)
        elapsed = (current - last_exit).total_seconds()
        return max(0.0, cooldown - elapsed)

    def _is_reentry_cooldown_active(self, symbol: str, ticker_doc: Optional[dict] = None) -> bool:
        remaining = self._reentry_cooldown_remaining(symbol, ticker_doc)
        if remaining > 0:
            deps.logger.debug(f"[{symbol}] Re-entry cooldown active ({remaining:.0f}s remaining)")
            return True
        return False

    async def _record_trade(self, trade: TradeRecord):
        with deps.tracer.start_as_current_span("trade.execute", attributes={
            "trade.id": trade.id, "trade.symbol": trade.symbol, "trade.side": trade.side,
            "trade.order_type": trade.order_type, "trade.price": trade.price,
            "trade.quantity": trade.quantity, "trade.total_value": trade.total_value,
            "trade.pnl": trade.pnl, "trade.rule_mode": trade.rule_mode,
        }) as span:
            doc = trade.model_dump()
            await deps.db.trades.insert_one(doc)
            now = datetime.now(timezone.utc)
            self._last_trade_ts[trade.symbol] = now
            if trade.side != "BUY":
                self._last_exit_ts[trade.symbol] = now
            else:
                await self._persist_trade_state()
            
            # Send ORDER_FILLED command to Edge if enabled
            try:
                from shared.edge_integration import on_trade_executed
                await on_trade_executed(doc)
            except ImportError:
                pass  # Edge integration not available
            
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
            await self._check_global_daily_drawdown()
        await self._persist_trade_state()

    async def _check_global_daily_drawdown(self):
        cfg_doc = await deps.db.settings.find_one({"key": "global_daily_drawdown"}, {"_id": 0})
        cfg = cfg_doc.get("value", {}) if cfg_doc else {}
        if not cfg.get("enabled"):
            return

        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        pipeline = [
            {"$match": {"pnl": {"$lt": 0}, "timestamp": {"$gte": today_start}}},
            {"$group": {"_id": None, "total_loss": {"$sum": "$pnl"}}},
        ]
        result = await deps.db.trades.aggregate(pipeline).to_list(1)
        daily_loss = abs(result[0]["total_loss"]) if result else 0
        if daily_loss <= 0:
            return

        limit = float(cfg.get("limit", 0) or 0)
        if cfg.get("type") == "percent":
            balance_doc = await deps.db.settings.find_one({"key": "account_balance"}, {"_id": 0})
            account_balance = float(balance_doc.get("value", 0) if balance_doc else 0)
            threshold = account_balance * (limit / 100) if account_balance > 0 else 0
        else:
            threshold = limit

        if threshold <= 0 or daily_loss < threshold:
            return

        self.running = False
        self.paused = True
        await self.save_state()
        reason = f"GLOBAL_DAILY_DRAWDOWN: daily loss ${daily_loss:.2f} exceeded limit ${threshold:.2f}"
        await deps.db.settings.update_one(
            {"key": "global_daily_drawdown_status"},
            {"$set": {
                "value": {
                    "tripped": True,
                    "reason": reason,
                    "daily_loss": round(daily_loss, 2),
                    "threshold": round(threshold, 2),
                    "tripped_at": datetime.now(timezone.utc).isoformat(),
                }
            }},
            upsert=True,
        )
        await deps.ws_manager.broadcast({"type": "BOT_STATUS", "running": False, "paused": True})
        await deps.ws_manager.broadcast({
            "type": "RISK_ALERT",
            "scope": "global",
            "code": "GLOBAL_DAILY_DRAWDOWN",
            "message": reason,
        })
        deps.logger.warning(reason)
        try:
            await deps.telegram_service._broadcast_alert(
                f"GLOBAL DAILY DRAWDOWN\n{reason}\nBot stopped. Review risk before restarting."
            )
        except Exception:
            pass

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
