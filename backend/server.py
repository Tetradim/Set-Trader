"""Sentinel Pulse — FastAPI application entry point.

This is the slim orchestrator that wires together all modules:
- deps.py: shared state
- schemas.py: Pydantic models
- ws_manager.py: WebSocket manager
- price_service.py: price data service
- trading_engine.py: core trading logic
- telegram_service.py: Telegram bot service
- broker_manager.py: broker connection manager
- routes/: API route modules
"""
import asyncio
import os
import sys
import webbrowser
import threading
from contextlib import asynccontextmanager
from pathlib import Path

# Load .env file early so env vars are available
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, APIRouter
from starlette.middleware.cors import CORSMiddleware

# Shared state (must be imported first — populates db, logger, etc.)
import deps
from schemas import TickerConfig
from ws_manager import ConnectionManager
from price_service import PriceService
from trading_engine import TradingEngine
from telegram_service import TelegramService
from broker_manager import BrokerConnectionManager
from resilience import CircuitOpenError

# --- Instantiate singletons and register in deps ---
deps.ws_manager = ConnectionManager()
deps.price_service = PriceService()
deps.engine = TradingEngine()
deps.telegram_service = TelegramService()
deps.broker_mgr = BrokerConnectionManager(deps.db)


# --- Background tasks ---
import random

def add_jitter(base_seconds: float, jitter_pct: float = 0.2) -> float:
    """Add random jitter to prevent thundering herd on restart."""
    jitter = base_seconds * jitter_pct
    return base_seconds + random.uniform(-jitter, jitter)


async def price_broadcast_loop():
    while True:
        try:
            tickers = await deps.db.tickers.find({}, {"_id": 0}).to_list(100)
            if tickers:
                prices = {}
                for t in tickers:
                    sym = t["symbol"]
                    prices[sym] = await deps.price_service.get_price(sym)

                positions = {}
                for sym, pos in deps.engine._positions.items():
                    if pos["qty"] > 0:
                        cp = prices.get(sym, 0)
                        mv = round(cp * pos["qty"], 2)
                        positions[sym] = {
                            "symbol": sym, "quantity": pos["qty"],
                            "avg_entry": pos["avg_entry"], "current_price": cp,
                            "market_value": mv,
                            "unrealized_pnl": round((cp - pos["avg_entry"]) * pos["qty"], 2),
                        }

                profits_list = await deps.db.profits.find({}, {"_id": 0}).to_list(100)
                profits = {p["symbol"]: p.get("total_pnl", 0) for p in profits_list}

                cash_doc = await deps.db.settings.find_one({"key": "cash_reserve"}, {"_id": 0})
                cash_reserve = round(cash_doc.get("value", 0), 2) if cash_doc else 0

                await deps.ws_manager.broadcast({
                    "type": "PRICE_UPDATE",
                    "prices": prices,
                    "positions": positions,
                    "profits": profits,
                    "cash_reserve": cash_reserve,
                    "paused": deps.engine.paused,
                    "running": deps.engine.running,
                    "market_open": deps.engine.is_market_open(),
                    "simulate_24_7": deps.engine.simulate_24_7,
                    "market_hours_only": deps.engine.market_hours_only,
                })
        except Exception as e:
            deps.logger.error(f"Price broadcast error: {e}", exc_info=True)
        await asyncio.sleep(add_jitter(2))


async def trading_loop():
    while True:
        try:
            # Check for auto mode switching based on market hours
            if deps.engine.check_auto_mode_switch():
                await deps.engine.save_state()
                await deps.ws_manager.broadcast({
                    "type": "MODE_SWITCH",
                    "simulate_24_7": deps.engine.simulate_24_7,
                    "trading_mode": "paper" if deps.engine.simulate_24_7 else "live",
                })
            
            if deps.engine.running and not deps.engine.paused:
                # Market hours checked per-ticker inside evaluate_ticker
                # to support multiple international exchanges simultaneously
                tickers = await deps.db.tickers.find({"enabled": True}, {"_id": 0}).to_list(100)
                for t in tickers:
                    try:
                        await deps.engine.evaluate_ticker(t)
                    except CircuitOpenError as ce:
                        deps.logger.warning(f"Skipping {t.get('symbol','?')} — {ce}")
                    except Exception as te:
                        deps.logger.error(f"Evaluate {t.get('symbol','?')} error: {te}", exc_info=True)
            # Always check pending limit sells (even when paused — user explicitly requested)
            if deps.engine._pending_sells:
                await deps.engine.check_pending_sells()
        except Exception as e:
            deps.logger.error(f"Trading loop error: {e}", exc_info=True)
        await asyncio.sleep(add_jitter(5))


# --- App lifecycle ---
# Demo mode flag - set to True when MongoDB unavailable
DEMO_MODE_ACTIVE = False

@asynccontextmanager
async def lifespan(application: FastAPI):
    global DEMO_MODE_ACTIVE
    
    # Check demo mode - use mock data if no MongoDB
    demo_forced = os.environ.get("DEMO_MODE", "").lower() in ("1", "true", "yes")
    
    # Try to connect to MongoDB
    mongo_works = True
    try:
        await deps.db.command("ping")
    except Exception:
        mongo_works = False
    
    DEMO_MODE_ACTIVE = demo_forced or not mongo_works
    
    if DEMO_MODE_ACTIVE:
        deps.logger.info("Demo mode enabled - using in-memory data")
        yield
        return
    
    # Normal mode: create indexes
    try:
        await deps.db.tickers.create_index("symbol", unique=True)
        await deps.db.trades.create_index("timestamp")
        await deps.db.profits.create_index("symbol", unique=True)
        await deps.db.audit_logs.create_index("timestamp")
        await deps.db.audit_logs.create_index("event_type")
    except Exception as e:
        deps.logger.warning(f"Failed to create indexes: {e}")

    # Seed defaults if empty
    try:
        count = await deps.db.tickers.count_documents({})
        if count == 0:
            for sym in ["TSLA", "AAPL", "NVDA"]:
                t = TickerConfig(symbol=sym, base_power=100.0)
                await deps.db.tickers.update_one(
                    {"symbol": sym}, {"$setOnInsert": t.model_dump()}, upsert=True
                )
    except Exception as e:
        deps.logger.warning(f"Failed to seed defaults: {e}")

    # Restore engine state
    try:
        await asyncio.wait_for(deps.engine.load_state(), timeout=3.0)
    except Exception as e:
        deps.logger.warning(f"Failed to load engine state: {e}")
    
    # Load price service preference
    try:
        pref_doc = await asyncio.wait_for(deps.db.settings.find_one({"key": "prefer_broker_feeds"}), timeout=3.0)
        if pref_doc:
            deps.price_service.set_prefer_broker_feeds(pref_doc.get("value", True))
    except Exception as e:
        deps.logger.warning(f"Failed to load settings: {e}")
    
    # Initialize resilience (token-bucket rate limiter + circuit breakers)
    try:
        from resilience import broker_resilience
        broker_resilience.set_telegram(deps.telegram_service)
        broker_resilience.set_ws_manager(deps.ws_manager)
        await asyncio.wait_for(broker_resilience.load_config(), timeout=3.0)
    except Exception as e:
        deps.logger.warning(f"Failed to init resilience: {e}")

    # Load pluggable strategy system
    try:
        from strategies.loader import load_all_strategies, start_strategy_watcher
        strategies = await asyncio.wait_for(load_all_strategies(), timeout=3.0)
        start_strategy_watcher()
        deps.logger.info(f"Loaded {len(strategies)} strategy plugins")
    except Exception as e:
        deps.logger.warning(f"Failed to load strategies: {e}", exc_info=True)

    # Initialize broker manager dependencies
    deps.broker_mgr.set_telegram(deps.telegram_service)
    deps.broker_mgr.set_ws_manager(deps.ws_manager)
    try:
        await asyncio.wait_for(deps.broker_mgr.auto_connect_all(), timeout=3.0)
    except Exception as e:
        deps.logger.warning(f"Broker auto-connect failed: {e}")

    # Initialize Edge MongoDB client (for Edge ↔ Pulse integration)
    from shared import init_edge_client, start_edge_heartbeat
    await init_edge_client()
    await start_edge_heartbeat()
    
    # Start background tasks
    asyncio.create_task(price_broadcast_loop())
    asyncio.create_task(trading_loop())

    # Start Telegram if token exists
    try:
        await deps.telegram_service.reload_from_db()
    except Exception as e:
        deps.logger.warning(f"Telegram auto-start failed: {e}")

    deps.logger.info("Sentinel Pulse Engine started")
    yield

    # --- Graceful Shutdown ---
    deps.logger.info("Sentinel Pulse shutting down...")
    
    # Stop WS broadcast loop first to stop accepting new messages
    try:
        if hasattr(deps.ws_manager, 'stop_broadcast_loop'):
            await deps.ws_manager.stop_broadcast_loop()
    except Exception:
        pass
    
    # Save engine state
    try:
        await deps.engine.save_state()
    except Exception:
        pass
    
    # Stop broker manager
    try:
        if hasattr(deps.broker_mgr, 'save_idempotency_keys'):
            await deps.broker_mgr.save_idempotency_keys()
    except Exception:
        pass
    
    # Stop Telegram gracefully
    try:
        await deps.telegram_service.stop()
    except Exception:
        pass
    
    # Close MongoDB
    deps.mongo_client.close()
    deps.logger.info("Sentinel Pulse shutdown complete")


# --- FastAPI app ---
app = FastAPI(title="Sentinel Pulse", lifespan=lifespan)

# OpenTelemetry
from telemetry import setup_telemetry, get_tracer
setup_telemetry(app)
deps.tracer = get_tracer()

# CORS configuration - secure defaults
# Set CORS_ORIGINS env var in production to limit access
_cors_origins = os.environ.get("CORS_ORIGINS", "")
if _cors_origins == "*":
    # WARNING: Wildcard allowed only in development
    import logging
    logging.getLogger("SentinelPulse").warning(
        "CORS set to wildcard - this is insecure for production! "
        "Set CORS_ORIGINS to specific origins."
    )

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=_cors_origins.split(",") if _cors_origins else ["http://localhost:8001"],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)

# --- Mount routers ---
api = APIRouter(prefix="/api")

from routes.health import router as health_router
from routes.brokers import router as brokers_router
from routes.tickers import router as tickers_router
from routes.trades import router as trades_router
from routes.bot import router as bot_router
from routes.ws import router as ws_router
from routes.system import router as system_router
from routes.markets import router as markets_router
from routes.strategies import router as strategies_router
from routes.edge import router as edge_router

api.include_router(health_router)
api.include_router(brokers_router)
api.include_router(tickers_router)
api.include_router(trades_router)
api.include_router(bot_router)
api.include_router(ws_router)
api.include_router(system_router)
api.include_router(markets_router)
api.include_router(strategies_router)
api.include_router(edge_router)

app.include_router(api)

# --- Static file serving (for packaged desktop builds) ---
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


# --- Run as standalone executable ---
if __name__ == "__main__":
    import uvicorn
    
    # Open browser after a short delay
    def open_browser():
        import time
        time.sleep(2)
        webbrowser.open(f"http://localhost:{port}")
    
    # Check if running as frozen executable (PyInstaller)
    port = int(os.getenv("PORT", "8002"))
    
    if getattr(sys, 'frozen', False):
        threading.Thread(target=open_browser, daemon=True).start()
        print("\n" + "="*50)
        print("  Sentinel Pulse - Trading Bot")
        print("="*50)
        print(f"\n  Server starting on http://localhost:{port}")
        print("  Browser will open automatically...")
        print("\n  Press Ctrl+C to stop the server.\n")
    
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
