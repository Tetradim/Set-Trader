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

# Logging - allow DEBUG via env var
_log_level = os.environ.get("LOG_LEVEL", "INFO")
_level_map = {"DEBUG": logging.DEBUG, "INFO": logging.INFO, "WARNING": logging.WARNING}
logging.basicConfig(level=_level_map.get(_log_level, logging.INFO), format="%(asctime)s | %(levelname)s | %(message)s")
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
            serverSelectionTimeoutMS=10000,
            connectTimeoutMS=10000,
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

# Demo mode: in-memory DB fallback
_demo_db = None

def get_demo_db():
    """Get in-memory database for demo mode."""
    global _demo_db
    if _demo_db is None:
        _demo_db = InMemoryDatabase()
    return _demo_db

class InMemoryCursor:
    """In-memory cursor for find() results."""
    def __init__(self, docs):
        self._docs = docs
    
    async def to_list(self, limit=None):
        if limit:
            return self._docs[:limit]
        return self._docs

class InMemoryCollection:
    """In-memory collection for demo mode."""
    def __init__(self):
        self._docs = []
        self._id_counter = 0
    
    async def find(self, query=None, projection=None):
        return InMemoryCursor(self._docs)
    
    async def insert_one(self, doc):
        self._id_counter += 1
        doc["_id"] = self._id_counter
        self._docs.append(doc)
        return doc
    
    async def update_one(self, query, update, upsert=False):
        for i, doc in enumerate(self._docs):
            if _match_query(query, doc):
                if "$set" in update:
                    doc.update(update["$set"])
                if "$setOnInsert" in update and upsert:
                    for k, v in update["$setOnInsert"].items():
                        if k not in doc:
                            doc[k] = v
                return doc
        if upsert:
            new_doc = dict(query)
            if "$set" in update:
                new_doc.update(update["$set"])
            if "$setOnInsert" in update:
                new_doc.update(update["$setOnInsert"])
            await self.insert_one(new_doc)
            return new_doc
        return None
    
    async def delete_one(self, query):
        for i, doc in enumerate(self._docs):
            if _match_query(query, doc):
                self._docs.pop(i)
                return
        return None
    
    async def find_one(self, query, projection=None):
        for doc in self._docs:
            if _match_query(query, doc):
                return doc
        return None
    
    async def create_index(self, *args, **kwargs):
        pass
    
    async def count_documents(self, query=None):
        if query is None:
            return len(self._docs)
        return sum(1 for doc in self._docs if _match_query(query, doc))

def _match_query(query, doc):
    if query is None:
        return True
    for k, v in query.items():
        if doc.get(k) != v:
            return False
    return True

class InMemoryDatabase:
    """In-memory database for demo mode."""
    def __init__(self):
        self.tickers = InMemoryCollection()
        self.trades = InMemoryCollection()
        self.profits = InMemoryCollection()
        self.settings = InMemoryCollection()
        self.audit_logs = InMemoryCollection()
        
        # Seed default tickers
        import asyncio
        loop = asyncio.get_event_loop()
        for sym in ["SPY", "QQQ", "AAPL", "NVDA"]:
            loop.run_until_complete(
                self.tickers.insert_one({"symbol": sym, "base_power": 100.0, "market": "US"})
            )
        # Seed default settings
        for key, value in [("account_balance", 100000.0), ("cash_reserve", 10000.0), 
                         ("increment_step", 0.5), ("decrement_step", 0.5)]:
            loop.run_until_complete(
                self.settings.insert_one({"key": key, "value": value})
            )


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
