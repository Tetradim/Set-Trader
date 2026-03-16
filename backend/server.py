import asyncio
import json
import os
import logging
import random
import uuid
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Query
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ConfigDict

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
    sell_offset: float = 3.0
    sell_percent: bool = True
    stop_offset: float = -6.0
    stop_percent: bool = True
    trailing_enabled: bool = False
    trailing_percent: float = 2.0
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
    sell_offset: Optional[float] = None
    sell_percent: Optional[bool] = None
    stop_offset: Optional[float] = None
    stop_percent: Optional[bool] = None
    trailing_enabled: Optional[bool] = None
    trailing_percent: Optional[float] = None
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
    def __init__(self):
        self.running = False
        self.paused = False
        self.simulate_24_7 = False
        self._prices: Dict[str, float] = {}
        self._positions: Dict[str, dict] = {}
        self._trailing_highs: Dict[str, float] = {}

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

        price = await price_service.get_price(sym)
        self._prices[sym] = price
        avg = await price_service.get_avg_price(sym, ticker_doc.get("avg_days", 30))

        buy_off = ticker_doc.get("buy_offset", -3.0)
        is_buy_pct = ticker_doc.get("buy_percent", True)
        sell_off = ticker_doc.get("sell_offset", 3.0)
        is_sell_pct = ticker_doc.get("sell_percent", True)
        stop_off = ticker_doc.get("stop_offset", -6.0)
        is_stop_pct = ticker_doc.get("stop_percent", True)
        trailing = ticker_doc.get("trailing_enabled", False)
        trail_pct = ticker_doc.get("trailing_percent", 2.0)
        base_power = ticker_doc.get("base_power", 100.0)

        buy_target = round(avg * (1 + buy_off / 100) if is_buy_pct else avg + buy_off, 2)
        sell_target = round(avg * (1 + sell_off / 100) if is_sell_pct else avg + sell_off, 2)
        stop_target = round(avg * (1 + stop_off / 100) if is_stop_pct else avg + stop_off, 2)

        pos = self._positions.get(sym, {"qty": 0, "avg_entry": 0})

        # BUY logic
        if pos["qty"] == 0 and price <= buy_target:
            qty = round(base_power / price, 4)
            if qty > 0:
                self._positions[sym] = {"qty": qty, "avg_entry": price}
                trade = TradeRecord(
                    symbol=sym, side="BUY", price=price, quantity=qty,
                    reason=f"Price ${price} <= buy target ${buy_target}"
                )
                await self._record_trade(trade)

        # SELL / STOP / TRAILING logic
        elif pos["qty"] > 0:
            entry = pos["avg_entry"]

            if trailing:
                high = self._trailing_highs.get(sym, price)
                if price > high:
                    self._trailing_highs[sym] = price
                    high = price
                trail_stop = round(high * (1 - trail_pct / 100), 2)
                if price <= trail_stop:
                    pnl = round((price - entry) * pos["qty"], 2)
                    trade = TradeRecord(
                        symbol=sym, side="TRAILING_STOP", price=price,
                        quantity=pos["qty"], reason=f"Trailing stop hit ${trail_stop} (high ${high})", pnl=pnl
                    )
                    await self._record_trade(trade)
                    self._positions[sym] = {"qty": 0, "avg_entry": 0}
                    self._trailing_highs.pop(sym, None)
                    await self._update_profit(sym, pnl)
                    return

            if price >= sell_target:
                pnl = round((price - entry) * pos["qty"], 2)
                trade = TradeRecord(
                    symbol=sym, side="SELL", price=price, quantity=pos["qty"],
                    reason=f"Price ${price} >= sell target ${sell_target}", pnl=pnl
                )
                await self._record_trade(trade)
                self._positions[sym] = {"qty": 0, "avg_entry": 0}
                self._trailing_highs.pop(sym, None)
                await self._update_profit(sym, pnl)

            elif price <= stop_target:
                pnl = round((price - entry) * pos["qty"], 2)
                trade = TradeRecord(
                    symbol=sym, side="STOP", price=price, quantity=pos["qty"],
                    reason=f"Stop-loss hit ${price} <= ${stop_target}", pnl=pnl
                )
                await self._record_trade(trade)
                self._positions[sym] = {"qty": 0, "avg_entry": 0}
                self._trailing_highs.pop(sym, None)
                await self._update_profit(sym, pnl)

    async def _record_trade(self, trade: TradeRecord):
        doc = trade.model_dump()
        await db.trades.insert_one(doc)
        logger.info(f"TRADE: {trade.side} {trade.symbol} @ ${trade.price} x{trade.quantity}")
        await ws_manager.broadcast({
            "type": "TRADE",
            "trade": {k: v for k, v in doc.items() if k != "_id"}
        })

    async def _update_profit(self, symbol: str, pnl: float):
        await db.profits.update_one(
            {"symbol": symbol},
            {"$inc": {"total_pnl": pnl, "trade_count": 1},
             "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True
        )

engine = TradingEngine()


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
                        positions[sym] = {
                            "quantity": pos["qty"],
                            "avg_entry": pos["avg_entry"],
                            "current_price": cp,
                            "unrealized_pnl": round((cp - pos["avg_entry"]) * pos["qty"], 2)
                        }

                profits_cursor = db.profits.find({}, {"_id": 0})
                profits_list = await profits_cursor.to_list(100)
                profits = {p["symbol"]: p.get("total_pnl", 0) for p in profits_list}

                await ws_manager.broadcast({
                    "type": "PRICE_UPDATE",
                    "prices": prices,
                    "positions": positions,
                    "profits": profits,
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
                    await engine.evaluate_ticker(t)
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
    asyncio.create_task(price_broadcast_loop())
    asyncio.create_task(trading_loop())
    logger.info("BracketBot Engine started")
    yield
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
    strategy = PRESET_STRATEGIES.get(preset)
    if not strategy:
        raise HTTPException(400, f"Unknown preset: {preset}")
    updates = strategy.model_dump()
    updates.pop("name")
    updates["strategy"] = preset
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
    await ws_manager.broadcast({"type": "BOT_STATUS", "running": True, "paused": engine.paused})
    return {"running": True}

@api.post("/bot/stop")
async def stop_bot():
    engine.running = False
    await ws_manager.broadcast({"type": "BOT_STATUS", "running": False, "paused": engine.paused})
    return {"running": False}

@api.post("/bot/pause")
async def pause_bot():
    engine.paused = not engine.paused
    await ws_manager.broadcast({"type": "BOT_STATUS", "running": engine.running, "paused": engine.paused})
    return {"paused": engine.paused}

@api.post("/settings")
async def update_settings(body: SettingsUpdate):
    if body.simulate_24_7 is not None:
        engine.simulate_24_7 = body.simulate_24_7
    if body.telegram:
        doc = body.telegram.model_dump()
        await db.settings.update_one(
            {"key": "telegram"}, {"$set": {"value": doc}}, upsert=True
        )
    return {"ok": True}

@api.get("/settings")
async def get_settings():
    tg = await db.settings.find_one({"key": "telegram"}, {"_id": 0})
    return {
        "simulate_24_7": engine.simulate_24_7,
        "telegram": tg.get("value", {}) if tg else {"bot_token": "", "chat_ids": []},
    }

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

        await websocket.send_json({
            "type": "INITIAL_STATE",
            "tickers": tickers,
            "prices": prices,
            "profits": profits,
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
                await ws_manager.broadcast({"type": "BOT_STATUS", "running": engine.running, "paused": engine.paused})

            elif action == "START_BOT":
                engine.running = True
                await ws_manager.broadcast({"type": "BOT_STATUS", "running": True, "paused": engine.paused})

            elif action == "STOP_BOT":
                engine.running = False
                await ws_manager.broadcast({"type": "BOT_STATUS", "running": False, "paused": engine.paused})

            elif action == "APPLY_STRATEGY":
                sym = msg.get("symbol", "").upper()
                preset = msg.get("preset", "")
                strategy = PRESET_STRATEGIES.get(preset)
                if strategy:
                    updates = strategy.model_dump()
                    updates.pop("name")
                    updates["strategy"] = preset
                    await db.tickers.update_one({"symbol": sym}, {"$set": updates})
                    doc = await db.tickers.find_one({"symbol": sym}, {"_id": 0})
                    if doc:
                        await ws_manager.broadcast({"type": "TICKER_UPDATED", "ticker": doc})

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)


app.include_router(api)
