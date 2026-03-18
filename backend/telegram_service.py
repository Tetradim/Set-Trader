"""Telegram service — bot lifecycle, commands, and alert broadcasting."""
import asyncio
from typing import List, Optional, Any

import deps
from schemas import TickerConfig


class TelegramService:
    def __init__(self):
        self._app: Optional[Any] = None
        self._task: Optional[asyncio.Task] = None
        self.running = False
        self.bot_token = ""
        self.chat_ids: List[str] = []

    async def start(self, token: str, chat_ids: List[str]):
        await self.stop()
        if not deps.TG_AVAILABLE or not token:
            deps.logger.info("Telegram: skipping start (no library or no token)")
            return
        self.bot_token = token
        self.chat_ids = chat_ids
        try:
            from telegram.ext import Application
            self._app = Application.builder().token(token).build()
            self._register_handlers()
            await self._app.initialize()
            await self._app.start()
            await self._app.updater.start_polling(drop_pending_updates=True)
            self.running = True
            deps.logger.info("Telegram bot started (polling)")
            await self._broadcast_alert("Sentinel Pulse is now ONLINE and connected to Telegram.")
        except Exception as e:
            deps.logger.error(f"Telegram start error: {e}")
            self.running = False

    async def stop(self):
        if self._app and self.running:
            try:
                await self._broadcast_alert("Sentinel Pulse is going OFFLINE. You will be notified when it restarts.")
            except Exception:
                pass
            try:
                await self._app.updater.stop()
                await self._app.stop()
                await self._app.shutdown()
            except Exception as e:
                deps.logger.warning(f"Telegram stop error: {e}")
            self.running = False
            self._app = None

    async def reload_from_db(self):
        doc = await deps.db.settings.find_one({"key": "telegram"}, {"_id": 0})
        if doc and doc.get("value"):
            token = doc["value"].get("bot_token", "")
            ids = doc["value"].get("chat_ids", [])
            if token:
                await self.start(token, ids)

    # --- Alert helpers ---

    async def _broadcast_alert(self, text: str):
        if not self._app or not self.chat_ids:
            return
        bot = self._app.bot
        for cid in self.chat_ids:
            try:
                await bot.send_message(chat_id=int(cid), text=f"[Sentinel Pulse] {text}")
            except Exception as e:
                deps.logger.warning(f"Telegram send to {cid} failed: {e}")

    async def send_trade_alert(self, trade: dict):
        side = trade.get("side", "?")
        sym = trade.get("symbol", "?")
        price = trade.get("price", 0)
        qty = trade.get("quantity", 0)
        pnl = trade.get("pnl", 0)
        reason = trade.get("reason", "")
        order_type = trade.get("order_type", "")
        rule_mode = trade.get("rule_mode", "")
        entry_price = trade.get("entry_price", 0)
        target_price = trade.get("target_price", 0)
        total_value = trade.get("total_value", 0)
        buy_power = trade.get("buy_power", 0)

        pnl_str = f"\nP&L: {'+'if pnl>=0 else ''}{pnl:.2f}" if pnl != 0 else ""
        entry_str = f"\nEntry: ${entry_price:.2f}" if entry_price > 0 else ""
        trail_str = ""
        if side == "TRAILING_STOP":
            trail_str = (
                f"\nTrail High: ${trade.get('trail_high', 0):.2f} | "
                f"Trigger: ${trade.get('trail_trigger', 0):.2f} | "
                f"{trade.get('trail_mode', '')} {trade.get('trail_value', 0)}"
            )

        msg = (
            f"TRADE  {order_type} {side} {sym}\n"
            f"Fill: ${price:.2f}  Qty: {qty:.4f}\n"
            f"Target: ${target_price:.2f} | Mode: {rule_mode}\n"
            f"Value: ${total_value:.2f} | Power: ${buy_power:.2f}"
            f"{entry_str}{pnl_str}{trail_str}\n{reason}"
        )
        await self._broadcast_alert(msg)

    # --- Command handlers ---

    def _register_handlers(self):
        from telegram.ext import CommandHandler
        app = self._app
        app.add_handler(CommandHandler("stop", self._cmd_stop))
        app.add_handler(CommandHandler("start", self._cmd_start_bot))
        app.add_handler(CommandHandler("stop", self._cmd_stop_bot))
        app.add_handler(CommandHandler("status", self._cmd_status))
        app.add_handler(CommandHandler("portfolio", self._cmd_portfolio))
        app.add_handler(CommandHandler("new", self._cmd_new))
        app.add_handler(CommandHandler("cancel", self._cmd_cancel))
        app.add_handler(CommandHandler("cancelall", self._cmd_cancelall))
        app.add_handler(CommandHandler("history", self._cmd_history))
        app.add_handler(CommandHandler("reconnect_brokers", self._cmd_reconnect_brokers))
        app.add_handler(CommandHandler("help", self._cmd_help))

    def _authorised(self, update) -> bool:
        cid = str(update.effective_chat.id)
        if not self.chat_ids:
            return True
        return cid in self.chat_ids

    async def _cmd_stop(self, update, ctx):
        if not self._authorised(update):
            return await update.message.reply_text("Unauthorised.")
        engine = deps.engine
        if engine.running:
            engine.running = False
            engine.paused = False
            await engine.save_state()
            await deps.ws_manager.broadcast({"type": "BOT_STATUS", "running": False, "paused": False})
            await update.message.reply_text("Bot STOPPED.")
            await self._broadcast_alert("Bot has been STOPPED via Telegram /stop command.")
        else:
            engine.running = True
            engine.paused = False
            await engine.save_state()
            await deps.ws_manager.broadcast({"type": "BOT_STATUS", "running": True, "paused": False})
            await update.message.reply_text("Bot STARTED.")
            await self._broadcast_alert("Bot has been STARTED via Telegram /stop command.")

    async def _cmd_start_bot(self, update, ctx):
        if not self._authorised(update):
            return await update.message.reply_text("Unauthorised.")
        deps.engine.running = True
        await deps.engine.save_state()
        await deps.ws_manager.broadcast({"type": "BOT_STATUS", "running": True, "paused": deps.engine.paused})
        await update.message.reply_text("Bot engine STARTED.")

    async def _cmd_stop_bot(self, update, ctx):
        if not self._authorised(update):
            return await update.message.reply_text("Unauthorised.")
        deps.engine.running = False
        await deps.engine.save_state()
        await deps.ws_manager.broadcast({"type": "BOT_STATUS", "running": False, "paused": deps.engine.paused})
        await update.message.reply_text("Bot engine STOPPED.")

    async def _cmd_status(self, update, ctx):
        if not self._authorised(update):
            return await update.message.reply_text("Unauthorised.")
        tickers = await deps.db.tickers.find({}, {"_id": 0}).to_list(100)
        active = sum(1 for t in tickers if t.get("enabled"))
        profits_list = await deps.db.profits.find({}, {"_id": 0}).to_list(100)
        total_pnl = sum(p.get("total_pnl", 0) for p in profits_list)
        lines = [
            f"Running: {'YES' if deps.engine.running else 'NO'}",
            f"Paused: {'YES' if deps.engine.paused else 'NO'}",
            f"Market: {'OPEN' if deps.engine.is_market_open() else 'CLOSED'}",
            f"Tickers: {active}/{len(tickers)} active",
            f"Total P&L: ${total_pnl:.2f}",
        ]
        await update.message.reply_text("\n".join(lines))

    async def _cmd_portfolio(self, update, ctx):
        if not self._authorised(update):
            return await update.message.reply_text("Unauthorised.")
        profits_list = await deps.db.profits.find({}, {"_id": 0}).to_list(100)
        if not profits_list:
            return await update.message.reply_text("No profit data yet.")
        lines = ["Symbol | P&L"]
        total = 0
        for p in profits_list:
            pnl = p.get("total_pnl", 0)
            total += pnl
            lines.append(f"{p['symbol']}: {'+'if pnl>=0 else ''}{pnl:.2f}")
        lines.append(f"\nTotal: {'+'if total>=0 else ''}{total:.2f}")
        await update.message.reply_text("\n".join(lines))

    async def _cmd_new(self, update, ctx):
        if not self._authorised(update):
            return await update.message.reply_text("Unauthorised.")
        parts = (update.message.text or "").split()
        if len(parts) < 2:
            return await update.message.reply_text("Usage: /new SYMBOL [POWER]\nExample: /new MSFT 200")
        sym = parts[1].upper().strip()
        power = float(parts[2]) if len(parts) >= 3 else 100.0
        existing = await deps.db.tickers.find_one({"symbol": sym})
        if existing:
            return await update.message.reply_text(f"{sym} already exists.")
        t = TickerConfig(symbol=sym, base_power=power)
        doc = t.model_dump()
        await deps.db.tickers.insert_one(doc)
        doc.pop("_id", None)
        await deps.ws_manager.broadcast({"type": "TICKER_ADDED", "ticker": doc})
        await update.message.reply_text(f"Added {sym} with ${power:.0f} buy power.")

    async def _cmd_cancel(self, update, ctx):
        if not self._authorised(update):
            return await update.message.reply_text("Unauthorised.")
        parts = (update.message.text or "").split()
        if len(parts) < 2:
            return await update.message.reply_text("Usage: /cancel SYMBOL")
        sym = parts[1].upper()
        result = await deps.db.tickers.update_one({"symbol": sym}, {"$set": {"enabled": False}})
        if result.matched_count == 0:
            return await update.message.reply_text(f"{sym} not found.")
        deps.engine._positions.pop(sym, None)
        deps.engine._trailing_highs.pop(sym, None)
        doc = await deps.db.tickers.find_one({"symbol": sym}, {"_id": 0})
        if doc:
            await deps.ws_manager.broadcast({"type": "TICKER_UPDATED", "ticker": doc})
        await update.message.reply_text(f"{sym} disabled and orders cancelled.")

    async def _cmd_cancelall(self, update, ctx):
        if not self._authorised(update):
            return await update.message.reply_text("Unauthorised.")
        await deps.db.tickers.update_many({}, {"$set": {"enabled": False}})
        deps.engine._positions.clear()
        deps.engine._trailing_highs.clear()
        tickers = await deps.db.tickers.find({}, {"_id": 0}).to_list(100)
        for t in tickers:
            await deps.ws_manager.broadcast({"type": "TICKER_UPDATED", "ticker": t})
        await update.message.reply_text("All tickers disabled and orders cancelled.")

    async def _cmd_history(self, update, ctx):
        if not self._authorised(update):
            return await update.message.reply_text("Unauthorised.")
        trades = await deps.db.trades.find({}, {"_id": 0}).sort("timestamp", -1).to_list(10)
        if not trades:
            return await update.message.reply_text("No trade history.")
        lines = ["Recent Trades:"]
        for t in trades:
            pnl_str = f" P&L:{t.get('pnl',0):+.2f}" if t.get("pnl", 0) != 0 else ""
            mode = f" [{t.get('trading_mode', 'paper').upper()}]" if t.get('trading_mode') else ""
            lines.append(f"{t['side']} {t['symbol']} @${t['price']:.2f} x{t['quantity']:.4f}{pnl_str}{mode}")
        await update.message.reply_text("\n".join(lines))

    async def _cmd_reconnect_brokers(self, update, ctx):
        if not self._authorised(update):
            return await update.message.reply_text("Unauthorised.")
        await update.message.reply_text("Reconnecting all brokers...")
        results = await deps.broker_mgr.reconnect_all()
        if not results:
            return await update.message.reply_text("No broker credentials stored. Configure brokers in the web UI first.")
        lines = ["Broker Reconnection Results:"]
        for bid, status in results.items():
            icon = "OK" if status in ("connected", "already connected") else "FAIL"
            lines.append(f"  {icon} {bid}: {status}")
        await update.message.reply_text("\n".join(lines))

    async def _cmd_help(self, update, ctx):
        text = (
            "Sentinel Pulse Commands:\n"
            "/pause   - Pause all trading\n"
            "/resume  - Resume trading\n"
            "/start   - Start trading engine\n"
            "/stop    - Stop trading engine\n"
            "/status  - Bot status overview\n"
            "/portfolio - P&L by symbol\n"
            "/new SYMBOL [POWER] - Add ticker\n"
            "/cancel SYMBOL - Disable ticker\n"
            "/cancelall - Disable all tickers\n"
            "/history - Recent 10 trades\n"
            "/reconnect_brokers - Reconnect all brokers\n"
            "/help    - This message"
        )
        await update.message.reply_text(text)
