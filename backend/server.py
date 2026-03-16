import asyncio
import json
import os
import logging
import random
import uuid
import signal
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Query
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ConfigDict

# Telegram
try:
    from telegram import Bot, Update
    from telegram.ext import Application, CommandHandler, ContextTypes
    TG_AVAILABLE = True
except ImportError:
    TG_AVAILABLE = False

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("BracketBot")

# MongoDB
mongo_url = os.environ['MONGO_URL']
mongo_client = AsyncIOMotorClient(mongo_url)
db = mongo_client[os.environ['DB_NAME']]

# yfinance (optional, for real price data)
try:
    import yfinance as yf
    YF_AVAILABLE = True
except ImportError:
    YF_AVAILABLE = False
    logger.warning("yfinance not installed. Using simulated prices only.")


# --- SCHEMAS ---
class TickerConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str
    base_power: float = 100.0
    avg_days: int = 30
    buy_offset: float = -3.0
    buy_percent: bool = True
    buy_order_type: str = "limit"  # "limit" or "market"
    sell_offset: float = 3.0
    sell_percent: bool = True
    sell_order_type: str = "limit"
    stop_offset: float = -6.0
    stop_percent: bool = True
    stop_order_type: str = "limit"
    trailing_enabled: bool = False
    trailing_percent: float = 2.0
    trailing_percent_mode: bool = True
    trailing_order_type: str = "limit"
    wait_day_after_buy: bool = False
    enabled: bool = True
    strategy: str = "custom"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class TickerCreate(BaseModel):
    symbol: str
    base_power: float = 100.0

class TickerUpdate(BaseModel):
    base_power: Optional[float] = None
    avg_days: Optional[int] = None
    buy_offset: Optional[float] = None
    buy_percent: Optional[bool] = None
    buy_order_type: Optional[str] = None
    sell_offset: Optional[float] = None
    sell_percent: Optional[bool] = None
    sell_order_type: Optional[str] = None
    stop_offset: Optional[float] = None
    stop_percent: Optional[bool] = None
    stop_order_type: Optional[str] = None
    trailing_enabled: Optional[bool] = None
    trailing_percent: Optional[float] = None
    trailing_percent_mode: Optional[bool] = None
    trailing_order_type: Optional[str] = None
    wait_day_after_buy: Optional[bool] = None
    enabled: Optional[bool] = None
    strategy: Optional[str] = None

class TradeRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str
    side: str  # BUY, SELL, STOP, TRAILING_STOP
    price: float
    quantity: float
    reason: str = ""
    pnl: float = 0.0
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class Position(BaseModel):
    model_config = ConfigDict(extra="ignore")
    symbol: str
    quantity: float = 0.0
    avg_entry: float = 0.0
    current_price: float = 0.0
    unrealized_pnl: float = 0.0

class TelegramConfig(BaseModel):
    bot_token: str = ""
    chat_ids: List[str] = []

class SettingsUpdate(BaseModel):
    telegram: Optional[TelegramConfig] = None
    simulate_24_7: Optional[bool] = None
    increment_step: Optional[float] = None
    decrement_step: Optional[float] = None

class PresetStrategy(BaseModel):
    name: str
    avg_days: int
    buy_offset: float
    buy_percent: bool
    sell_offset: float
    sell_percent: bool
    stop_offset: float
    stop_percent: bool
    trailing_enabled: bool
    trailing_percent: float
    trailing_percent_mode: bool = True


# --- WEBSOCKET MANAGER ---
class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, msg: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

ws_manager = ConnectionManager()


# --- PRICE SERVICE ---
class PriceService:
    def __init__(self):
        self._cache: Dict[str, dict] = {}
        self._last_fetch: Dict[str, datetime] = {}

    async def get_price(self, symbol: str) -> float:
        now = datetime.now(timezone.utc)
        cached = self._cache.get(symbol)
        last = self._last_fetch.get(symbol)

        if cached and last and (now - last).total_seconds() < 15:
            noise = cached["price"] * random.uniform(-0.001, 0.001)
            return round(cached["price"] + noise, 2)

        if YF_AVAILABLE:
            try:
                loop = asyncio.get_event_loop()
                price = await loop.run_in_executor(None, self._fetch_yf, symbol)
                if price > 0:
                    self._cache[symbol] = {"price": price}
                    self._last_fetch[symbol] = now
                    return price
            except Exception as e:
                logger.warning(f"yfinance error for {symbol}: {e}")

        if cached:
            drift = cached["price"] * random.uniform(-0.005, 0.005)
            new_price = max(0.01, cached["price"] + drift)
            self._cache[symbol] = {"price": round(new_price, 2)}
            return round(new_price, 2)

        base = random.uniform(50, 500)
        self._cache[symbol] = {"price": round(base, 2)}
        return round(base, 2)

    def _fetch_yf(self, symbol: str) -> float:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="1d")
            if not hist.empty:
                return round(float(hist["Close"].iloc[-1]), 2)
        except Exception:
            pass
        return 0.0

    async def get_avg_price(self, symbol: str, days: int) -> float:
        if YF_AVAILABLE:
            try:
                loop = asyncio.get_event_loop()
                avg = await loop.run_in_executor(None, self._fetch_avg_yf, symbol, days)
                if avg > 0:
                    return avg
            except Exception:
                pass
        current = await self.get_price(symbol)
        return current

    def _fetch_avg_yf(self, symbol: str, days: int) -> float:
        try:
            ticker = yf.Ticker(symbol)
            period = "1mo" if days <= 30 else "3mo" if days <= 90 else "1y"
            hist = ticker.history(period=period)
            if not hist.empty:
                return round(float(hist["Close"].tail(days).mean()), 2)
        except Exception:
            pass
        return 0.0

price_service = PriceService()


# --- TRADING ENGINE ---
class TradingEngine:
    TRADE_COOLDOWN_SECS = 30  # min seconds between trades for the same symbol

    def __init__(self):
        self.running = False
        self.paused = False
        self.simulate_24_7 = False
        self._prices: Dict[str, float] = {}
        self._positions: Dict[str, dict] = {}
        self._trailing_highs: Dict[str, float] = {}
        self._last_trade_ts: Dict[str, datetime] = {}  # per-symbol cooldown

    async def save_state(self):
        """Persist running/paused/simulate_24_7 to MongoDB so they survive restarts."""
        await db.settings.update_one(
            {"key": "engine_state"},
            {"$set": {"value": {
                "running": self.running,
                "paused": self.paused,
                "simulate_24_7": self.simulate_24_7,
            }}},
            upsert=True,
        )

    async def load_state(self):
        """Restore running/paused state from MongoDB on startup."""
        doc = await db.settings.find_one({"key": "engine_state"}, {"_id": 0})
        if doc and doc.get("value"):
            v = doc["value"]
            self.running = v.get("running", False)
            self.paused = v.get("paused", False)
            self.simulate_24_7 = v.get("simulate_24_7", False)
            logger.info(f"Engine state restored: running={self.running}, paused={self.paused}, sim247={self.simulate_24_7}")

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

    async def evaluate_ticker(self, ticker_doc: dict):
        sym = ticker_doc["symbol"]
        if not ticker_doc.get("enabled", False):
            return

        # Per-symbol cooldown: skip if we traded too recently
        now = datetime.now(timezone.utc)
        last = self._last_trade_ts.get(sym)
        if last and (now - last).total_seconds() < self.TRADE_COOLDOWN_SECS:
            return

        price = await price_service.get_price(sym)
        self._prices[sym] = price
        avg = await price_service.get_avg_price(sym, ticker_doc.get("avg_days", 30))

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
        base_power = ticker_doc.get("base_power", 100.0)

        # Percent mode: offset from average. Dollar mode: ABSOLUTE target price.
        buy_target = round(avg * (1 + buy_off / 100), 2) if is_buy_pct else round(buy_off, 2)
        sell_target = round(avg * (1 + sell_off / 100), 2) if is_sell_pct else round(sell_off, 2)
        stop_target = round(avg * (1 + stop_off / 100), 2) if is_stop_pct else round(stop_off, 2)

        pos = self._positions.get(sym, {"qty": 0, "avg_entry": 0})

        # BUY logic: market = buy immediately when no position, limit = buy when price <= target
        if pos["qty"] == 0:
            should_buy = (buy_otype == "market") or (price <= buy_target)
            if should_buy:
                exec_price = price  # market orders execute at current price
                qty = round(base_power / exec_price, 4)
                if qty > 0:
                    self._positions[sym] = {"qty": qty, "avg_entry": exec_price}
                    order_label = "MKT" if buy_otype == "market" else "LMT"
                    trade = TradeRecord(
                        symbol=sym, side="BUY", price=exec_price, quantity=qty,
                        reason=f"[{order_label}] Price ${exec_price} {'(market)' if buy_otype == 'market' else f'<= buy target ${buy_target}'}"
                    )
                    await self._record_trade(trade)

        # SELL / STOP / TRAILING logic
        elif pos["qty"] > 0:
            entry = pos["avg_entry"]

            # Wait-a-day guard: skip sell logic if last buy was today
            wait_day = ticker_doc.get("wait_day_after_buy", False)
            if wait_day:
                last_buy = await db.trades.find_one(
                    {"symbol": sym, "side": "BUY"},
                    {"_id": 0, "timestamp": 1},
                    sort=[("timestamp", -1)]
                )
                if last_buy:
                    buy_date = datetime.fromisoformat(last_buy["timestamp"]).date()
                    today = datetime.now(timezone.utc).date()
                    if buy_date >= today:
                        return  # skip all sell logic until next trading day

            if trailing:
                high = self._trailing_highs.get(sym, price)
                if price > high:
                    self._trailing_highs[sym] = price
                    high = price
                if trail_is_pct:
                    trail_stop = round(high * (1 - trail_pct / 100), 2)
                else:
                    trail_stop = round(high - trail_pct, 2)
                should_trail = (trail_otype == "market") or (price <= trail_stop)
                if should_trail:
                    exec_price = price
                    pnl = round((exec_price - entry) * pos["qty"], 2)
                    order_label = "MKT" if trail_otype == "market" else "LMT"
                    trade = TradeRecord(
                        symbol=sym, side="TRAILING_STOP", price=exec_price,
                        quantity=pos["qty"], reason=f"[{order_label}] Trailing stop hit ${trail_stop} (high ${high})", pnl=pnl
                    )
                    await self._record_trade(trade)
                    self._positions[sym] = {"qty": 0, "avg_entry": 0}
                    self._trailing_highs.pop(sym, None)
                    await self._update_profit(sym, pnl)
                    return

            should_sell = (sell_otype == "market") or (price >= sell_target)
            if should_sell:
                exec_price = price
                pnl = round((exec_price - entry) * pos["qty"], 2)
                order_label = "MKT" if sell_otype == "market" else "LMT"
                trade = TradeRecord(
                    symbol=sym, side="SELL", price=exec_price, quantity=pos["qty"],
                    reason=f"[{order_label}] Price ${exec_price} {'(market)' if sell_otype == 'market' else f'>= sell target ${sell_target}'}", pnl=pnl
                )
                await self._record_trade(trade)
                self._positions[sym] = {"qty": 0, "avg_entry": 0}
                self._trailing_highs.pop(sym, None)
                await self._update_profit(sym, pnl)

            elif price <= stop_target or stop_otype == "market":
                should_stop = (stop_otype == "market") or (price <= stop_target)
                if should_stop:
                    exec_price = price
                    pnl = round((exec_price - entry) * pos["qty"], 2)
                    order_label = "MKT" if stop_otype == "market" else "LMT"
                    trade = TradeRecord(
                        symbol=sym, side="STOP", price=exec_price, quantity=pos["qty"],
                        reason=f"[{order_label}] Stop-loss hit ${exec_price} {'(market)' if stop_otype == 'market' else f'<= ${stop_target}'}", pnl=pnl
                    )
                    await self._record_trade(trade)
                    self._positions[sym] = {"qty": 0, "avg_entry": 0}
                    self._trailing_highs.pop(sym, None)
                    await self._update_profit(sym, pnl)

    async def _record_trade(self, trade: TradeRecord):
        doc = trade.model_dump()
        await db.trades.insert_one(doc)
        self._last_trade_ts[trade.symbol] = datetime.now(timezone.utc)
        logger.info(f"TRADE: {trade.side} {trade.symbol} @ ${trade.price} x{trade.quantity}")
        clean = {k: v for k, v in doc.items() if k != "_id"}
        await ws_manager.broadcast({"type": "TRADE", "trade": clean})
        # Telegram alert
        try:
            await telegram_service.send_trade_alert(clean)
        except Exception:
            pass

    async def _update_profit(self, symbol: str, pnl: float):
        await db.profits.update_one(
            {"symbol": symbol},
            {"$inc": {"total_pnl": pnl, "trade_count": 1},
             "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True
        )

engine = TradingEngine()


# --- TELEGRAM SERVICE ---
class TelegramService:
    """Manages the Telegram bot lifecycle: polling, commands, alerts."""

    def __init__(self):
        self._app: Optional[Any] = None
        self._task: Optional[asyncio.Task] = None
        self.running = False
        self.bot_token = ""
        self.chat_ids: List[str] = []

    # ---- lifecycle ----

    async def start(self, token: str, chat_ids: List[str]):
        """Start (or restart) the Telegram bot with a new token."""
        await self.stop()
        if not TG_AVAILABLE or not token:
            logger.info("Telegram: skipping start (no library or no token)")
            return
        self.bot_token = token
        self.chat_ids = chat_ids
        try:
            self._app = (
                Application.builder()
                .token(token)
                .build()
            )
            self._register_handlers()
            await self._app.initialize()
            await self._app.start()
            await self._app.updater.start_polling(drop_pending_updates=True)
            self.running = True
            logger.info("Telegram bot started (polling)")
            await self._broadcast_alert("BracketBot is now ONLINE and connected to Telegram.")
        except Exception as e:
            logger.error(f"Telegram start error: {e}")
            self.running = False

    async def stop(self):
        """Gracefully shut down the bot and notify chat IDs."""
        if self._app and self.running:
            try:
                await self._broadcast_alert("BracketBot is going OFFLINE. You will be notified when it restarts.")
            except Exception:
                pass
            try:
                await self._app.updater.stop()
                await self._app.stop()
                await self._app.shutdown()
            except Exception as e:
                logger.warning(f"Telegram stop error: {e}")
            self.running = False
            self._app = None

    async def reload_from_db(self):
        """Load config from MongoDB and start if a token is present."""
        doc = await db.settings.find_one({"key": "telegram"}, {"_id": 0})
        if doc and doc.get("value"):
            token = doc["value"].get("bot_token", "")
            ids = doc["value"].get("chat_ids", [])
            if token:
                await self.start(token, ids)

    # ---- alert helpers ----

    async def _broadcast_alert(self, text: str):
        """Send a message to every registered chat_id."""
        if not self._app or not self.chat_ids:
            return
        bot = self._app.bot
        for cid in self.chat_ids:
            try:
                await bot.send_message(chat_id=int(cid), text=f"[BracketBot] {text}")
            except Exception as e:
                logger.warning(f"Telegram send to {cid} failed: {e}")

    async def send_trade_alert(self, trade: dict):
        """Push a trade notification to all chats."""
        side = trade.get("side", "?")
        sym = trade.get("symbol", "?")
        price = trade.get("price", 0)
        qty = trade.get("quantity", 0)
        pnl = trade.get("pnl", 0)
        reason = trade.get("reason", "")
        pnl_str = f"  P&L: {'+'if pnl>=0 else ''}{pnl:.2f}" if pnl != 0 else ""
        msg = f"TRADE  {side} {sym}\nPrice: ${price:.2f}  Qty: {qty:.4f}{pnl_str}\n{reason}"
        await self._broadcast_alert(msg)

    # ---- command handlers ----

    def _register_handlers(self):
        app = self._app
        app.add_handler(CommandHandler("pause", self._cmd_pause))
        app.add_handler(CommandHandler("resume", self._cmd_resume))
        app.add_handler(CommandHandler("start", self._cmd_start_bot))
        app.add_handler(CommandHandler("stop", self._cmd_stop_bot))
        app.add_handler(CommandHandler("status", self._cmd_status))
        app.add_handler(CommandHandler("portfolio", self._cmd_portfolio))
        app.add_handler(CommandHandler("new", self._cmd_new))
        app.add_handler(CommandHandler("cancel", self._cmd_cancel))
        app.add_handler(CommandHandler("cancelall", self._cmd_cancelall))
        app.add_handler(CommandHandler("history", self._cmd_history))
        app.add_handler(CommandHandler("help", self._cmd_help))

    def _authorised(self, update: Update) -> bool:
        cid = str(update.effective_chat.id)
        if not self.chat_ids:
            return True
        return cid in self.chat_ids

    async def _cmd_pause(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._authorised(update):
            return await update.message.reply_text("Unauthorised.")
        engine.paused = True
        await engine.save_state()
        await ws_manager.broadcast({"type": "BOT_STATUS", "running": engine.running, "paused": True})
        await update.message.reply_text("All trading PAUSED.")
        await self._broadcast_alert("Trading has been PAUSED via Telegram command.")

    async def _cmd_resume(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._authorised(update):
            return await update.message.reply_text("Unauthorised.")
        engine.paused = False
        await engine.save_state()
        await ws_manager.broadcast({"type": "BOT_STATUS", "running": engine.running, "paused": False})
        await update.message.reply_text("Trading RESUMED.")
        await self._broadcast_alert("Trading has been RESUMED via Telegram command.")

    async def _cmd_start_bot(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._authorised(update):
            return await update.message.reply_text("Unauthorised.")
        engine.running = True
        await engine.save_state()
        await ws_manager.broadcast({"type": "BOT_STATUS", "running": True, "paused": engine.paused})
        await update.message.reply_text("Bot engine STARTED.")

    async def _cmd_stop_bot(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._authorised(update):
            return await update.message.reply_text("Unauthorised.")
        engine.running = False
        await engine.save_state()
        await ws_manager.broadcast({"type": "BOT_STATUS", "running": False, "paused": engine.paused})
        await update.message.reply_text("Bot engine STOPPED.")

    async def _cmd_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._authorised(update):
            return await update.message.reply_text("Unauthorised.")
        tickers = await db.tickers.find({}, {"_id": 0}).to_list(100)
        active = sum(1 for t in tickers if t.get("enabled"))
        profits_cursor = db.profits.find({}, {"_id": 0})
        profits_list = await profits_cursor.to_list(100)
        total_pnl = sum(p.get("total_pnl", 0) for p in profits_list)
        lines = [
            f"Running: {'YES' if engine.running else 'NO'}",
            f"Paused: {'YES' if engine.paused else 'NO'}",
            f"Market: {'OPEN' if engine.is_market_open() else 'CLOSED'}",
            f"Tickers: {active}/{len(tickers)} active",
            f"Total P&L: ${total_pnl:.2f}",
        ]
        await update.message.reply_text("\n".join(lines))

    async def _cmd_portfolio(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._authorised(update):
            return await update.message.reply_text("Unauthorised.")
        profits_cursor = db.profits.find({}, {"_id": 0})
        profits_list = await profits_cursor.to_list(100)
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

    async def _cmd_new(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._authorised(update):
            return await update.message.reply_text("Unauthorised.")
        parts = (update.message.text or "").split()
        if len(parts) < 2:
            return await update.message.reply_text("Usage: /new SYMBOL [POWER]\nExample: /new MSFT 200")
        sym = parts[1].upper().strip()
        power = float(parts[2]) if len(parts) >= 3 else 100.0
        existing = await db.tickers.find_one({"symbol": sym})
        if existing:
            return await update.message.reply_text(f"{sym} already exists.")
        t = TickerConfig(symbol=sym, base_power=power)
        doc = t.model_dump()
        await db.tickers.insert_one(doc)
        doc.pop("_id", None)
        await ws_manager.broadcast({"type": "TICKER_ADDED", "ticker": doc})
        await update.message.reply_text(f"Added {sym} with ${power:.0f} buy power.")

    async def _cmd_cancel(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._authorised(update):
            return await update.message.reply_text("Unauthorised.")
        parts = (update.message.text or "").split()
        if len(parts) < 2:
            return await update.message.reply_text("Usage: /cancel SYMBOL")
        sym = parts[1].upper()
        result = await db.tickers.update_one({"symbol": sym}, {"$set": {"enabled": False}})
        if result.matched_count == 0:
            return await update.message.reply_text(f"{sym} not found.")
        engine._positions.pop(sym, None)
        engine._trailing_highs.pop(sym, None)
        doc = await db.tickers.find_one({"symbol": sym}, {"_id": 0})
        if doc:
            await ws_manager.broadcast({"type": "TICKER_UPDATED", "ticker": doc})
        await update.message.reply_text(f"{sym} disabled and orders cancelled.")

    async def _cmd_cancelall(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._authorised(update):
            return await update.message.reply_text("Unauthorised.")
        await db.tickers.update_many({}, {"$set": {"enabled": False}})
        engine._positions.clear()
        engine._trailing_highs.clear()
        tickers = await db.tickers.find({}, {"_id": 0}).to_list(100)
        for t in tickers:
            await ws_manager.broadcast({"type": "TICKER_UPDATED", "ticker": t})
        await update.message.reply_text("All tickers disabled and orders cancelled.")

    async def _cmd_history(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._authorised(update):
            return await update.message.reply_text("Unauthorised.")
        trades = await db.trades.find({}, {"_id": 0}).sort("timestamp", -1).to_list(10)
        if not trades:
            return await update.message.reply_text("No trade history.")
        lines = ["Recent Trades:"]
        for t in trades:
            pnl_str = f" P&L:{t.get('pnl',0):+.2f}" if t.get("pnl", 0) != 0 else ""
            lines.append(f"{t['side']} {t['symbol']} @${t['price']:.2f} x{t['quantity']:.4f}{pnl_str}")
        await update.message.reply_text("\n".join(lines))

    async def _cmd_help(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        text = (
            "BracketBot Commands:\n"
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
            "/help    - This message"
        )
        await update.message.reply_text(text)


telegram_service = TelegramService()


# --- PRESET STRATEGIES ---
PRESET_STRATEGIES = {
    "conservative_1y": PresetStrategy(
        name="Conservative 1-Year Bracket",
        avg_days=365, buy_offset=-5.0, buy_percent=True,
        sell_offset=8.0, sell_percent=True, stop_offset=-10.0,
        stop_percent=True, trailing_enabled=False, trailing_percent=3.0
    ),
    "aggressive_monthly": PresetStrategy(
        name="Aggressive Monthly Dip-Buy",
        avg_days=30, buy_offset=-2.0, buy_percent=True,
        sell_offset=4.0, sell_percent=True, stop_offset=-5.0,
        stop_percent=True, trailing_enabled=True, trailing_percent=1.5
    ),
    "swing_trader": PresetStrategy(
        name="Swing Trader",
        avg_days=14, buy_offset=-1.5, buy_percent=True,
        sell_offset=3.0, sell_percent=True, stop_offset=-3.0,
        stop_percent=True, trailing_enabled=True, trailing_percent=2.0
    ),
}


# --- BACKGROUND TASKS ---
async def price_broadcast_loop():
    while True:
        try:
            tickers = await db.tickers.find({}, {"_id": 0}).to_list(100)
            if tickers:
                prices = {}
                for t in tickers:
                    sym = t["symbol"]
                    prices[sym] = await price_service.get_price(sym)

                positions = {}
                for sym, pos in engine._positions.items():
                    if pos["qty"] > 0:
                        cp = prices.get(sym, 0)
                        mv = round(cp * pos["qty"], 2)
                        positions[sym] = {
                            "symbol": sym,
                            "quantity": pos["qty"],
                            "avg_entry": pos["avg_entry"],
                            "current_price": cp,
                            "market_value": mv,
                            "unrealized_pnl": round((cp - pos["avg_entry"]) * pos["qty"], 2)
                        }

                profits_cursor = db.profits.find({}, {"_id": 0})
                profits_list = await profits_cursor.to_list(100)
                profits = {p["symbol"]: p.get("total_pnl", 0) for p in profits_list}

                cash_doc = await db.settings.find_one({"key": "cash_reserve"}, {"_id": 0})
                cash_reserve = round(cash_doc.get("value", 0), 2) if cash_doc else 0

                await ws_manager.broadcast({
                    "type": "PRICE_UPDATE",
                    "prices": prices,
                    "positions": positions,
                    "profits": profits,
                    "cash_reserve": cash_reserve,
                    "paused": engine.paused,
                    "running": engine.running,
                    "market_open": engine.is_market_open(),
                })
        except Exception as e:
            logger.error(f"Price broadcast error: {e}")
        await asyncio.sleep(2)


async def trading_loop():
    while True:
        try:
            if engine.running and not engine.paused and engine.is_market_open():
                tickers = await db.tickers.find({"enabled": True}, {"_id": 0}).to_list(100)
                for t in tickers:
                    try:
                        await engine.evaluate_ticker(t)
                    except Exception as te:
                        logger.error(f"Evaluate {t.get('symbol','?')} error: {te}")
            elif engine.running and not engine.paused and not engine.is_market_open():
                # Log once per minute that market is closed
                pass
        except Exception as e:
            logger.error(f"Trading loop error: {e}")
        await asyncio.sleep(5)


# --- APP LIFECYCLE ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.tickers.create_index("symbol", unique=True)
    await db.trades.create_index("timestamp")
    await db.profits.create_index("symbol", unique=True)
    # Seed defaults if empty
    count = await db.tickers.count_documents({})
    if count == 0:
        for sym in ["TSLA", "AAPL", "NVDA"]:
            t = TickerConfig(symbol=sym, base_power=100.0)
            await db.tickers.update_one(
                {"symbol": sym}, {"$setOnInsert": t.model_dump()}, upsert=True
            )
    # Restore engine state from DB (survives restarts)
    await engine.load_state()
    asyncio.create_task(price_broadcast_loop())
    asyncio.create_task(trading_loop())
    # Start Telegram if token exists in DB
    try:
        await telegram_service.reload_from_db()
    except Exception as e:
        logger.warning(f"Telegram auto-start failed: {e}")
    logger.info("BracketBot Engine started")
    yield
    # Shutdown: send offline alert then close
    try:
        await telegram_service.stop()
    except Exception:
        pass
    mongo_client.close()


# --- FASTAPI APP ---
app = FastAPI(title="BracketBot", lifespan=lifespan)
api = APIRouter(prefix="/api")

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- REST ENDPOINTS ---
@api.get("/health")
async def health():
    return {
        "status": "online",
        "running": engine.running,
        "paused": engine.paused,
        "market_open": engine.is_market_open(),
        "yfinance": YF_AVAILABLE,
        "telegram": telegram_service.running,
        "ws_clients": len(ws_manager.active),
    }

@api.get("/tickers")
async def get_tickers():
    docs = await db.tickers.find({}, {"_id": 0}).to_list(100)
    return docs

@api.post("/tickers")
async def add_ticker(body: TickerCreate):
    sym = body.symbol.upper().strip()
    existing = await db.tickers.find_one({"symbol": sym})
    if existing:
        raise HTTPException(400, f"{sym} already exists")
    t = TickerConfig(symbol=sym, base_power=body.base_power)
    doc = t.model_dump()
    await db.tickers.insert_one(doc)
    doc.pop("_id", None)
    await ws_manager.broadcast({"type": "TICKER_ADDED", "ticker": doc})
    return doc

@api.put("/tickers/{symbol}")
async def update_ticker(symbol: str, body: TickerUpdate):
    sym = symbol.upper()
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "No updates provided")
    result = await db.tickers.update_one({"symbol": sym}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(404, f"{sym} not found")
    doc = await db.tickers.find_one({"symbol": sym}, {"_id": 0})
    await ws_manager.broadcast({"type": "TICKER_UPDATED", "ticker": doc})
    return doc

@api.delete("/tickers/{symbol}")
async def delete_ticker(symbol: str):
    sym = symbol.upper()
    result = await db.tickers.delete_one({"symbol": sym})
    if result.deleted_count == 0:
        raise HTTPException(404, f"{sym} not found")
    engine._positions.pop(sym, None)
    engine._trailing_highs.pop(sym, None)
    await ws_manager.broadcast({"type": "TICKER_DELETED", "symbol": sym})
    return {"deleted": sym}

@api.post("/tickers/{symbol}/strategy/{preset}")
async def apply_strategy(symbol: str, preset: str):
    sym = symbol.upper()
    current_doc = await db.tickers.find_one({"symbol": sym}, {"_id": 0})
    if not current_doc:
        raise HTTPException(404, f"{sym} not found")

    # Toggle OFF: restore custom backup
    if current_doc.get("strategy") == preset:
        backup = current_doc.get("custom_backup", {})
        if backup:
            backup["strategy"] = "custom"
            await db.tickers.update_one({"symbol": sym}, {"$set": backup, "$unset": {"custom_backup": ""}})
        else:
            await db.tickers.update_one({"symbol": sym}, {"$set": {"strategy": "custom"}})
        doc = await db.tickers.find_one({"symbol": sym}, {"_id": 0})
        return doc

    # Toggle ON: backup + apply
    strategy = PRESET_STRATEGIES.get(preset)
    if not strategy:
        raise HTTPException(400, f"Unknown preset: {preset}")
    backup_fields = {
        "avg_days": current_doc.get("avg_days"),
        "buy_offset": current_doc.get("buy_offset"),
        "buy_percent": current_doc.get("buy_percent"),
        "buy_order_type": current_doc.get("buy_order_type", "limit"),
        "sell_offset": current_doc.get("sell_offset"),
        "sell_percent": current_doc.get("sell_percent"),
        "sell_order_type": current_doc.get("sell_order_type", "limit"),
        "stop_offset": current_doc.get("stop_offset"),
        "stop_percent": current_doc.get("stop_percent"),
        "stop_order_type": current_doc.get("stop_order_type", "limit"),
        "trailing_enabled": current_doc.get("trailing_enabled"),
        "trailing_percent": current_doc.get("trailing_percent"),
        "trailing_percent_mode": current_doc.get("trailing_percent_mode", True),
        "trailing_order_type": current_doc.get("trailing_order_type", "limit"),
    }
    updates = strategy.model_dump()
    updates.pop("name")
    updates["strategy"] = preset
    updates["custom_backup"] = backup_fields
    await db.tickers.update_one({"symbol": sym}, {"$set": updates})
    doc = await db.tickers.find_one({"symbol": sym}, {"_id": 0})
    return doc

@api.get("/strategies")
async def get_strategies():
    return {k: v.model_dump() for k, v in PRESET_STRATEGIES.items()}

@api.get("/trades")
async def get_trades(limit: int = Query(50, le=200)):
    docs = await db.trades.find({}, {"_id": 0}).sort("timestamp", -1).to_list(limit)
    return docs

@api.get("/portfolio")
async def get_portfolio():
    profits_cursor = db.profits.find({}, {"_id": 0})
    profits_list = await profits_cursor.to_list(100)
    total_pnl = sum(p.get("total_pnl", 0) for p in profits_list)
    total_trades = sum(p.get("trade_count", 0) for p in profits_list)

    positions = []
    total_equity = 0
    for sym, pos in engine._positions.items():
        if pos["qty"] > 0:
            cp = engine._prices.get(sym, pos["avg_entry"])
            val = cp * pos["qty"]
            total_equity += val
            positions.append({
                "symbol": sym,
                "quantity": pos["qty"],
                "avg_entry": pos["avg_entry"],
                "current_price": cp,
                "market_value": round(val, 2),
                "unrealized_pnl": round((cp - pos["avg_entry"]) * pos["qty"], 2)
            })

    tickers = await db.tickers.find({}, {"_id": 0}).to_list(100)
    total_buying_power = sum(t.get("base_power", 0) for t in tickers if t.get("enabled"))

    wins = await db.trades.count_documents({"pnl": {"$gt": 0}})
    losses = await db.trades.count_documents({"pnl": {"$lt": 0}})
    win_rate = round(wins / (wins + losses) * 100, 1) if (wins + losses) > 0 else 0

    return {
        "total_pnl": round(total_pnl, 2),
        "total_equity": round(total_equity, 2),
        "buying_power": round(total_buying_power, 2),
        "total_trades": total_trades,
        "win_rate": win_rate,
        "positions": positions,
        "profits_by_symbol": {p["symbol"]: round(p.get("total_pnl", 0), 2) for p in profits_list}
    }

@api.get("/positions")
async def get_positions():
    positions = []
    for sym, pos in engine._positions.items():
        if pos["qty"] > 0:
            cp = engine._prices.get(sym, pos["avg_entry"])
            positions.append({
                "symbol": sym,
                "quantity": pos["qty"],
                "avg_entry": pos["avg_entry"],
                "current_price": cp,
                "market_value": round(cp * pos["qty"], 2),
                "unrealized_pnl": round((cp - pos["avg_entry"]) * pos["qty"], 2)
            })
    return positions

@api.get("/logs")
async def get_logs(limit: int = Query(100, le=500), level: str = "ALL"):
    docs = await db.logs.find({}, {"_id": 0}).sort("timestamp", -1).to_list(limit)
    if level != "ALL":
        docs = [d for d in docs if d.get("level", "").upper() == level.upper()]
    return docs

# Bot control
@api.post("/bot/start")
async def start_bot():
    engine.running = True
    await engine.save_state()
    await ws_manager.broadcast({"type": "BOT_STATUS", "running": True, "paused": engine.paused})
    logger.info("Bot STARTED via API")
    return {"running": True}

@api.post("/bot/stop")
async def stop_bot():
    engine.running = False
    await engine.save_state()
    await ws_manager.broadcast({"type": "BOT_STATUS", "running": False, "paused": engine.paused})
    logger.info("Bot STOPPED via API")
    return {"running": False}

@api.post("/bot/pause")
async def pause_bot():
    engine.paused = not engine.paused
    await engine.save_state()
    await ws_manager.broadcast({"type": "BOT_STATUS", "running": engine.running, "paused": engine.paused})
    logger.info(f"Bot {'PAUSED' if engine.paused else 'UNPAUSED'} via API")
    return {"paused": engine.paused}

# Take Profit: zero out P&L for a symbol, move to cash reserve
@api.post("/tickers/{symbol}/take-profit")
async def take_profit(symbol: str):
    sym = symbol.upper()
    profit_doc = await db.profits.find_one({"symbol": sym}, {"_id": 0})
    if not profit_doc or profit_doc.get("total_pnl", 0) <= 0:
        raise HTTPException(400, f"No positive profit to take for {sym}")
    amount = profit_doc.get("total_pnl", 0)
    # Record the cash withdrawal
    await db.cash_ledger.insert_one({
        "symbol": sym,
        "amount": amount,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": "TAKE_PROFIT",
    })
    # Accumulate total cash
    await db.settings.update_one(
        {"key": "cash_reserve"},
        {"$inc": {"value": amount}},
        upsert=True,
    )
    # Zero out the symbol's profit
    await db.profits.update_one(
        {"symbol": sym},
        {"$set": {"total_pnl": 0, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    logger.info(f"TAKE PROFIT: {sym} ${amount:.2f} moved to cash reserve")
    # Broadcast updated profits
    profits_cursor = db.profits.find({}, {"_id": 0})
    profits_list = await profits_cursor.to_list(100)
    profits = {p["symbol"]: p.get("total_pnl", 0) for p in profits_list}
    cash_doc = await db.settings.find_one({"key": "cash_reserve"}, {"_id": 0})
    cash_total = cash_doc.get("value", 0) if cash_doc else 0
    await ws_manager.broadcast({
        "type": "PROFITS_UPDATE",
        "profits": profits,
        "cash_reserve": round(cash_total, 2),
    })
    return {"taken": round(amount, 2), "symbol": sym, "cash_reserve": round(cash_total, 2)}

@api.get("/cash-reserve")
async def get_cash_reserve():
    cash_doc = await db.settings.find_one({"key": "cash_reserve"}, {"_id": 0})
    cash_total = cash_doc.get("value", 0) if cash_doc else 0
    ledger = await db.cash_ledger.find({}, {"_id": 0}).sort("timestamp", -1).to_list(50)
    return {"total": round(cash_total, 2), "ledger": ledger}

@api.post("/settings")
async def update_settings(body: SettingsUpdate):
    if body.simulate_24_7 is not None:
        engine.simulate_24_7 = body.simulate_24_7
        await engine.save_state()
    if body.increment_step is not None:
        await db.settings.update_one(
            {"key": "increment_step"}, {"$set": {"value": body.increment_step}}, upsert=True
        )
    if body.decrement_step is not None:
        await db.settings.update_one(
            {"key": "decrement_step"}, {"$set": {"value": body.decrement_step}}, upsert=True
        )
    if body.telegram:
        doc = body.telegram.model_dump()
        await db.settings.update_one(
            {"key": "telegram"}, {"$set": {"value": doc}}, upsert=True
        )
        # (Re)start or stop Telegram bot based on new token
        if doc.get("bot_token"):
            try:
                await telegram_service.start(doc["bot_token"], doc.get("chat_ids", []))
            except Exception as e:
                logger.error(f"Telegram start failed: {e}")
        else:
            await telegram_service.stop()
    return {"ok": True, "telegram_running": telegram_service.running}

@api.get("/settings")
async def get_settings():
    tg = await db.settings.find_one({"key": "telegram"}, {"_id": 0})
    inc_doc = await db.settings.find_one({"key": "increment_step"}, {"_id": 0})
    dec_doc = await db.settings.find_one({"key": "decrement_step"}, {"_id": 0})
    cash_doc = await db.settings.find_one({"key": "cash_reserve"}, {"_id": 0})
    return {
        "simulate_24_7": engine.simulate_24_7,
        "telegram": tg.get("value", {}) if tg else {"bot_token": "", "chat_ids": []},
        "telegram_connected": telegram_service.running,
        "increment_step": inc_doc.get("value", 0.5) if inc_doc else 0.5,
        "decrement_step": dec_doc.get("value", 0.5) if dec_doc else 0.5,
        "cash_reserve": round(cash_doc.get("value", 0), 2) if cash_doc else 0,
    }

@api.post("/settings/telegram/test")
async def test_telegram():
    """Send a test alert to all registered chat IDs."""
    if not telegram_service.running:
        raise HTTPException(400, "Telegram bot is not connected. Save a valid token first.")
    await telegram_service._broadcast_alert("Test alert from BracketBot! Connection verified.")
    return {"ok": True, "sent_to": telegram_service.chat_ids}

# --- WEBSOCKET ---
@api.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        tickers = await db.tickers.find({}, {"_id": 0}).to_list(100)
        prices = {}
        for t in tickers:
            prices[t["symbol"]] = await price_service.get_price(t["symbol"])

        profits_cursor = db.profits.find({}, {"_id": 0})
        profits_list = await profits_cursor.to_list(100)
        profits = {p["symbol"]: p.get("total_pnl", 0) for p in profits_list}

        cash_doc = await db.settings.find_one({"key": "cash_reserve"}, {"_id": 0})
        cash_reserve = round(cash_doc.get("value", 0), 2) if cash_doc else 0

        inc_doc = await db.settings.find_one({"key": "increment_step"}, {"_id": 0})
        dec_doc = await db.settings.find_one({"key": "decrement_step"}, {"_id": 0})

        await websocket.send_json({
            "type": "INITIAL_STATE",
            "tickers": tickers,
            "prices": prices,
            "profits": profits,
            "cash_reserve": cash_reserve,
            "increment_step": inc_doc.get("value", 0.5) if inc_doc else 0.5,
            "decrement_step": dec_doc.get("value", 0.5) if dec_doc else 0.5,
            "paused": engine.paused,
            "running": engine.running,
            "market_open": engine.is_market_open(),
        })

        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            action = msg.get("action")

            if action == "ADD_TICKER":
                sym = msg.get("symbol", "").upper().strip()
                if sym:
                    t = TickerConfig(symbol=sym, base_power=msg.get("base_power", 100.0))
                    doc = t.model_dump()
                    try:
                        await db.tickers.insert_one(doc)
                        doc.pop("_id", None)
                        await ws_manager.broadcast({"type": "TICKER_ADDED", "ticker": doc})
                    except Exception:
                        pass

            elif action == "DELETE_TICKER":
                sym = msg.get("symbol", "").upper()
                await db.tickers.delete_one({"symbol": sym})
                engine._positions.pop(sym, None)
                await ws_manager.broadcast({"type": "TICKER_DELETED", "symbol": sym})

            elif action == "UPDATE_TICKER":
                sym = msg.get("symbol", "").upper()
                updates = {k: v for k, v in msg.items() if k not in ("action", "symbol")}
                if updates:
                    await db.tickers.update_one({"symbol": sym}, {"$set": updates})
                    doc = await db.tickers.find_one({"symbol": sym}, {"_id": 0})
                    if doc:
                        await ws_manager.broadcast({"type": "TICKER_UPDATED", "ticker": doc})

            elif action == "GLOBAL_PAUSE":
                engine.paused = msg.get("pause", False)
                await engine.save_state()
                await ws_manager.broadcast({"type": "BOT_STATUS", "running": engine.running, "paused": engine.paused})

            elif action == "START_BOT":
                engine.running = True
                await engine.save_state()
                await ws_manager.broadcast({"type": "BOT_STATUS", "running": True, "paused": engine.paused})

            elif action == "STOP_BOT":
                engine.running = False
                await engine.save_state()
                await ws_manager.broadcast({"type": "BOT_STATUS", "running": False, "paused": engine.paused})

            elif action == "APPLY_STRATEGY":
                sym = msg.get("symbol", "").upper()
                preset = msg.get("preset", "")
                current_doc = await db.tickers.find_one({"symbol": sym}, {"_id": 0})
                if not current_doc:
                    continue

                # Toggle OFF: if already on this preset, restore custom backup
                if current_doc.get("strategy") == preset:
                    backup = current_doc.get("custom_backup", {})
                    if backup:
                        backup["strategy"] = "custom"
                        backup.pop("custom_backup", None)
                        await db.tickers.update_one({"symbol": sym}, {"$set": backup, "$unset": {"custom_backup": ""}})
                    else:
                        await db.tickers.update_one({"symbol": sym}, {"$set": {"strategy": "custom"}})
                    doc = await db.tickers.find_one({"symbol": sym}, {"_id": 0})
                    if doc:
                        await ws_manager.broadcast({"type": "TICKER_UPDATED", "ticker": doc})
                    continue

                # Toggle ON: backup current custom config, then apply preset
                strategy = PRESET_STRATEGIES.get(preset)
                if strategy:
                    backup_fields = {
                        "avg_days": current_doc.get("avg_days"),
                        "buy_offset": current_doc.get("buy_offset"),
                        "buy_percent": current_doc.get("buy_percent"),
                        "buy_order_type": current_doc.get("buy_order_type", "limit"),
                        "sell_offset": current_doc.get("sell_offset"),
                        "sell_percent": current_doc.get("sell_percent"),
                        "sell_order_type": current_doc.get("sell_order_type", "limit"),
                        "stop_offset": current_doc.get("stop_offset"),
                        "stop_percent": current_doc.get("stop_percent"),
                        "stop_order_type": current_doc.get("stop_order_type", "limit"),
                        "trailing_enabled": current_doc.get("trailing_enabled"),
                        "trailing_percent": current_doc.get("trailing_percent"),
                        "trailing_percent_mode": current_doc.get("trailing_percent_mode", True),
                        "trailing_order_type": current_doc.get("trailing_order_type", "limit"),
                    }
                    updates = strategy.model_dump()
                    updates.pop("name")
                    updates["strategy"] = preset
                    updates["custom_backup"] = backup_fields
                    await db.tickers.update_one({"symbol": sym}, {"$set": updates})
                    doc = await db.tickers.find_one({"symbol": sym}, {"_id": 0})
                    if doc:
                        await ws_manager.broadcast({"type": "TICKER_UPDATED", "ticker": doc})

            elif action == "TAKE_PROFIT":
                sym = msg.get("symbol", "").upper()
                profit_doc = await db.profits.find_one({"symbol": sym}, {"_id": 0})
                if profit_doc and profit_doc.get("total_pnl", 0) > 0:
                    amount = profit_doc["total_pnl"]
                    await db.cash_ledger.insert_one({
                        "symbol": sym, "amount": amount,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "type": "TAKE_PROFIT",
                    })
                    await db.settings.update_one(
                        {"key": "cash_reserve"}, {"$inc": {"value": amount}}, upsert=True
                    )
                    await db.profits.update_one(
                        {"symbol": sym},
                        {"$set": {"total_pnl": 0, "updated_at": datetime.now(timezone.utc).isoformat()}}
                    )
                    profits_cursor = db.profits.find({}, {"_id": 0})
                    profits_list = await profits_cursor.to_list(100)
                    profits = {p["symbol"]: p.get("total_pnl", 0) for p in profits_list}
                    cash_doc = await db.settings.find_one({"key": "cash_reserve"}, {"_id": 0})
                    cash_total = round(cash_doc.get("value", 0), 2) if cash_doc else 0
                    await ws_manager.broadcast({
                        "type": "PROFITS_UPDATE",
                        "profits": profits,
                        "cash_reserve": cash_total,
                    })

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)


app.include_router(api)
