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
logger = logging.getLogger("SentinelPulse")

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
    compound_profits: bool = True
    max_daily_loss: float = 0  # 0 = disabled, positive $ amount
    max_consecutive_losses: int = 0  # 0 = disabled
    auto_stopped: bool = False
    auto_stop_reason: str = ""
    auto_rebracket: bool = False
    rebracket_threshold: float = 2.0
    rebracket_spread: float = 0.80
    rebracket_cooldown: int = 0        # seconds between rebrackets, 0 = no cooldown
    rebracket_lookback: int = 10       # number of recent ticks to evaluate
    rebracket_buffer: float = 0.10     # $ below recent low for new buy target
    enabled: bool = True
    strategy: str = "custom"
    sort_order: int = 0
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
    compound_profits: Optional[bool] = None
    max_daily_loss: Optional[float] = None
    max_consecutive_losses: Optional[int] = None
    auto_stopped: Optional[bool] = None
    auto_stop_reason: Optional[str] = None
    auto_rebracket: Optional[bool] = None
    rebracket_threshold: Optional[float] = None
    rebracket_spread: Optional[float] = None
    rebracket_cooldown: Optional[int] = None
    rebracket_lookback: Optional[int] = None
    rebracket_buffer: Optional[float] = None
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
    # --- Rich metadata ---
    order_type: str = ""          # MARKET or LIMIT
    rule_mode: str = ""           # PERCENT or DOLLAR
    entry_price: float = 0.0     # avg entry price (for sell-side trades)
    target_price: float = 0.0    # the trigger/target price for this trade
    total_value: float = 0.0     # price * quantity (cost for buys, proceeds for sells)
    buy_power: float = 0.0       # buying power used/available at time of trade
    avg_price: float = 0.0       # moving average price at time of trade
    # Sell-side specifics
    sell_target: float = 0.0     # configured sell target at time of trade
    stop_target: float = 0.0     # configured stop-loss target at time of trade
    # Trailing stop specifics
    trail_high: float = 0.0      # highest price seen before trailing stop triggered
    trail_trigger: float = 0.0   # the trailing stop trigger level
    trail_value: float = 0.0     # the trailing % or $ value configured
    trail_mode: str = ""         # PERCENT or DOLLAR for trailing stop

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
    account_balance: Optional[float] = None

class BetaRegistration(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone: str = ""
    ssn_last4: str
    address_street: str
    address_city: str
    address_state: str
    address_zip: str
    address_country: str
    agreement_accepted: bool
    agreement_version: str = "1.0"
    jurisdiction: str = ""
    registered_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class FeedbackReport(BaseModel):
    type: str = "bug"  # bug, error, suggestion, complaint
    subject: str
    description: str
    error_log: str = ""


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
        self._recent_prices: Dict[str, list] = {}  # rolling window for rebracket
        self._last_rebracket_ts: Dict[str, datetime] = {}  # per-symbol rebracket cooldown

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
        if ticker_doc.get("auto_stopped", False):
            return

        # Per-symbol cooldown: skip if we traded too recently
        now = datetime.now(timezone.utc)
        last = self._last_trade_ts.get(sym)
        if last and (now - last).total_seconds() < self.TRADE_COOLDOWN_SECS:
            return

        with _tracer.start_as_current_span("ticker.evaluate", attributes={
            "ticker.symbol": sym,
            "ticker.buy_power": ticker_doc.get("base_power", 0),
            "ticker.enabled": ticker_doc.get("enabled", True),
        }):
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
        compound = ticker_doc.get("compound_profits", True)
        base_power = ticker_doc.get("base_power", 100.0)

        # Percent mode: offset from average. Dollar mode: ABSOLUTE target price.
        buy_target = round(avg * (1 + buy_off / 100), 2) if is_buy_pct else round(buy_off, 2)

        pos = self._positions.get(sym, {"qty": 0, "avg_entry": 0})
        entry = pos.get("avg_entry", 0)

        # Sell/Stop targets: when holding a position and in percent mode,
        # anchor to ENTRY PRICE so targets don't drift with the rolling average.
        if pos["qty"] > 0 and entry > 0:
            sell_target = round(entry * (1 + sell_off / 100), 2) if is_sell_pct else round(sell_off, 2)
            stop_target = round(entry * (1 + stop_off / 100), 2) if is_stop_pct else round(stop_off, 2)
        else:
            sell_target = round(avg * (1 + sell_off / 100), 2) if is_sell_pct else round(sell_off, 2)
            stop_target = round(avg * (1 + stop_off / 100), 2) if is_stop_pct else round(stop_off, 2)

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
                        reason=f"[{order_label}] Price ${exec_price} {'(market)' if buy_otype == 'market' else f'<= buy target ${buy_target}'}",
                        order_type=buy_otype.upper(),
                        rule_mode="PERCENT" if is_buy_pct else "DOLLAR",
                        target_price=buy_target,
                        total_value=round(exec_price * qty, 2),
                        buy_power=base_power,
                        avg_price=avg,
                        sell_target=sell_target,
                        stop_target=stop_target,
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
                        quantity=pos["qty"], reason=f"[{order_label}] Trailing stop hit ${trail_stop} (high ${high})", pnl=pnl,
                        order_type=trail_otype.upper(),
                        rule_mode="PERCENT" if is_sell_pct else "DOLLAR",
                        entry_price=entry,
                        target_price=trail_stop,
                        total_value=round(exec_price * pos["qty"], 2),
                        buy_power=base_power,
                        avg_price=avg,
                        sell_target=sell_target,
                        stop_target=stop_target,
                        trail_high=high,
                        trail_trigger=trail_stop,
                        trail_value=trail_pct,
                        trail_mode="PERCENT" if trail_is_pct else "DOLLAR",
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
                trade = TradeRecord(
                    symbol=sym, side="SELL", price=exec_price, quantity=pos["qty"],
                    reason=f"[{order_label}] Price ${exec_price} {'(market)' if sell_otype == 'market' else f'>= sell target ${sell_target}'}", pnl=pnl,
                    order_type=sell_otype.upper(),
                    rule_mode="PERCENT" if is_sell_pct else "DOLLAR",
                    entry_price=entry,
                    target_price=sell_target,
                    total_value=round(exec_price * pos["qty"], 2),
                    buy_power=base_power,
                    avg_price=avg,
                    sell_target=sell_target,
                    stop_target=stop_target,
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
                    trade = TradeRecord(
                        symbol=sym, side="STOP", price=exec_price, quantity=pos["qty"],
                        reason=f"[{order_label}] Stop-loss hit ${exec_price} {'(market)' if stop_otype == 'market' else f'<= ${stop_target}'}", pnl=pnl,
                        order_type=stop_otype.upper(),
                        rule_mode="PERCENT" if is_stop_pct else "DOLLAR",
                        entry_price=entry,
                        target_price=stop_target,
                        total_value=round(exec_price * pos["qty"], 2),
                        buy_power=base_power,
                        avg_price=avg,
                        sell_target=sell_target,
                        stop_target=stop_target,
                    )
                    await self._record_trade(trade)
                    self._positions[sym] = {"qty": 0, "avg_entry": 0}
                    self._trailing_highs.pop(sym, None)
                    await self._update_profit(sym, pnl, compound)

        # --- AUTO REBRACKET ---
        rebracket_on = ticker_doc.get("auto_rebracket", False)
        if rebracket_on and pos["qty"] == 0:
            threshold = ticker_doc.get("rebracket_threshold", 2.0)
            spread = ticker_doc.get("rebracket_spread", 0.80)
            cooldown = ticker_doc.get("rebracket_cooldown", 0)
            lookback = max(2, ticker_doc.get("rebracket_lookback", 10))
            buffer = ticker_doc.get("rebracket_buffer", 0.10)

            # Rebracket cooldown: skip if we rebracketed too recently
            now = datetime.now(timezone.utc)
            if cooldown > 0:
                last_rb = self._last_rebracket_ts.get(sym)
                if last_rb and (now - last_rb).total_seconds() < cooldown:
                    return

            # Track rolling recent prices (configurable lookback)
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

                # Switch to dollar mode and update bracket
                await db.tickers.update_one(
                    {"symbol": sym},
                    {"$set": {
                        "buy_offset": new_buy,
                        "buy_percent": False,
                        "sell_offset": new_sell,
                        "sell_percent": False,
                    }}
                )
                doc = await db.tickers.find_one({"symbol": sym}, {"_id": 0})
                if doc:
                    await ws_manager.broadcast({"type": "TICKER_UPDATED", "ticker": doc})

                self._last_rebracket_ts[sym] = now
                direction = "UP" if drifted_up else "DOWN"
                logger.info(f"REBRACKET: {sym} drifted {direction} — new bracket ${new_buy} / ${new_sell} (was ${old_buy} / ${old_sell}) [lookback={lookback}, buffer=${buffer}, cooldown={cooldown}s]")

                # Record rebracket as a trace span
                with _tracer.start_as_current_span("ticker.rebracket", attributes={
                    "rebracket.symbol": sym, "rebracket.direction": direction,
                    "rebracket.old_buy": old_buy, "rebracket.old_sell": old_sell,
                    "rebracket.new_buy": new_buy, "rebracket.new_sell": new_sell,
                    "rebracket.price": price,
                }):
                    pass

                # Telegram notification
                try:
                    await telegram_service._broadcast_alert(
                        f"REBRACKET {sym}\n"
                        f"Price drifted {direction}: ${price:.2f}\n"
                        f"Old bracket: ${old_buy:.2f} / ${old_sell:.2f}\n"
                        f"New bracket: ${new_buy:.2f} / ${new_sell:.2f}\n"
                        f"Spread: ${spread:.2f}"
                    )
                except Exception:
                    pass

                # Reset recent prices after rebracket
                self._recent_prices[sym] = []

    async def _record_trade(self, trade: TradeRecord):
        with _tracer.start_as_current_span("trade.execute", attributes={
            "trade.id": trade.id,
            "trade.symbol": trade.symbol,
            "trade.side": trade.side,
            "trade.order_type": trade.order_type,
            "trade.price": trade.price,
            "trade.quantity": trade.quantity,
            "trade.total_value": trade.total_value,
            "trade.pnl": trade.pnl,
            "trade.rule_mode": trade.rule_mode,
        }) as span:
            doc = trade.model_dump()
            await db.trades.insert_one(doc)
            self._last_trade_ts[trade.symbol] = datetime.now(timezone.utc)
            pnl_str = f" P&L: ${trade.pnl:+.2f}" if trade.pnl != 0 else ""
            entry_str = f" entry=${trade.entry_price:.2f}" if trade.entry_price > 0 else ""
            logger.info(
                f"TRADE: {trade.order_type} {trade.side} {trade.symbol} @ ${trade.price:.2f} x{trade.quantity:.4f}"
                f" | {trade.rule_mode} mode | target=${trade.target_price:.2f}{entry_str}"
                f" | value=${trade.total_value:.2f} | power=${trade.buy_power:.2f}{pnl_str}"
            )
            clean = {k: v for k, v in doc.items() if k != "_id"}
            await ws_manager.broadcast({"type": "TRADE", "trade": clean})
            if trade.pnl < 0:
                span.set_attribute("trade.loss", True)
                span.add_event("loss_trade", {"pnl": trade.pnl, "symbol": trade.symbol})
            # Telegram alert
            try:
                await telegram_service.send_trade_alert(clean)
            except Exception:
                pass
            # Write loss log file
            if trade.pnl < 0:
                self._write_loss_log(trade)

    def _write_loss_log(self, trade: TradeRecord):
        """Write a detailed .txt file for every losing trade, organized by date."""
        try:
            ts = datetime.fromisoformat(trade.timestamp)
            date_str = ts.strftime("%Y-%m-%d")
            time_str = ts.strftime("%H-%M-%S")
            log_dir = ROOT_DIR / "trade_logs" / "losses" / date_str
            log_dir.mkdir(parents=True, exist_ok=True)

            filename = f"{trade.symbol}_{trade.side}_{time_str}_{trade.id[:8]}.txt"
            filepath = log_dir / filename

            pct_change = ((trade.price / trade.entry_price - 1) * 100) if trade.entry_price > 0 else 0

            lines = [
                f"{'='*60}",
                f"  LOSS TRADE LOG — {trade.symbol}",
                f"{'='*60}",
                f"",
                f"Trade ID:       {trade.id}",
                f"Timestamp:      {ts.strftime('%Y-%m-%d %H:%M:%S UTC')}",
                f"Symbol:         {trade.symbol}",
                f"Side:           {trade.side}",
                f"",
                f"--- ORDER INFO ---",
                f"Order Type:     {trade.order_type}",
                f"Rule Mode:      {trade.rule_mode}",
                f"",
                f"--- PRICES ---",
                f"Fill Price:     ${trade.price:.2f}",
                f"Entry Price:    ${trade.entry_price:.2f}" if trade.entry_price > 0 else f"Entry Price:    N/A (legacy trade)",
                f"Target Price:   ${trade.target_price:.2f}" if trade.target_price > 0 else f"Target Price:   N/A",
                f"Avg Price (MA): ${trade.avg_price:.2f}" if trade.avg_price > 0 else f"Avg Price (MA): N/A",
                f"",
                f"--- POSITION ---",
                f"Quantity:       {trade.quantity:.4f}",
                f"Total Value:    ${trade.total_value:.2f}",
                f"Buy Power:      ${trade.buy_power:.2f}",
                f"",
                f"--- TARGETS AT TIME OF TRADE ---",
                f"Sell Target:    ${trade.sell_target:.2f}" if trade.sell_target > 0 else f"Sell Target:    N/A",
                f"Stop Target:    ${trade.stop_target:.2f}" if trade.stop_target > 0 else f"Stop Target:    N/A",
                f"",
                f"--- P&L ---",
                f"P&L:            ${trade.pnl:+.2f}",
                f"% Change:       {pct_change:+.2f}%" if trade.entry_price > 0 else f"% Change:       N/A",
                f"",
            ]

            if trade.side == "TRAILING_STOP":
                lines += [
                    f"--- TRAILING STOP DETAILS ---",
                    f"Trail High:     ${trade.trail_high:.2f}",
                    f"Trail Trigger:  ${trade.trail_trigger:.2f}",
                    f"Trail Value:    {trade.trail_value}" + ("%" if trade.trail_mode == "PERCENT" else f" (${trade.trail_value:.2f})"),
                    f"Trail Mode:     {trade.trail_mode}",
                    f"",
                ]

            lines += [
                f"--- REASON ---",
                f"{trade.reason}",
                f"",
                f"{'='*60}",
            ]

            filepath.write_text("\n".join(lines))
            logger.info(f"LOSS LOG: Written to {filepath}")
        except Exception as e:
            logger.error(f"Failed to write loss log for {trade.symbol}: {e}")

    async def _update_profit(self, symbol: str, pnl: float, compound: bool = False):
        await db.profits.update_one(
            {"symbol": symbol},
            {"$inc": {"total_pnl": pnl, "trade_count": 1},
             "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True
        )
        # Compound: add positive profit to buy power
        if compound and pnl > 0:
            await db.tickers.update_one(
                {"symbol": symbol},
                {"$inc": {"base_power": round(pnl, 2)}}
            )
            doc = await db.tickers.find_one({"symbol": symbol}, {"_id": 0})
            if doc:
                await ws_manager.broadcast({"type": "TICKER_UPDATED", "ticker": doc})
                logger.info(f"COMPOUND: {symbol} buy power increased by ${pnl:.2f} to ${doc.get('base_power', 0):.2f}")

        # Check auto-stop conditions on losses
        if pnl < 0:
            await self._check_auto_stop(symbol)

    async def _check_auto_stop(self, symbol: str):
        ticker_doc = await db.tickers.find_one({"symbol": symbol}, {"_id": 0})
        if not ticker_doc:
            return

        max_daily = ticker_doc.get("max_daily_loss", 0)
        max_consec = ticker_doc.get("max_consecutive_losses", 0)
        reason = ""

        # Check daily loss limit
        if max_daily > 0:
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            pipeline = [
                {"$match": {"symbol": symbol, "pnl": {"$lt": 0}, "timestamp": {"$gte": today_start}}},
                {"$group": {"_id": None, "total_loss": {"$sum": "$pnl"}}}
            ]
            result = await db.trades.aggregate(pipeline).to_list(1)
            if result:
                daily_loss = abs(result[0]["total_loss"])
                if daily_loss >= max_daily:
                    reason = f"Daily loss ${daily_loss:.2f} exceeded limit ${max_daily:.2f}"

        # Check consecutive losses
        if not reason and max_consec > 0:
            recent = await db.trades.find(
                {"symbol": symbol, "side": {"$ne": "BUY"}},
                {"_id": 0, "pnl": 1}
            ).sort("timestamp", -1).limit(max_consec).to_list(max_consec)
            if len(recent) >= max_consec and all(t.get("pnl", 0) < 0 for t in recent):
                reason = f"{max_consec} consecutive losing trades"

        if reason:
            await db.tickers.update_one(
                {"symbol": symbol},
                {"$set": {"auto_stopped": True, "auto_stop_reason": reason, "enabled": False}}
            )
            doc = await db.tickers.find_one({"symbol": symbol}, {"_id": 0})
            if doc:
                await ws_manager.broadcast({"type": "TICKER_UPDATED", "ticker": doc})
            logger.warning(f"AUTO-STOP: {symbol} — {reason}")
            # Telegram alert
            try:
                await telegram_service._broadcast_alert(
                    f"AUTO-STOP {symbol}\n{reason}\nTrading disabled. Manual re-enable required."
                )
            except Exception:
                pass

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
            await self._broadcast_alert("Sentinel Pulse is now ONLINE and connected to Telegram.")
        except Exception as e:
            logger.error(f"Telegram start error: {e}")
            self.running = False

    async def stop(self):
        """Gracefully shut down the bot and notify chat IDs."""
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
                await bot.send_message(chat_id=int(cid), text=f"[Sentinel Pulse] {text}")
            except Exception as e:
                logger.warning(f"Telegram send to {cid} failed: {e}")

    async def send_trade_alert(self, trade: dict):
        """Push a rich trade notification to all chats."""
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
            trail_str = f"\nTrail High: ${trade.get('trail_high', 0):.2f} | Trigger: ${trade.get('trail_trigger', 0):.2f} | {trade.get('trail_mode', '')} {trade.get('trail_value', 0)}"

        msg = (
            f"TRADE  {order_type} {side} {sym}\n"
            f"Fill: ${price:.2f}  Qty: {qty:.4f}\n"
            f"Target: ${target_price:.2f} | Mode: {rule_mode}\n"
            f"Value: ${total_value:.2f} | Power: ${buy_power:.2f}"
            f"{entry_str}{pnl_str}{trail_str}\n"
            f"{reason}"
        )
        await self._broadcast_alert(msg)

    # ---- command handlers ----

    def _register_handlers(self):
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
        app.add_handler(CommandHandler("help", self._cmd_help))

    def _authorised(self, update: Update) -> bool:
        cid = str(update.effective_chat.id)
        if not self.chat_ids:
            return True
        return cid in self.chat_ids

    async def _cmd_stop(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Toggle bot: if running → stop, if stopped → start."""
        if not self._authorised(update):
            return await update.message.reply_text("Unauthorised.")
        if engine.running:
            engine.running = False
            engine.paused = False
            await engine.save_state()
            await ws_manager.broadcast({"type": "BOT_STATUS", "running": False, "paused": False})
            await update.message.reply_text("Bot STOPPED.")
            await self._broadcast_alert("Bot has been STOPPED via Telegram /stop command.")
        else:
            engine.running = True
            engine.paused = False
            await engine.save_state()
            await ws_manager.broadcast({"type": "BOT_STATUS", "running": True, "paused": False})
            await update.message.reply_text("Bot STARTED.")
            await self._broadcast_alert("Bot has been STARTED via Telegram /stop command.")

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
    logger.info("Sentinel Pulse Engine started")
    yield
    # Shutdown: send offline alert then close
    try:
        await telegram_service.stop()
    except Exception:
        pass
    mongo_client.close()


# --- FASTAPI APP ---
app = FastAPI(title="Sentinel Pulse", lifespan=lifespan)
api = APIRouter(prefix="/api")

# OpenTelemetry
from telemetry import setup_telemetry, get_tracer, get_stored_spans
setup_telemetry(app)
_tracer = get_tracer()

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

@api.get("/traces")
async def get_traces(limit: int = Query(100, ge=1, le=500), name: str = Query("", description="Filter by span name")):
    """Retrieve recent OpenTelemetry trace spans stored in memory."""
    spans = get_stored_spans(limit=limit, name_filter=name)
    return {"count": len(spans), "spans": spans}

@api.get("/beta/status")
async def beta_status():
    """Check if a beta tester is registered."""
    reg = await db.beta_registrations.find_one({}, {"_id": 0})
    return {"registered": reg is not None, "registration": reg}

@api.post("/beta/register")
async def beta_register(body: BetaRegistration):
    """Register as a beta tester. Must accept agreement."""
    if not body.agreement_accepted:
        raise HTTPException(400, "You must accept the Beta Tester Agreement to proceed.")
    if not body.first_name or not body.last_name or not body.email:
        raise HTTPException(400, "Name and email are required.")
    if len(body.ssn_last4) != 4 or not body.ssn_last4.isdigit():
        raise HTTPException(400, "Last 4 of SSN must be exactly 4 digits.")
    doc = body.model_dump()
    doc["ip_address"] = ""  # Placeholder — would capture in production
    await db.beta_registrations.delete_many({})  # Only one registration per instance
    await db.beta_registrations.insert_one(doc)
    doc.pop("_id", None)
    logger.info(f"BETA REGISTRATION: {body.first_name} {body.last_name} ({body.email})")
    # Send registration details via email (async in background)
    from email_service import send_registration_email
    try:
        send_registration_email(doc)
    except Exception as e:
        logger.warning(f"Registration email failed (non-blocking): {e}")
    return {"status": "registered", "registration": doc}


# --- FEEDBACK / BUG REPORT ---
@api.post("/feedback")
async def submit_feedback(body: FeedbackReport):
    """Submit a bug report, suggestion, complaint or error log."""
    if not body.subject.strip() or not body.description.strip():
        raise HTTPException(400, "Subject and description are required.")
    if body.type not in ("bug", "error", "suggestion", "complaint"):
        raise HTTPException(400, "Type must be one of: bug, error, suggestion, complaint.")

    # Look up registered user
    reg = await db.beta_registrations.find_one({}, {"_id": 0})
    user = reg or {"first_name": "Unregistered", "last_name": "", "email": "unknown"}

    from email_service import send_feedback_email, APP_VERSION, _check_rate_limit
    doc = {
        "type": body.type,
        "subject": body.subject,
        "description": body.description,
        "error_log": body.error_log,
        "user_name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip(),
        "user_email": user.get("email", "unknown"),
        "app_version": APP_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await db.feedback.insert_one(doc)
    doc.pop("_id", None)

    email_sent = False
    try:
        email_sent = send_feedback_email(
            {"type": body.type, "subject": body.subject, "description": body.description, "error_log": body.error_log},
            user,
        )
    except Exception as e:
        logger.warning(f"Feedback email failed (non-blocking): {e}")

    rate_limited = not _check_rate_limit()
    return {"status": "submitted", "email_sent": email_sent, "rate_limited": rate_limited, "feedback": doc}


from starlette.responses import PlainTextResponse

@api.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics():
    """Expose key application metrics in Prometheus text format."""
    lines = []
    lines.append("# HELP sentinel_pulse_up Whether the bot engine is running (1) or stopped (0).")
    lines.append("# TYPE sentinel_pulse_up gauge")
    lines.append(f"sentinel_pulse_up {1 if engine.running else 0}")

    lines.append("# HELP sentinel_pulse_paused Whether the bot engine is paused (1) or active (0).")
    lines.append("# TYPE sentinel_pulse_paused gauge")
    lines.append(f"sentinel_pulse_paused {1 if engine.paused else 0}")

    lines.append("# HELP sentinel_pulse_market_open Whether the market is currently open (1) or closed (0).")
    lines.append("# TYPE sentinel_pulse_market_open gauge")
    lines.append(f"sentinel_pulse_market_open {1 if engine.is_market_open() else 0}")

    lines.append("# HELP sentinel_pulse_ws_clients Number of active WebSocket connections.")
    lines.append("# TYPE sentinel_pulse_ws_clients gauge")
    lines.append(f"sentinel_pulse_ws_clients {len(ws_manager.active)}")

    # Account balance metrics
    balance_doc = await db.settings.find_one({"key": "account_balance"}, {"_id": 0})
    account_balance = round(balance_doc.get("value", 0), 2) if balance_doc else 0
    tickers = await db.tickers.find({}, {"_id": 0}).to_list(100)
    allocated = round(sum(t.get("base_power", 0) for t in tickers), 2)
    available = round(account_balance - allocated, 2)

    lines.append("# HELP sentinel_pulse_account_balance_usd Total account balance in USD.")
    lines.append("# TYPE sentinel_pulse_account_balance_usd gauge")
    lines.append(f"sentinel_pulse_account_balance_usd {account_balance}")

    lines.append("# HELP sentinel_pulse_allocated_usd Total allocated capital in USD.")
    lines.append("# TYPE sentinel_pulse_allocated_usd gauge")
    lines.append(f"sentinel_pulse_allocated_usd {allocated}")

    lines.append("# HELP sentinel_pulse_available_usd Available (unallocated) capital in USD.")
    lines.append("# TYPE sentinel_pulse_available_usd gauge")
    lines.append(f"sentinel_pulse_available_usd {available}")

    # Ticker count
    lines.append("# HELP sentinel_pulse_tickers_total Number of configured tickers.")
    lines.append("# TYPE sentinel_pulse_tickers_total gauge")
    lines.append(f"sentinel_pulse_tickers_total {len(tickers)}")

    tickers_enabled = sum(1 for t in tickers if t.get("enabled", True))
    lines.append("# HELP sentinel_pulse_tickers_enabled Number of enabled tickers.")
    lines.append("# TYPE sentinel_pulse_tickers_enabled gauge")
    lines.append(f"sentinel_pulse_tickers_enabled {tickers_enabled}")

    # Per-ticker buy power
    for t in tickers:
        sym = t.get("symbol", "unknown")
        bp = t.get("base_power", 0)
        lines.append(f'sentinel_pulse_ticker_buy_power_usd{{symbol="{sym}"}} {bp}')

    # Trade counts and P&L
    total_trades = await db.trades.count_documents({})
    lines.append("# HELP sentinel_pulse_trades_total Total number of trades executed.")
    lines.append("# TYPE sentinel_pulse_trades_total counter")
    lines.append(f"sentinel_pulse_trades_total {total_trades}")

    buy_trades = await db.trades.count_documents({"side": "BUY"})
    sell_trades = await db.trades.count_documents({"side": {"$in": ["SELL", "STOP", "TRAILING_STOP"]}})
    lines.append("# HELP sentinel_pulse_trades_by_side_total Trade count by side.")
    lines.append("# TYPE sentinel_pulse_trades_by_side_total counter")
    lines.append(f'sentinel_pulse_trades_by_side_total{{side="BUY"}} {buy_trades}')
    lines.append(f'sentinel_pulse_trades_by_side_total{{side="SELL"}} {sell_trades}')

    # Per-ticker P&L
    profits_cursor = db.profits.find({}, {"_id": 0})
    profits_list = await profits_cursor.to_list(100)
    total_pnl = 0.0
    lines.append("# HELP sentinel_pulse_ticker_pnl_usd Realized P&L per ticker in USD.")
    lines.append("# TYPE sentinel_pulse_ticker_pnl_usd gauge")
    for p in profits_list:
        sym = p.get("symbol", "unknown")
        pnl = p.get("total_pnl", 0)
        total_pnl += pnl
        lines.append(f'sentinel_pulse_ticker_pnl_usd{{symbol="{sym}"}} {round(pnl, 2)}')

    lines.append("# HELP sentinel_pulse_total_pnl_usd Total realized P&L across all tickers in USD.")
    lines.append("# TYPE sentinel_pulse_total_pnl_usd gauge")
    lines.append(f"sentinel_pulse_total_pnl_usd {round(total_pnl, 2)}")

    # Cash reserve
    cash_doc = await db.settings.find_one({"key": "cash_reserve"}, {"_id": 0})
    cash_reserve = round(cash_doc.get("value", 0), 2) if cash_doc else 0
    lines.append("# HELP sentinel_pulse_cash_reserve_usd Cash reserve from take profit actions.")
    lines.append("# TYPE sentinel_pulse_cash_reserve_usd gauge")
    lines.append(f"sentinel_pulse_cash_reserve_usd {cash_reserve}")

    # Positions
    positions = await db.positions.find({}, {"_id": 0}).to_list(100)
    lines.append("# HELP sentinel_pulse_open_positions Number of open positions.")
    lines.append("# TYPE sentinel_pulse_open_positions gauge")
    lines.append(f"sentinel_pulse_open_positions {len(positions)}")

    for pos in positions:
        sym = pos.get("symbol", "unknown")
        qty = pos.get("quantity", 0)
        upnl = pos.get("unrealized_pnl", 0)
        lines.append(f'sentinel_pulse_position_quantity{{symbol="{sym}"}} {qty}')
        lines.append(f'sentinel_pulse_position_unrealized_pnl_usd{{symbol="{sym}"}} {round(upnl, 2)}')

    return "\n".join(lines) + "\n"


# --- BROKER ENDPOINTS ---
from brokers import BROKER_REGISTRY, get_broker_info, get_broker_adapter

@api.get("/brokers")
async def list_brokers():
    """List all supported brokers with their metadata and risk warnings."""
    result = []
    for broker_id, info in BROKER_REGISTRY.items():
        entry = {
            "id": info.id,
            "name": info.name,
            "description": info.description,
            "supported": info.supported,
            "auth_fields": info.auth_fields,
            "docs_url": info.docs_url,
            "risk_warning": None,
        }
        if info.risk_warning:
            entry["risk_warning"] = {
                "level": info.risk_warning.level.value,
                "message": info.risk_warning.message,
            }
        result.append(entry)
    return result

@api.get("/brokers/{broker_id}")
async def get_broker(broker_id: str):
    """Get details for a specific broker."""
    info = get_broker_info(broker_id)
    if not info:
        raise HTTPException(404, f"Broker '{broker_id}' not found.")
    entry = {
        "id": info.id,
        "name": info.name,
        "description": info.description,
        "supported": info.supported,
        "auth_fields": info.auth_fields,
        "docs_url": info.docs_url,
        "risk_warning": None,
    }
    if info.risk_warning:
        entry["risk_warning"] = {
            "level": info.risk_warning.level.value,
            "message": info.risk_warning.message,
        }
    return entry


class BrokerTestRequest(BaseModel):
    credentials: Dict[str, str]

@api.post("/brokers/{broker_id}/test")
async def test_broker_connection(broker_id: str, body: BrokerTestRequest):
    """Full credential validation dry-run for a broker connection."""
    info = get_broker_info(broker_id)
    if not info:
        raise HTTPException(404, f"Broker '{broker_id}' not found.")

    results = {
        "broker_id": broker_id,
        "broker_name": info.name,
        "checks": [],
        "overall": "fail",
    }

    # Check 1: Required fields present
    missing = [f for f in info.auth_fields if not body.credentials.get(f, "").strip()]
    if missing:
        results["checks"].append({
            "name": "required_fields",
            "status": "fail",
            "message": f"Missing required credentials: {', '.join(missing)}",
        })
        return results
    results["checks"].append({
        "name": "required_fields",
        "status": "pass",
        "message": "All required credential fields provided.",
    })

    # Check 2: Field format validation
    format_issues = []
    creds = body.credentials
    if broker_id == "ibkr":
        port = creds.get("port", "")
        if port and not port.isdigit():
            format_issues.append("'port' must be a number (e.g., 7497 for paper, 7496 for live)")
        client_id = creds.get("client_id", "")
        if client_id and not client_id.isdigit():
            format_issues.append("'client_id' must be a number")
    if broker_id == "robinhood":
        mfa = creds.get("mfa_code", "")
        if mfa and (len(mfa) != 6 or not mfa.isdigit()):
            format_issues.append("'mfa_code' should be a 6-digit code")
    if broker_id == "webull":
        pin = creds.get("trading_pin", "")
        if pin and (len(pin) < 4 or not pin.isdigit()):
            format_issues.append("'trading_pin' should be a numeric PIN (4+ digits)")
    if broker_id == "schwab":
        for field in ["app_key", "app_secret"]:
            val = creds.get(field, "")
            if val and len(val) < 8:
                format_issues.append(f"'{field}' appears too short — verify from Schwab Developer Portal")
    if broker_id == "alpaca":
        for field in ["api_key", "api_secret"]:
            val = creds.get(field, "")
            if val and len(val) < 10:
                format_issues.append(f"'{field}' appears too short — get keys from https://app.alpaca.markets")
        paper = creds.get("paper", "")
        if paper and paper.lower() not in ("true", "false", "1", "0", "yes", "no"):
            format_issues.append("'paper' must be true/false (true for paper trading, false for live)")


    if format_issues:
        results["checks"].append({
            "name": "format_validation",
            "status": "fail",
            "message": "; ".join(format_issues),
        })
        return results
    results["checks"].append({
        "name": "format_validation",
        "status": "pass",
        "message": "Credential formats look valid.",
    })

    # Check 3: Adapter availability
    adapter = get_broker_adapter(broker_id, body.credentials)
    if not adapter:
        results["checks"].append({
            "name": "adapter_available",
            "status": "warn",
            "message": f"Live adapter for {info.name} is not yet implemented. Credential format validated but connection could not be tested end-to-end.",
        })
        results["overall"] = "partial"
        return results

    # Check 4: Live connection test (when adapter is available)
    try:
        connected = await adapter.connect(body.credentials)
        if connected:
            results["checks"].append({
                "name": "live_connection",
                "status": "pass",
                "message": f"Successfully authenticated with {info.name}.",
            })
            # Check 5: Account access
            try:
                account = await adapter.get_account()
                results["checks"].append({
                    "name": "account_access",
                    "status": "pass",
                    "message": f"Account accessible. Balance: ${account.balance:.2f}, Buying Power: ${account.buying_power:.2f}",
                })
            except Exception as e:
                results["checks"].append({
                    "name": "account_access",
                    "status": "fail",
                    "message": f"Authenticated but could not access account data: {e}",
                })
            await adapter.disconnect()
            results["overall"] = "pass"
        else:
            results["checks"].append({
                "name": "live_connection",
                "status": "fail",
                "message": "Authentication failed — check your credentials.",
            })
    except Exception as e:
        results["checks"].append({
            "name": "live_connection",
            "status": "fail",
            "message": f"Connection error: {e}",
        })

    return results


@api.get("/tickers")
async def get_tickers():
    docs = await db.tickers.find({}, {"_id": 0}).sort("sort_order", 1).to_list(100)
    return docs

async def _broadcast_account_update():
    """Recompute and broadcast account balance, allocated, available."""
    balance_doc = await db.settings.find_one({"key": "account_balance"}, {"_id": 0})
    account_balance = round(balance_doc.get("value", 0), 2) if balance_doc else 0
    tickers = await db.tickers.find({}, {"_id": 0, "base_power": 1}).to_list(100)
    allocated = round(sum(t.get("base_power", 0) for t in tickers), 2)
    await ws_manager.broadcast({
        "type": "ACCOUNT_UPDATE",
        "account_balance": account_balance,
        "allocated": allocated,
        "available": round(account_balance - allocated, 2),
    })

@api.post("/tickers")
async def add_ticker(body: TickerCreate):
    sym = body.symbol.upper().strip()
    existing = await db.tickers.find_one({"symbol": sym})
    if existing:
        raise HTTPException(400, f"{sym} already exists")
    max_order = await db.tickers.find_one(sort=[("sort_order", -1)], projection={"sort_order": 1})
    next_order = (max_order.get("sort_order", 0) + 1) if max_order else 0
    t = TickerConfig(symbol=sym, base_power=body.base_power, sort_order=next_order)
    doc = t.model_dump()
    await db.tickers.insert_one(doc)
    doc.pop("_id", None)
    await ws_manager.broadcast({"type": "TICKER_ADDED", "ticker": doc})
    await _broadcast_account_update()
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
    if "base_power" in updates:
        await _broadcast_account_update()
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
    await _broadcast_account_update()
    return {"deleted": sym}

@api.post("/tickers/reorder")
async def reorder_tickers(body: dict):
    """Update sort_order for all tickers. Expects: {"order": ["SPY", "NVDA", "TSLA"]}"""
    order = body.get("order", [])
    if not order:
        raise HTTPException(400, "No order provided")
    for i, sym in enumerate(order):
        await db.tickers.update_one({"symbol": sym.upper()}, {"$set": {"sort_order": i}})
    docs = await db.tickers.find({}, {"_id": 0}).to_list(100)
    await ws_manager.broadcast({"type": "TICKERS_REORDERED", "tickers": docs})
    return {"status": "ok"}

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

@api.get("/loss-logs")
async def list_loss_logs():
    """List all loss log dates and file counts."""
    log_dir = ROOT_DIR / "trade_logs" / "losses"
    if not log_dir.exists():
        return {"dates": []}
    dates = []
    for d in sorted(log_dir.iterdir(), reverse=True):
        if d.is_dir():
            files = [f.name for f in d.iterdir() if f.suffix == ".txt"]
            dates.append({"date": d.name, "count": len(files), "files": sorted(files, reverse=True)})
    return {"dates": dates}

@api.get("/loss-logs/{date}/{filename}")
async def get_loss_log(date: str, filename: str):
    """Return the contents of a specific loss log file."""
    from fastapi.responses import PlainTextResponse
    filepath = ROOT_DIR / "trade_logs" / "losses" / date / filename
    if not filepath.exists() or not filepath.suffix == ".txt":
        raise HTTPException(404, "Log file not found")
    return PlainTextResponse(filepath.read_text())

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
    # If compound was active, subtract the taken profit from buy power
    ticker_doc = await db.tickers.find_one({"symbol": sym}, {"_id": 0})
    if ticker_doc and ticker_doc.get("compound_profits", True):
        new_bp = max(1.0, round(ticker_doc.get("base_power", 100) - amount, 2))
        await db.tickers.update_one({"symbol": sym}, {"$set": {"base_power": new_bp}})
        updated_ticker = await db.tickers.find_one({"symbol": sym}, {"_id": 0})
        if updated_ticker:
            await ws_manager.broadcast({"type": "TICKER_UPDATED", "ticker": updated_ticker})
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
    if body.account_balance is not None:
        if body.account_balance < 0 or body.account_balance > 100_000_000:
            raise HTTPException(400, "Account balance must be between $0 and $100,000,000.")
        await db.settings.update_one(
            {"key": "account_balance"}, {"$set": {"value": body.account_balance}}, upsert=True
        )
        # Broadcast the updated balance
        tickers = await db.tickers.find({}, {"_id": 0, "base_power": 1}).to_list(100)
        allocated = round(sum(t.get("base_power", 0) for t in tickers), 2)
        await ws_manager.broadcast({
            "type": "ACCOUNT_UPDATE",
            "account_balance": round(body.account_balance, 2),
            "allocated": allocated,
            "available": round(body.account_balance - allocated, 2),
        })
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
    balance_doc = await db.settings.find_one({"key": "account_balance"}, {"_id": 0})
    tickers = await db.tickers.find({}, {"_id": 0, "base_power": 1}).to_list(100)
    allocated = sum(t.get("base_power", 0) for t in tickers)
    account_balance = balance_doc.get("value", 0) if balance_doc else 0
    cash_reserve = round(cash_doc.get("value", 0), 2) if cash_doc else 0
    return {
        "simulate_24_7": engine.simulate_24_7,
        "telegram": tg.get("value", {}) if tg else {"bot_token": "", "chat_ids": []},
        "telegram_connected": telegram_service.running,
        "increment_step": inc_doc.get("value", 0.5) if inc_doc else 0.5,
        "decrement_step": dec_doc.get("value", 0.5) if dec_doc else 0.5,
        "cash_reserve": cash_reserve,
        "account_balance": round(account_balance, 2),
        "allocated": round(allocated, 2),
        "available": round(account_balance - allocated, 2),
    }

@api.post("/settings/telegram/test")
async def test_telegram():
    """Send a test alert to all registered chat IDs."""
    if not telegram_service.running:
        raise HTTPException(400, "Telegram bot is not connected. Save a valid token first.")
    await telegram_service._broadcast_alert("Test alert from Sentinel Pulse! Connection verified.")
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
        balance_doc = await db.settings.find_one({"key": "account_balance"}, {"_id": 0})
        account_balance = round(balance_doc.get("value", 0), 2) if balance_doc else 0
        allocated = round(sum(t.get("base_power", 0) for t in tickers), 2)

        await websocket.send_json({
            "type": "INITIAL_STATE",
            "tickers": tickers,
            "prices": prices,
            "profits": profits,
            "cash_reserve": cash_reserve,
            "account_balance": account_balance,
            "allocated": allocated,
            "available": round(account_balance - allocated, 2),
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
                # Validate numeric fields
                NUMERIC_BOUNDS = {
                    "base_power": (1, 10_000_000),
                    "buy_offset": (-99999, 99999),
                    "sell_offset": (-99999, 99999),
                    "stop_offset": (-99999, 99999),
                    "trailing_percent": (0.01, 50),
                    "avg_days": (1, 365),
                    "max_daily_loss": (0, 999999),
                    "max_consecutive_losses": (0, 100),
                    "rebracket_threshold": (0.01, 99999),
                    "rebracket_spread": (0.01, 99999),
                    "rebracket_cooldown": (0, 3600),
                    "rebracket_lookback": (2, 100),
                    "rebracket_buffer": (0, 99999),
                }
                valid = True
                for field, (lo, hi) in NUMERIC_BOUNDS.items():
                    if field in updates:
                        try:
                            val = float(updates[field])
                            updates[field] = max(lo, min(hi, val))
                        except (ValueError, TypeError):
                            valid = False
                            break
                if updates and valid:
                    await db.tickers.update_one({"symbol": sym}, {"$set": updates})
                    doc = await db.tickers.find_one({"symbol": sym}, {"_id": 0})
                    if doc:
                        await ws_manager.broadcast({"type": "TICKER_UPDATED", "ticker": doc})

            elif action == "START_BOT":
                engine.running = True
                engine.paused = False
                await engine.save_state()
                await ws_manager.broadcast({"type": "BOT_STATUS", "running": True, "paused": False})

            elif action == "STOP_BOT":
                engine.running = False
                engine.paused = False
                await engine.save_state()
                await ws_manager.broadcast({"type": "BOT_STATUS", "running": False, "paused": False})

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
                    # If compound was active, subtract taken profit from buy power
                    ticker_doc = await db.tickers.find_one({"symbol": sym}, {"_id": 0})
                    if ticker_doc and ticker_doc.get("compound_profits", True):
                        new_bp = max(1.0, round(ticker_doc.get("base_power", 100) - amount, 2))
                        await db.tickers.update_one({"symbol": sym}, {"$set": {"base_power": new_bp}})
                        updated_ticker = await db.tickers.find_one({"symbol": sym}, {"_id": 0})
                        if updated_ticker:
                            await ws_manager.broadcast({"type": "TICKER_UPDATED", "ticker": updated_ticker})
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

# Serve built frontend in desktop/packaged mode
# Must be AFTER include_router so /api/* routes have priority
_static_dir = Path(__file__).parent / "static"
if _static_dir.is_dir():
    from starlette.staticfiles import StaticFiles
    from starlette.responses import FileResponse

    @app.get("/")
    async def serve_index():
        return FileResponse(_static_dir / "index.html")

    app.mount("/assets", StaticFiles(directory=str(_static_dir / "assets")), name="static-assets")

    @app.get("/{path:path}")
    async def serve_spa(path: str):
        file = _static_dir / path
        if file.is_file():
            return FileResponse(file)
        return FileResponse(_static_dir / "index.html")
