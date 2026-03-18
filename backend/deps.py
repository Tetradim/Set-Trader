"""Shared dependencies — populated by server.py at startup.

Every module that needs access to global state imports this module
and reads deps.db, deps.engine, etc.  This breaks circular imports.
"""
import os
import logging
from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("SentinelPulse")

# MongoDB
mongo_url = os.environ["MONGO_URL"]
mongo_client = AsyncIOMotorClient(mongo_url)
db = mongo_client[os.environ["DB_NAME"]]

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
