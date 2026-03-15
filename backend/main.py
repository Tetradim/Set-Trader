# backend/main.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import asyncio, json, os, threading, logging
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager

# LOGGING & LOCKS
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("BracketBot")
file_lock = threading.Lock()

try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.enums import OrderSide, OrderClass, TimeInForce, OrderStatus
    from alpaca.trading.requests import LimitOrderRequest, StopLossRequest, TakeProfitRequest
    from alpaca.data import StockHistoricalDataClient, StockBarsRequest, StockLatestQuoteRequest
    from alpaca.data.timeframe import TimeFrame
    ALPACA_AVAILABLE = True
except ImportError:
    ALPACA_AVAILABLE = False

STATE_FILE, TRADES_FILE = "bot_state.json", "trades_history.json"

# SCHEMAS
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

class AppState:
    def __init__(self):
        self.tickers, self.profits, self.tracked_orders, self.paused = {}, {}, {}, False
        self.load()

    def load(self):
        if os.path.exists(STATE_FILE):
            with file_lock:
                try:
                    with open(STATE_FILE, "r") as f:
                        d = json.load(f)
                        self.tickers = {k: TickerConfig(**v) for k, v in d.get("tickers", {}).items()}
                        self.profits, self.tracked_orders, self.paused = d.get("profits", {}), d.get("tracked_orders", {}), d.get("paused", False)
                except Exception as e: logger.error(f"Load Error: {e}")

    def save(self):
        with file_lock:
            try:
                with open(STATE_FILE, "w") as f:
                    json.dump({"tickers": {k: v.model_dump() for k, v in self.tickers.items()}, "profits": self.profits, "tracked_orders": self.tracked_orders, "paused": self.paused}, f, indent=2)
            except Exception as e: logger.error(f"Save Error: {e}")

state = AppState()

# ALPACA SERVICE
class AlpacaService:
    def __init__(self):
        self.trading_client, self.data_client, self.connected = None, None, False
        self._init()

    def _init(self):
        key, secret = os.getenv("ALPACA_KEY"), os.getenv("ALPACA_SECRET")
        if key and secret and ALPACA_AVAILABLE:
            try:
                self.trading_client = TradingClient(key, secret, paper=True)
                self.data_client = StockHistoricalDataClient(key, secret)
                self.connected = True
            except: pass

    def get_current_price(self, symbol):
        if not self.connected: return 0.0
        try:
            q = self.data_client.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=symbol))
            return float(q[symbol].ask_price)
        except: return 0.0

    def get_avg_price(self, symbol, days):
        if not self.connected: return 0.0
        try:
            req = StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Day, start=datetime.now(timezone.utc)-timedelta(days=days+5), end=datetime.now(timezone.utc))
            df = self.data_client.get_stock_bars(req).df
            return float(df["close"].tail(days).mean())
        except: return 0.0

alpaca = AlpacaService()

# STRATEGY & LOOP
class StrategyEngine:
    def place_bracket(self, sym):
        if not alpaca.connected or state.paused: return
        cfg = state.tickers.get(sym)
        if not cfg or not cfg.enabled: return
        
        avg = alpaca.get_avg_price(sym, cfg.avg_days)
        buy = round(avg * (1 + cfg.buy_offset/100) if cfg.buy_percent else avg + cfg.buy_offset, 2)
        sell = round(avg * (1 + cfg.sell_offset/100) if cfg.sell_percent else avg + cfg.sell_offset, 2)
        stop = round(buy * (1 + cfg.stop_offset/100) if cfg.stop_percent else buy + cfg.stop_offset, 2)
        
        qty = int(cfg.base_power // buy)
        if qty < 1: return

        try:
            order = alpaca.trading_client.submit_order(LimitOrderRequest(
                symbol=sym, qty=qty, side=OrderSide.BUY, time_in_force=TimeInForce.GTC,
                limit_price=buy, order_class=OrderClass.BRACKET,
                take_profit=TakeProfitRequest(limit_price=sell), stop_loss=StopLossRequest(stop_price=stop)
            ))
            state.tracked_orders[str(order.id)] = {"symbol": sym, "buy": buy}
            state.save()
            logger.info(f"Placed {sym} order @ {buy}")
        except Exception as e: logger.error(f"Order Failed: {e}")

async def trading_loop():
    engine = StrategyEngine()
    while True:
        now = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=-5)))
        is_open = now.weekday() < 5 and (9 <= now.hour < 16)
        if is_open and not state.paused:
            for sym in list(state.tickers.keys()):
                engine.place_bracket(sym)
        await asyncio.sleep(60)

# APP SETUP
@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(trading_loop())
    yield

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"], allow_methods=["*"], allow_headers=["*"])

@app.get("/state")
async def get_bot_state():
    return {"paused": state.paused, "tickers": state.tickers, "connected": alpaca.connected}
# Add these endpoints to your main.py file

@app.post("/tickers")
async def add_ticker(config: TickerConfig):
    state.tickers[config.symbol] = config
    state.save()
    logger.info(f"Added new ticker: {config.symbol}")
    return {"status": "success"}

@app.delete("/tickers/{symbol}")
async def delete_ticker(symbol: str):
    if symbol in state.tickers:
        del state.tickers[symbol]
        state.save()
        logger.info(f"Deleted ticker: {symbol}")
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Ticker not found")

@app.post("/pause")
async def toggle_pause():
    state.paused = not state.paused
    state.save()
    return {"paused": state.paused}

# Run with: uvicorn main:app --reload