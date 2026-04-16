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

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("SentinelPulse")

# MongoDB - use getenv with defaults
mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
db_name = os.environ.get("DB_NAME", "sentinelpulse")
mongo_client = AsyncIOMotorClient(mongo_url)
db = mongo_client[db_name]

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
