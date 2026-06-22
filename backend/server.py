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
import logging
from contextlib import asynccontextmanager
from pathlib import Path

# Use centralized logging from logging_config.py
from logging_config import setup_logging

# Configure logging early - before any imports that might log
_log_file = getattr(sys, 'frozen', False) and 'sentinel_pulse.log' or 'logs/sentinel_pulse.log'
setup_logging(
    level=os.getenv("LOG_LEVEL", "INFO"),
    json_format=os.getenv("LOG_JSON", "false").lower() == "true",
    log_file=os.getenv("LOG_FILE", _log_file),
)
logger = logging.getLogger("SentinelPulse")

# Log detailed startup info
logger.info("=" * 80)
logger.info("🚀 Sentinel Pulse STARTING UP")
logger.info(f"PID: {os.getpid()} | Frozen: {getattr(sys, 'frozen', False)} | Python: {sys.version.split()[0]}")
logger.info(f"ENV: {os.getenv('ENVIRONMENT', 'production')}")
logger.info(f"LOG_LEVEL: {os.getenv('LOG_LEVEL', 'INFO')} | LOG_JSON: {os.getenv('LOG_JSON', 'false')}")

# Load .env file early so env vars are available
# For packaged apps, look in the working directory (not exe dir)
from dotenv import load_dotenv
from pathlib import Path

# Determine the .env path based on whether we're packaged
if getattr(sys, 'frozen', False):
    # Running as packaged exe - look in CWD (where exe was launched from)
    # or next to the exe in the app folder
    env_paths = [
        Path.cwd() / '.env',
        Path(sys.executable).parent / '.env',
    ]
    for env_path in env_paths:
        if env_path.exists():
            load_dotenv(env_path)
            logger.info(f"Loaded .env from: {env_path}")
            break
    else:
        load_dotenv()  # fallback to default behavior
else:
    load_dotenv()

from fastapi import FastAPI, APIRouter, Depends
from starlette.middleware.cors import CORSMiddleware

# Shared state (must be imported first — populates db, logger, etc.)
import deps
from bot_snapshot import build_bot_snapshot
from default_tickers import ensure_default_tickers
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
    from pymongo.errors import ServerSelectionTimeoutError
    
    while True:
        try:
            snapshot = await build_bot_snapshot()
            if snapshot["tickers"]:
                update = {
                    "prices": snapshot["prices"],
                    "price_sources": snapshot["price_sources"],
                    "price_errors": snapshot["price_errors"],
                    "positions": snapshot["positions"],
                    "profits": snapshot["profits"],
                    "cash_reserve": snapshot["cash_reserve"],
                    "account_balance": snapshot["account_balance"],
                    "allocated": snapshot["allocated"],
                    "available": snapshot["available"],
                    "trades": snapshot["trades"],
                    "paused": snapshot["paused"],
                    "running": snapshot["running"],
                    "market_open": snapshot["market_open"],
                    "simulate_24_7": snapshot["simulate_24_7"],
                    "market_hours_only": snapshot["market_hours_only"],
                    "live_during_market_hours": snapshot["live_during_market_hours"],
                    "paper_after_hours": snapshot["paper_after_hours"],
                    "replay": snapshot["replay"],
                }
                update["type"] = "PRICE_UPDATE"
                await deps.ws_manager.broadcast(update)
        except ServerSelectionTimeoutError as e:
            # MongoDB dropped - log but don't crash the loop
            deps.logger.warning(f"MongoDB temporarily unavailable: {e}")
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
                    "trading_mode": deps.engine.get_trading_mode(),
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
            # Pending limit sells may continue while paused, but a full stop must stop all bot activity.
            if deps.engine.running and deps.engine._pending_sells:
                await deps.engine.check_pending_sells()
        except Exception as e:
            deps.logger.error(f"Trading loop error: {e}", exc_info=True)
        await asyncio.sleep(add_jitter(5))


# --- App lifecycle ---
@asynccontextmanager
async def lifespan(application: FastAPI):
    # Always require MongoDB
    mongo_works = True
    mongo_error = None
    
    if getattr(sys, 'frozen', False):
        # Packaged mode - check if MongoDB exists bundled or system MongoDB running
        from pathlib import Path
        import socket
        
        mongo_exists = Path(sys._MEIPASS).joinpath("mongodb", "mongod.exe").exists()
        
        # Check if system MongoDB is running on port 27017
        system_mongo_ok = False
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex(('localhost', 27017))
            sock.close()
            system_mongo_ok = (result == 0)
        except:
            pass
        
        if not mongo_exists and not system_mongo_ok:
            raise RuntimeError("MongoDB is required but not found. Please install MongoDB or bundle mongod.exe")
        
        if system_mongo_ok:
            logger.info("Using system MongoDB on port 27017")
    
    try:
        await deps.db.command("ping")
    except Exception as e:
        mongo_error = str(e)
        mongo_works = False
    
    if not mongo_works:
        raise RuntimeError(f"MongoDB unavailable: {mongo_error}")
    
    logger.info("MongoDB connected")
    
    # Normal mode: create indexes
    try:
        await deps.db.tickers.create_index("symbol", unique=True)
        await deps.db.trades.create_index("timestamp")
        await deps.db.profits.create_index("symbol", unique=True)
        await deps.db.audit_logs.create_index("timestamp")
        await deps.db.audit_logs.create_index("event_type")
        await deps.db.replay_sessions.create_index("session_id", unique=True)
        await deps.db.replay_bars.create_index([("session_id", 1), ("timestamp", 1), ("symbol", 1)])
        logger.info("Database indexes created")
    except Exception as e:
        deps.logger.warning(f"Failed to create indexes: {e}")

    # Seed canonical defaults for fresh DBs and backfill legacy 3-ticker installs.
    try:
        await ensure_default_tickers(deps.db, logger)
    except Exception as e:
        deps.logger.warning(f"Failed to seed defaults: {e}")

    # Restore engine state
    try:
        await asyncio.wait_for(deps.engine.load_state(), timeout=3.0)
        logger.info("Engine state loaded")
    except Exception as e:
        deps.logger.warning(f"Failed to load engine state: {e}")
    try:
        await asyncio.wait_for(deps.engine.load_recent_exit_cooldowns(), timeout=3.0)
    except Exception as e:
        deps.logger.warning(f"Failed to load recent exit cooldowns: {e}")
    
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
    from shared import edge_client, init_edge_client, start_edge_heartbeat
    try:
        edge_retry_doc = await deps.db.settings.find_one({"key": "edge_retry_max_attempts"}, {"_id": 0})
        edge_client.set_max_retry_attempts(edge_retry_doc.get("value", 10) if edge_retry_doc else 10)
    except Exception as e:
        deps.logger.warning(f"Failed to load Edge retry settings: {e}")
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

    # Initialize notification service
    try:
        from notification_service import notification_service
        await notification_service.load_config()
        deps.logger.info("Notification service initialized")
    except Exception as e:
        deps.logger.warning(f"Failed to init notification service: {e}")

    deps.logger.info("Sentinel Pulse Engine started")
    yield

    # --- Graceful Shutdown ---
    logger.info("=" * 80)
    logger.info("🛑 Sentinel Pulse SHUTTING DOWN...")
    logger.info("Cancelling tasks, closing broker sessions, flushing audit logs...")

    # 1. Cancel background tasks gracefully
    try:
        current_task = asyncio.current_task()
        for task in asyncio.all_tasks():
            if task is not current_task and not task.done():
                task.cancel()
        await asyncio.gather(*asyncio.all_tasks(), return_exceptions=True)
        logger.info("Background tasks cancelled")
    except Exception as e:
        logger.warning(f"Task cancellation warning: {e}")

    # 2. Stop WS broadcast loop first to stop accepting new messages
    try:
        if hasattr(deps.ws_manager, 'stop_broadcast_loop'):
            await deps.ws_manager.stop_broadcast_loop()
        logger.info("WebSocket broadcast loop stopped")
    except Exception:
        pass
    
    # 3. Save engine state
    try:
        if deps.engine:
            deps.engine.running = False
            deps.engine.paused = True
        await deps.engine.save_state()
        logger.info("Engine state saved")
    except Exception:
        pass
    
    # 4. Stop broker manager
    try:
        if hasattr(deps.broker_mgr, 'save_idempotency_keys'):
            await deps.broker_mgr.save_idempotency_keys()
        logger.info("Broker sessions closed")
    except Exception:
        pass
    
    # 5. Stop Telegram gracefully
    try:
        if deps.telegram_service:
            await deps.telegram_service.stop()
        logger.info("Telegram service stopped")
    except Exception:
        pass
    
    # 6. Close MongoDB connection
    try:
        if hasattr(deps, "mongo_client") and deps.mongo_client:
            deps.mongo_client.close()
    except Exception as e:
        logger.warning(f"MongoDB close warning: {e}")
    logger.info("✅ Shutdown complete. Goodbye.")


# --- FastAPI app ---
app = FastAPI(title="Sentinel Pulse", lifespan=lifespan)

# OpenTelemetry
from telemetry import setup_telemetry, get_tracer
setup_telemetry(app)
deps.tracer = get_tracer()

# CORS configuration - secure defaults
# Set CORS_ORIGINS env var in production to limit access
DEFAULT_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8001",
    "http://127.0.0.1:8001",
    "http://localhost:8002",
    "http://127.0.0.1:8002",
]
_cors_origins = os.environ.get("CORS_ORIGINS", "")
if _cors_origins == "*":
    # WARNING: Wildcard origins should only be used on trusted local networks.
    import logging
    logging.getLogger("SentinelPulse").warning(
        "CORS set to wildcard - this is insecure for production! "
        "Set CORS_ORIGINS to specific origins."
    )

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=_cors_origins.split(",") if _cors_origins else DEFAULT_CORS_ORIGINS,
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
from routes.settings import router as settings_router
from routes.ws import router as ws_router
from routes.system import router as system_router
from routes.markets import router as markets_router
from routes.strategies import router as strategies_router
from routes.edge import router as edge_router
from routes.bot_bus import router as bot_bus_router
from routes.chrome_bridge import router as chrome_bridge_router
from routes.risk import router as risk_router
from routes.auth import router as auth_router
from routes.orders import router as orders_router
from routes.reconciliation import router as reconciliation_router
from routes.audit import router as audit_router
from alert_handler import router as alert_router
from routes.ops import router as ops_router
from routes.analytics import router as analytics_router
from routes.slo import router as slo_router
from routes.notifications import router as notifications_router
from routes.portfolio import router as portfolio_router
from routes.logs import router as logs_router
from routes.replay import router as replay_router
from auth import get_current_user

api.include_router(health_router)
api.include_router(brokers_router, dependencies=[Depends(get_current_user)])
api.include_router(tickers_router, dependencies=[Depends(get_current_user)])
api.include_router(trades_router, dependencies=[Depends(get_current_user)])
api.include_router(bot_router, dependencies=[Depends(get_current_user)])
api.include_router(settings_router, dependencies=[Depends(get_current_user)])
api.include_router(ws_router)
api.include_router(system_router, dependencies=[Depends(get_current_user)])
api.include_router(markets_router, dependencies=[Depends(get_current_user)])
api.include_router(strategies_router, dependencies=[Depends(get_current_user)])
api.include_router(edge_router)
api.include_router(bot_bus_router)
api.include_router(chrome_bridge_router)
api.include_router(risk_router, dependencies=[Depends(get_current_user)])
api.include_router(auth_router)
api.include_router(orders_router, dependencies=[Depends(get_current_user)])
api.include_router(reconciliation_router, dependencies=[Depends(get_current_user)])
api.include_router(audit_router, dependencies=[Depends(get_current_user)])
api.include_router(alert_router)
api.include_router(ops_router, dependencies=[Depends(get_current_user)])
api.include_router(analytics_router, dependencies=[Depends(get_current_user)])
api.include_router(slo_router, dependencies=[Depends(get_current_user)])
api.include_router(notifications_router, dependencies=[Depends(get_current_user)])
api.include_router(portfolio_router, dependencies=[Depends(get_current_user)])
api.include_router(logs_router, dependencies=[Depends(get_current_user)])
api.include_router(replay_router, dependencies=[Depends(get_current_user)])

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
    
    # Check if running as frozen executable (PyInstaller)
    port = int(os.getenv("PORT", "8002"))
    
    if getattr(sys, 'frozen', False):
        print("\n" + "="*50)
        print("  Sentinel Pulse - Trading Bot")
        print("="*50)
        print(f"\n  Server starting on http://localhost:{port}")
        print("  Browser will open automatically...")
        print("\n  Press Ctrl+C to stop the server.\n")
    
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
