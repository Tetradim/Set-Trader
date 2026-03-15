import asyncio
import json
import os
import threading
import logging
import random
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager
from dotenv import load_dotenv

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Load environment variables
load_dotenv()

# LOGGING & LOCKS
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("BracketBot")
file_lock = threading.Lock()

# ALPACA IMPORTS
try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.enums import OrderSide, OrderClass, TimeInForce
    from alpaca.trading.requests import LimitOrderRequest, StopLossRequest, TakeProfitRequest
    from alpaca.data import StockHistoricalDataClient, StockBarsRequest, StockLatestQuoteRequest
    from alpaca.data.timeframe import TimeFrame
    ALPACA_AVAILABLE = True
except ImportError:
    logger.error("Alpaca SDK not found. Running in Mock Mode only.")
    ALPACA_AVAILABLE = False

STATE_FILE = "bot_state.json"

# --- WEBSOCKET MANAGER ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                continue

manager = ConnectionManager()

# --- SCHEMAS ---
class TickerConfig(BaseModel):
    symbol: str
    base_power: float = 100.0
    avg_days: int = 30
    buy_offset: float = -3.0
    buy_percent: bool = True
    sell_offset: float = 3.0
    sell_percent: bool = True
    stop_offset: float = -6.0
    stop_percent: bool = True
    enabled: bool = True

# --- STATE MANAGEMENT ---
class AppState:
    def __init__(self):
        self.tickers = {}
        self.profits = {}
        self.tracked_orders = {}
        self.paused = False
        self.load()

    def load(self):
        if os.path.exists(STATE_FILE):
            with file_lock:
                try:
                    with open(STATE_FILE, "r") as f:
                        d = json.load(f)
                        self.tickers = {k: TickerConfig(**v) for k, v in d.get("tickers", {}).items()}
                        self.profits = d.get("profits", {})
                        self.tracked_orders = d.get("tracked_orders", {})
                        self.paused = d.get("paused", False)
                except Exception as e:
                    logger.error(f"Load Error: {e}")

    def save(self):
        with file_lock:
            try:
                with open(STATE_FILE, "w") as f:
                    data = {
                        "tickers": {k: v.model_dump() for k, v in self.tickers.items()},
                        "profits": self.profits,
                        "tracked_orders": self.tracked_orders,
                        "paused": self.paused
                    }
                    json.dump(data, f, indent=2)
            except Exception as e:
                logger.error(f"Save Error: {e}")

state = AppState()

# --- ALPACA SERVICE ---
class AlpacaService:
    def __init__(self):
        self.trading_client = None
        self.data_client = None
        self.connected = False
        self._init()

    def _init(self):
        key = os.getenv("ALPACA_KEY")
        secret = os.getenv("ALPACA_SECRET")
        if key and secret and ALPACA_AVAILABLE:
            try:
                self.trading_client = TradingClient(key, secret, paper=True)
                self.data_client = StockHistoricalDataClient(key, secret)
                self.connected = True
                logger.info("Alpaca Client Connected Successfully.")
            except Exception as e:
                logger.error(f"Alpaca Connection Failed: {e}")

    def get_avg_price(self, symbol, days):
        if not self.connected: return 0.0
        try:
            start_date = datetime.now(timezone.utc) - timedelta(days=days + 5)
            req = StockBarsRequest(
                symbol_or_symbols=symbol, 
                timeframe=TimeFrame.Day, 
                start=start_date
            )
            df = self.data_client.get_stock_bars(req).df
            return float(df["close"].tail(days).mean())
        except Exception:
            return 0.0

alpaca = AlpacaService()

# --- STRATEGY ENGINE ---
class StrategyEngine:
    def place_bracket(self, sym):
        if not alpaca.connected or state.paused: return
        cfg = state.tickers.get(sym)
        if not cfg or not cfg.enabled: return
        
        avg = alpaca.get_avg_price(sym, cfg.avg_days)
        if avg <= 0: return # Skip if no data
        
        buy = round(avg * (1 + cfg.buy_offset/100) if cfg.buy_percent else avg + cfg.buy_offset, 2)
        sell = round(avg * (1 + cfg.sell_offset/100) if cfg.sell_percent else avg + cfg.sell_offset, 2)
        stop = round(buy * (1 + cfg.stop_offset/100) if cfg.stop_percent else buy + cfg.stop_offset, 2)
        
        qty = int(cfg.base_power // buy)
        if qty < 1: return

        try:
            order = alpaca.trading_client.submit_order(
                LimitOrderRequest(
                    symbol=sym, qty=qty, side=OrderSide.BUY, time_in_force=TimeInForce.GTC,
                    limit_price=buy, order_class=OrderClass.BRACKET,
                    take_profit=TakeProfitRequest(limit_price=sell), 
                    stop_loss=StopLossRequest(stop_price=stop)
                )
            )
            
            # Update local tracking
            state.tracked_orders[str(order.id)] = {"symbol": sym, "buy": buy}
            state.save()
            logger.info(f"Placed {sym} order @ {buy}")

            # Broadcast log to UI
            asyncio.create_task(manager.broadcast({
                "type": "TRADE_LOG",
                "log": {
                    "id": str(order.id),
                    "symbol": sym,
                    "type": "BUY",
                    "price": buy,
                    "timestamp": datetime.now().strftime("%H:%M:%S")
                }
            }))
        except Exception as e:
            logger.error(f"Order Failed for {sym}: {e}")

# --- BACKGROUND LOOPS ---
async def trading_loop():
    engine = StrategyEngine()
    while True:
        now = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=-5)))
        is_open = now.weekday() < 5 and (9 <= now.hour < 16)
        
        if not state.paused and is_open:
            for sym in list(state.tickers.keys()):
                engine.place_bracket(sym)
            
        await asyncio.sleep(60)

async def mock_data_generator():
    """Simulates market movements for UI testing."""
    while True:
        if not state.paused and state.tickers:
            symbol = random.choice(list(state.tickers.keys()))
            change = random.uniform(-5.0, 5.0)
            state.profits[symbol] = state.profits.get(symbol, 0) + change
            
            if random.random() > 0.8:
                await manager.broadcast({
                    "type": "TRADE_LOG",
                    "log": {
                        "id": f"mock_{random.randint(1000, 9999)}",
                        "symbol": symbol,
                        "type": random.choice(["BUY", "SELL", "STOP"]),
                        "price": 100.0 + random.uniform(-10, 10),
                        "timestamp": datetime.now().strftime("%H:%M:%S")
                    }
                })

            await manager.broadcast({
                "type": "INITIAL_STATE",
                "tickers": {k: v.model_dump() for k, v in state.tickers.items()},
                "paused": state.paused
            })
            
        await asyncio.sleep(5)

# --- APP SETUP ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(trading_loop())
    asyncio.create_task(mock_data_generator())
    yield

app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Adjust for production
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ROUTES ---
@app.get("/api/health")
async def health_check():
    return {"status": "online", "bot": "BracketBot", "alpaca": alpaca.connected}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Initial Push
        await websocket.send_json({
            "type": "INITIAL_STATE",
            "tickers": {k: v.model_dump() for k, v in state.tickers.items()},
            "paused": state.paused
        })

        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            action = msg.get("action")

            if action == "ADD_TICKER":
                sym = msg["symbol"]
                state.tickers[sym] = TickerConfig(symbol=sym, base_power=msg.get("base_power", 100.0))
            elif action == "DELETE_TICKER":
                state.tickers.pop(msg["symbol"], None)
            elif action == "GLOBAL_PAUSE":
                state.paused = msg.get("pause", False)
            elif action == "UPDATE_TICKER":
                sym = msg.get("symbol")
                if sym in state.tickers:
                    # Update ticker config dynamically
                    cfg_dict = state.tickers[sym].model_dump()
                    cfg_dict.update({k: v for k, v in msg.items() if k != "action"})
                    state.tickers[sym] = TickerConfig(**cfg_dict)
            
            state.save()
            await manager.broadcast({
                "type": "INITIAL_STATE",
                "tickers": {k: v.model_dump() for k, v in state.tickers.items()},
                "paused": state.paused
            })

    except WebSocketDisconnect:
        manager.disconnect(websocket)