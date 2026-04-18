"""Shared dependencies — populated by server.py at startup.

Every module that needs access to global state imports this module
and reads deps.db, deps.engine, etc.  This breaks circular imports.
"""
import os
import sys
import logging
import tempfile
from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

# Find .env in bundled app or development
if getattr(sys, 'frozen', False):
    # Running as bundled PyInstaller app
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).parent

# Try multiple possible .env locations
for env_path in [BASE_DIR / ".env", Path(".env")]:
    if env_path.exists():
        load_dotenv(env_path)
        break

ROOT_DIR = BASE_DIR

# Demo mode - enables mock data when MongoDB is unavailable
DEMO_MODE = os.environ.get("DEMO_MODE", "false").lower() in ("1", "true", "yes")

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("SentinelPulse")

# MongoDB - lazy initialization with optional connection
_mongo_client = None
_db = None
_mongo_connecting = False

def _ensure_db():
    """Lazily connect to MongoDB - returns None if not available."""
    global _mongo_client, _db, _mongo_connecting
    if _db is not None:
        return _db
    if _mongo_connecting:
        return None
    _mongo_connecting = True
    try:
        mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "sentinelpulse")
        _mongo_client = AsyncIOMotorClient(
            mongo_url,
            serverSelectionTimeoutMS=2000,
            connectTimeoutMS=2000,
        )
        _db = _mongo_client[db_name]
        logger.info("MongoDB connected")
        return _db
    except Exception as e:
        logger.warning(f"MongoDB connection failed: {e}")
        _mongo_connecting = False
        return None

# For backward compatibility: db and mongo_client are lazy-loaded
class LazyDB:
    """Lazy proxy to MongoDB database."""
    def __getattr__(self, name):
        db = _ensure_db()
        if db is None:
            raise AttributeError("MongoDB not available")
        return getattr(db, name)
    
    def __call__(self, *args, **kwargs):
        db = _ensure_db()
        if db is None:
            raise RuntimeError("MongoDB not available")
        return db(*args, **kwargs)

class LazyClient:
    """Lazy proxy to MongoDB client."""
    def __getattr__(self, name):
        if _mongo_client is None:
            _ensure_db()
        if _mongo_client is None:
            raise AttributeError("MongoDB not available")
        return getattr(_mongo_client, name)

mongo_client = LazyClient()
db = LazyDB()

# yfinance
YF_AVAILABLE = False
try:
    import yfinance as yf  # noqa: F401
    YF_AVAILABLE = True
except ImportError:
    logger.warning("yfinance not installed. Using simulated prices only.")

# Telegram library
TG_AVAILABLE = False
try:
    from telegram import Bot, Update  # noqa: F401
    from telegram.ext import Application, CommandHandler, ContextTypes  # noqa: F401
    TG_AVAILABLE = True
except ImportError:
    pass

# --- Singletons: set by server.py during lifespan ---
engine = None           # TradingEngine
ws_manager = None       # ConnectionManager
telegram_service = None # TelegramService
price_service = None    # PriceService
broker_mgr = None       # BrokerConnectionManager
tracer = None           # OpenTelemetry tracer
