# bot_dashboard_enhanced.py
# Run with: streamlit run bot_dashboard_enhanced.py
# Requirements: pip install streamlit alpaca-py pandas pyTelegramBotAPI jsonschema

import json
import os
import threading
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

import pandas as pd
import streamlit as st
import telebot
from jsonschema import validate, ValidationError as JsonValidationError
from alpaca.data import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce, OrderStatus
from alpaca.trading.requests import LimitOrderRequest, StopLossRequest, TakeProfitRequest

# ─────────────────────────────────────────────────
# Logging Setup
# ─────────────────────────────────────────────────

LOG_FILE = "bot_dashboard.log"
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Create logger
logger = logging.getLogger("BracketBot")
logger.setLevel(logging.DEBUG)

# File handler
file_handler = logging.FileHandler(LOG_FILE, mode='a')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))

# Console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))

# Add handlers (avoid duplicates)
if not logger.handlers:
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

# ─────────────────────────────────────────────────
# Constants & Enums
# ─────────────────────────────────────────────────

CONFIG_FILE = "ticker_config.json"
PAUSE_FILE = "pause.flag"
TRADES_HISTORY_FILE = "trades_history.json"

class TradeStatus(Enum):
    WAITING = "Waiting"
    IN_TRADE = "In-trade"
    PENDING_ORDER = "Pending"
    FILLED = "Filled"

# ─────────────────────────────────────────────────
# Configuration Schema for Validation
# ─────────────────────────────────────────────────

TICKER_CONFIG_SCHEMA = {
    "type": "object",
    "properties": {
        "buy_power": {"type": "number", "minimum": 1, "maximum": 1000000},
        "avg_days": {"type": "integer", "minimum": 1, "maximum": 365},
        "buy_offset": {"type": "number", "minimum": -50, "maximum": 50},
        "buy_is_percent": {"type": "boolean"},
        "sell_offset": {"type": "number", "minimum": -50, "maximum": 100},
        "sell_is_percent": {"type": "boolean"},
        "stop_offset": {"type": "number", "minimum": -50, "maximum": 50},
        "stop_is_percent": {"type": "boolean"},
        "compound_enabled": {"type": "boolean"},
        "max_multiple": {"type": "number", "minimum": 1, "maximum": 100},
        "max_dollar_cap": {"type": "number", "minimum": 0, "maximum": 10000000},
    },
    "required": ["buy_power", "avg_days", "buy_offset", "buy_is_percent", 
                 "sell_offset", "sell_is_percent", "stop_offset", "stop_is_percent"],
    "additionalProperties": False
}

CONFIG_SCHEMA = {
    "type": "object",
    "properties": {
        "tickers": {
            "type": "object",
            "additionalProperties": TICKER_CONFIG_SCHEMA
        },
        "profits": {
            "type": "object",
            "additionalProperties": {"type": "number"}
        },
        "tracked_orders": {
            "type": "object",
            "additionalProperties": {"type": "object"}
        }
    },
    "required": ["tickers", "profits"]
}

TICKER_DEFAULTS = {
    "buy_power": 100.0,
    "avg_days": 168,
    "buy_offset": -3.0,
    "buy_is_percent": True,
    "sell_offset": 3.0,
    "sell_is_percent": True,
    "stop_offset": -6.0,
    "stop_is_percent": True,
    "compound_enabled": False,
    "max_multiple": 5.0,
    "max_dollar_cap": 10000.0,
}

# ─────────────────────────────────────────────────
# Input Validation Helpers
# ─────────────────────────────────────────────────

class ValidationError(Exception):
    """Custom validation error with user-friendly messages"""
    pass

def validate_symbol(symbol: str) -> str:
    """Validate and normalize stock symbol"""
    if not symbol:
        raise ValidationError("Symbol cannot be empty")
    
    symbol = symbol.strip().upper()
    
    if not symbol.isalpha():
        raise ValidationError(f"Invalid symbol '{symbol}': must contain only letters")
    
    if len(symbol) > 5:
        raise ValidationError(f"Invalid symbol '{symbol}': must be 5 characters or less")
    
    return symbol

def validate_buy_power(value: float) -> float:
    """Validate buy power amount"""
    if value < 1:
        raise ValidationError("Buy power must be at least $1")
    if value > 1000000:
        raise ValidationError("Buy power cannot exceed $1,000,000")
    return float(value)

def validate_avg_days(value: int) -> int:
    """Validate averaging days"""
    if value < 1:
        raise ValidationError("Averaging days must be at least 1")
    if value > 365:
        raise ValidationError("Averaging days cannot exceed 365")
    return int(value)

def validate_offset(value: float, name: str, min_val: float = -50, max_val: float = 100) -> float:
    """Validate offset value"""
    if value < min_val:
        raise ValidationError(f"{name} cannot be less than {min_val}")
    if value > max_val:
        raise ValidationError(f"{name} cannot exceed {max_val}")
    return float(value)

def validate_config_schema(config: dict) -> Tuple[bool, str]:
    """Validate entire configuration against schema"""
    try:
        validate(instance=config, schema=CONFIG_SCHEMA)
        return True, "Configuration is valid"
    except JsonValidationError as e:
        return False, f"Configuration validation error: {e.message}"

# ─────────────────────────────────────────────────
# Config Persistence with Validation
# ─────────────────────────────────────────────────

def load_config() -> dict:
    """Load and validate configuration from file"""
    default_config = {"tickers": {}, "profits": {}, "tracked_orders": {}}
    
    if not os.path.exists(CONFIG_FILE):
        logger.info("Config file not found, creating default configuration")
        return default_config
    
    try:
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
        
        # Ensure required keys exist
        data.setdefault("profits", {})
        data.setdefault("tickers", {})
        data.setdefault("tracked_orders", {})
        
        # Validate schema
        is_valid, msg = validate_config_schema(data)
        if not is_valid:
            logger.warning(f"Config validation warning: {msg}")
            # Attempt to repair by removing invalid entries
            data = repair_config(data)
        
        logger.info(f"Configuration loaded: {len(data['tickers'])} tickers")
        return data
        
    except json.JSONDecodeError as e:
        logger.error(f"Config file corrupted (JSON error): {e}")
        backup_file = f"{CONFIG_FILE}.backup.{int(time.time())}"
        os.rename(CONFIG_FILE, backup_file)
        logger.info(f"Corrupted config backed up to {backup_file}")
        return default_config
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return default_config

def repair_config(config: dict) -> dict:
    """Attempt to repair invalid configuration"""
    repaired = {"tickers": {}, "profits": {}, "tracked_orders": {}}
    
    # Repair tickers
    for symbol, cfg in config.get("tickers", {}).items():
        try:
            symbol = validate_symbol(symbol)
            # Apply defaults for missing fields
            repaired_cfg = {**TICKER_DEFAULTS, **cfg}
            repaired["tickers"][symbol] = repaired_cfg
        except ValidationError as e:
            logger.warning(f"Skipping invalid ticker {symbol}: {e}")
    
    # Copy profits for valid tickers only
    for symbol in repaired["tickers"]:
        if symbol in config.get("profits", {}):
            repaired["profits"][symbol] = float(config["profits"][symbol])
        else:
            repaired["profits"][symbol] = 0.0
    
    # Copy tracked orders
    repaired["tracked_orders"] = config.get("tracked_orders", {})
    
    logger.info(f"Config repaired: {len(repaired['tickers'])} valid tickers")
    return repaired

def save_config(config: dict) -> bool:
    """Save configuration to file with validation"""
    try:
        # Validate before saving
        is_valid, msg = validate_config_schema(config)
        if not is_valid:
            logger.warning(f"Saving potentially invalid config: {msg}")
        
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)
        
        logger.debug("Configuration saved successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to save config: {e}")
        return False

# ─────────────────────────────────────────────────
# Trade History Management
# ─────────────────────────────────────────────────

def load_trade_history() -> List[dict]:
    """Load trade history from file"""
    if not os.path.exists(TRADES_HISTORY_FILE):
        return []
    try:
        with open(TRADES_HISTORY_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load trade history: {e}")
        return []

def save_trade_history(history: List[dict]) -> bool:
    """Save trade history to file"""
    try:
        # Keep only last 1000 trades
        history = history[-1000:]
        with open(TRADES_HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Failed to save trade history: {e}")
        return False

def add_trade_record(symbol: str, order_id: str, action: str, 
                     qty: int, price: float, profit: float = 0.0) -> None:
    """Add a trade record to history"""
    history = load_trade_history()
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "order_id": order_id,
        "action": action,
        "qty": qty,
        "price": price,
        "profit": profit
    }
    history.append(record)
    save_trade_history(history)
    logger.info(f"Trade recorded: {action} {qty} {symbol} @ ${price:.2f}")

# ─────────────────────────────────────────────────
# Trading Helpers with Enhanced Error Handling
# ─────────────────────────────────────────────────

def get_avg_price(symbol: str, days: int, data_client) -> Tuple[float, str]:
    """
    Fetch average price with detailed error reporting
    Returns: (price, error_message) - error_message is empty on success
    """
    if not data_client:
        return 0.0, "Data client not connected"
    
    try:
        symbol = validate_symbol(symbol)
        days = validate_avg_days(days)
    except ValidationError as e:
        return 0.0, str(e)
    
    try:
        end = datetime.now()
        start = end - timedelta(days=days + 10)
        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Day,
            start=start,
            end=end,
            limit=days + 5,
        )
        bars = data_client.get_stock_bars(req).df
        
        if bars.empty:
            logger.warning(f"No data returned for {symbol}")
            return 0.0, f"No historical data available for {symbol}"
        
        avg = float(bars["close"].tail(days).mean())
        logger.debug(f"Average price for {symbol} ({days}d): ${avg:.2f}")
        return avg, ""
        
    except Exception as e:
        error_msg = f"API error fetching {symbol}: {str(e)}"
        logger.error(error_msg)
        return 0.0, error_msg

def has_open_position(symbol: str, trading_client) -> Tuple[bool, Optional[dict]]:
    """
    Check for open position with position details
    Returns: (has_position, position_info)
    """
    if not trading_client:
        return False, None
    
    try:
        position = trading_client.get_open_position(symbol)
        position_info = {
            "qty": int(position.qty),
            "avg_entry": float(position.avg_entry_price),
            "current_price": float(position.current_price),
            "unrealized_pl": float(position.unrealized_pl),
            "unrealized_plpc": float(position.unrealized_plpc) * 100
        }
        logger.debug(f"Open position for {symbol}: {position_info}")
        return True, position_info
    except Exception:
        return False, None

def get_open_orders(symbol: str, trading_client) -> List[dict]:
    """Get all open orders for a symbol"""
    if not trading_client:
        return []
    
    try:
        orders = trading_client.get_orders(
            filter={"symbol": symbol, "status": "open"}
        )
        return [
            {
                "id": str(order.id),
                "symbol": order.symbol,
                "side": str(order.side),
                "qty": int(order.qty),
                "type": str(order.type),
                "limit_price": float(order.limit_price) if order.limit_price else None,
                "status": str(order.status),
                "created_at": order.created_at.isoformat() if order.created_at else None
            }
            for order in orders
        ]
    except Exception as e:
        logger.error(f"Error fetching orders for {symbol}: {e}")
        return []

def cancel_orders(symbol: str, trading_client) -> Tuple[int, List[str]]:
    """
    Cancel all open orders for a symbol
    Returns: (cancelled_count, error_messages)
    """
    if not trading_client:
        return 0, ["Trading client not connected"]
    
    errors = []
    cancelled = 0
    
    try:
        orders = trading_client.get_orders(filter={"symbol": symbol, "status": "open"})
        
        for order in orders:
            try:
                trading_client.cancel_order_by_id(order.id)
                cancelled += 1
                logger.info(f"Cancelled order {order.id} for {symbol}")
            except Exception as e:
                error_msg = f"Failed to cancel order {order.id}: {e}"
                errors.append(error_msg)
                logger.error(error_msg)
        
        return cancelled, errors
        
    except Exception as e:
        error_msg = f"Error fetching orders to cancel: {e}"
        logger.error(error_msg)
        return 0, [error_msg]

def cancel_all_orders(trading_client) -> Tuple[int, List[str]]:
    """
    Cancel ALL open orders across all symbols
    Returns: (cancelled_count, error_messages)
    """
    if not trading_client:
        return 0, ["Trading client not connected"]
    
    try:
        trading_client.cancel_orders()
        logger.info("All orders cancelled successfully")
        return -1, []  # -1 indicates all orders cancelled (count unknown)
    except Exception as e:
        error_msg = f"Error cancelling all orders: {e}"
        logger.error(error_msg)
        return 0, [error_msg]

def calc_effective_power(cfg: dict, profit: float) -> float:
    """Calculate effective buying power with compounding logic"""
    effective = cfg["buy_power"] + profit
    
    if cfg.get("compound_enabled", False):
        cap_multiple = cfg["buy_power"] * cfg.get("max_multiple", 5.0)
        cap_dollar = cfg.get("max_dollar_cap") or float("inf")
        effective = min(effective, cap_multiple, cap_dollar)
    
    return max(effective, 0)  # Never negative

def place_bracket(symbol: str, cfg: dict, effective_power: float,
                  trading_client, data_client, config: dict) -> Tuple[str, Optional[str]]:
    """
    Place bracket order with enhanced error handling
    Returns: (message, order_id or None)
    """
    if not trading_client:
        return "Trading client not connected.", None

    try:
        symbol = validate_symbol(symbol)
    except ValidationError as e:
        return str(e), None

    avg, error = get_avg_price(symbol, cfg["avg_days"], data_client)
    if error:
        return f"Could not fetch average price for {symbol}: {error}", None

    # Calculate prices
    buy_price = round(
        avg * (1 + cfg["buy_offset"] / 100) if cfg["buy_is_percent"]
        else avg + cfg["buy_offset"],
        2,
    )
    sell_price = round(
        avg * (1 + cfg["sell_offset"] / 100) if cfg["sell_is_percent"]
        else avg + cfg["sell_offset"],
        2,
    )
    stop_price = round(
        buy_price * (1 + cfg.get("stop_offset", -10.0) / 100) if cfg.get("stop_is_percent", True)
        else buy_price + cfg.get("stop_offset", -5.0),
        2,
    )

    # Validate price logic
    if buy_price <= 0:
        return f"Invalid buy price calculated: ${buy_price}", None
    if sell_price <= buy_price:
        return f"Sell price (${sell_price}) must be higher than buy price (${buy_price})", None
    if stop_price >= buy_price:
        return f"Stop price (${stop_price}) must be lower than buy price (${buy_price})", None

    qty = int(effective_power // buy_price)
    if qty < 1:
        return f"Insufficient buying power for {symbol} (need ${buy_price:.2f}, have ${effective_power:.2f}).", None

    try:
        order_data = LimitOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.GTC,
            limit_price=buy_price,
            order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(limit_price=sell_price),
            stop_loss=StopLossRequest(stop_price=stop_price),
        )
        order = trading_client.submit_order(order_data=order_data)
        order_id = str(order.id)
        
        # Track the order for profit monitoring
        config.setdefault("tracked_orders", {})
        config["tracked_orders"][order_id] = {
            "symbol": symbol,
            "qty": qty,
            "buy_price": buy_price,
            "sell_price": sell_price,
            "stop_price": stop_price,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        save_config(config)
        
        # Log the trade
        add_trade_record(symbol, order_id, "BRACKET_PLACED", qty, buy_price)
        
        msg = (
            f"Bracket placed for {symbol} | Qty: {qty} "
            f"| Buy @ ${buy_price} | Sell @ ${sell_price} | Stop @ ${stop_price}"
        )
        logger.info(msg)
        return msg, order_id
        
    except Exception as e:
        error_msg = f"Order failed for {symbol}: {e}"
        logger.error(error_msg)
        return error_msg, None

# ─────────────────────────────────────────────────
# Automated Profit Tracking
# ─────────────────────────────────────────────────

def check_closed_orders_and_update_profits(trading_client, config: dict) -> List[str]:
    """
    Check for closed orders and automatically update profits
    Returns list of update messages
    """
    if not trading_client:
        return []
    
    messages = []
    tracked_orders = config.get("tracked_orders", {})
    orders_to_remove = []
    
    for order_id, order_info in tracked_orders.items():
        try:
            order = trading_client.get_order_by_id(order_id)
            symbol = order_info["symbol"]
            
            # Check if order is filled (buy executed)
            if order.status == OrderStatus.FILLED:
                # Check if position is now closed (profit taken or stopped out)
                has_pos, _ = has_open_position(symbol, trading_client)
                
                if not has_pos:
                    # Position closed - calculate profit
                    buy_price = order_info["buy_price"]
                    qty = order_info["qty"]
                    
                    # Try to get the exit price from closed orders
                    try:
                        closed_orders = trading_client.get_orders(
                            filter={"symbol": symbol, "status": "closed", "limit": 10}
                        )
                        
                        exit_price = None
                        for closed_order in closed_orders:
                            if closed_order.side == OrderSide.SELL and closed_order.filled_avg_price:
                                exit_price = float(closed_order.filled_avg_price)
                                break
                        
                        if exit_price:
                            profit = (exit_price - buy_price) * qty
                            config["profits"][symbol] = config["profits"].get(symbol, 0.0) + profit
                            
                            # Record the trade
                            add_trade_record(symbol, order_id, "CLOSED", qty, exit_price, profit)
                            
                            msg = f"{symbol}: Trade closed. Profit: ${profit:.2f}"
                            messages.append(msg)
                            logger.info(msg)
                        else:
                            # Couldn't determine exit price, mark for manual review
                            msg = f"{symbol}: Position closed but exit price unknown"
                            messages.append(msg)
                            logger.warning(msg)
                            
                    except Exception as e:
                        logger.error(f"Error getting exit price for {symbol}: {e}")
                    
                    orders_to_remove.append(order_id)
            
            # Check if order was cancelled
            elif order.status in [OrderStatus.CANCELED, OrderStatus.EXPIRED, OrderStatus.REJECTED]:
                orders_to_remove.append(order_id)
                logger.info(f"Order {order_id} for {symbol} was {order.status}")
                
        except Exception as e:
            logger.error(f"Error checking order {order_id}: {e}")
            # If order not found, remove from tracking
            if "not found" in str(e).lower():
                orders_to_remove.append(order_id)
    
    # Clean up tracked orders
    for order_id in orders_to_remove:
        config["tracked_orders"].pop(order_id, None)
    
    if orders_to_remove:
        save_config(config)
    
    return messages

def start_profit_monitor(trading_client, check_interval: int = 60):
    """Start background thread to monitor profits"""
    def monitor_loop():
        while True:
            try:
                config = load_config()
                messages = check_closed_orders_and_update_profits(trading_client, config)
                for msg in messages:
                    logger.info(f"[PROFIT MONITOR] {msg}")
            except Exception as e:
                logger.error(f"Profit monitor error: {e}")
            time.sleep(check_interval)
    
    thread = threading.Thread(target=monitor_loop, daemon=True)
    thread.start()
    logger.info(f"Profit monitor started (interval: {check_interval}s)")
    return thread

# ─────────────────────────────────────────────────
# Portfolio Analytics
# ─────────────────────────────────────────────────

def get_portfolio_summary(trading_client) -> Optional[dict]:
    """Get overall portfolio summary"""
    if not trading_client:
        return None
    
    try:
        account = trading_client.get_account()
        return {
            "equity": float(account.equity),
            "cash": float(account.cash),
            "buying_power": float(account.buying_power),
            "portfolio_value": float(account.portfolio_value),
            "day_pl": float(account.equity) - float(account.last_equity),
            "day_pl_pct": ((float(account.equity) / float(account.last_equity)) - 1) * 100 if float(account.last_equity) > 0 else 0
        }
    except Exception as e:
        logger.error(f"Error getting portfolio summary: {e}")
        return None

def get_all_positions(trading_client) -> List[dict]:
    """Get all open positions"""
    if not trading_client:
        return []
    
    try:
        positions = trading_client.get_all_positions()
        return [
            {
                "symbol": pos.symbol,
                "qty": int(pos.qty),
                "avg_entry": float(pos.avg_entry_price),
                "current_price": float(pos.current_price),
                "market_value": float(pos.market_value),
                "unrealized_pl": float(pos.unrealized_pl),
                "unrealized_plpc": float(pos.unrealized_plpc) * 100
            }
            for pos in positions
        ]
    except Exception as e:
        logger.error(f"Error getting positions: {e}")
        return []

# ─────────────────────────────────────────────────
# Page Config (must be first Streamlit call)
# ─────────────────────────────────────────────────

st.set_page_config(
    page_title="Bracket Bot Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .stMetric {
        background-color: #1e1e1e;
        padding: 15px;
        border-radius: 10px;
    }
    .profit-positive { color: #00ff88; }
    .profit-negative { color: #ff4444; }
    .status-badge {
        padding: 4px 12px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: bold;
    }
    .status-waiting { background-color: #ffc107; color: #000; }
    .status-in-trade { background-color: #28a745; color: #fff; }
    .status-pending { background-color: #17a2b8; color: #fff; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────
# Load config early so the sidebar form can read it
# ─────────────────────────────────────────────────

config = load_config()

# ─────────────────────────────────────────────────
# Sidebar — API keys & connection
# ─────────────────────────────────────────────────

st.sidebar.title("⚙️ Settings")

API_KEY = st.sidebar.text_input("Alpaca API Key", type="password", value=os.getenv("ALPACA_API_KEY", ""))
API_SECRET = st.sidebar.text_input("Alpaca API Secret", type="password", value=os.getenv("ALPACA_SECRET_KEY", ""))
PAPER_MODE = st.sidebar.checkbox("Paper Trading", value=True)

st.sidebar.divider()

TELEGRAM_TOKEN = st.sidebar.text_input("Telegram Bot Token (optional)", type="password", value=os.getenv("TELEGRAM_TOKEN", ""))
TELEGRAM_USER_ID = st.sidebar.number_input("Your Telegram User ID", min_value=0, value=int(os.getenv("TELEGRAM_USER_ID", "0")))

if not API_KEY or not API_SECRET:
    st.sidebar.warning("Enter Alpaca API keys to enable trading features.")
    trading_client = None
    data_client = None
else:
    try:
        trading_client = TradingClient(API_KEY, API_SECRET, paper=PAPER_MODE)
        data_client = StockHistoricalDataClient(API_KEY, API_SECRET)
        st.sidebar.success("✅ Alpaca connected")
        logger.info("Alpaca clients initialized successfully")
        
        # Start profit monitor if not already running
        if "profit_monitor_started" not in st.session_state:
            start_profit_monitor(trading_client)
            st.session_state["profit_monitor_started"] = True
            
    except Exception as e:
        st.sidebar.error(f"Connection failed: {e}")
        logger.error(f"Alpaca connection failed: {e}")
        trading_client = None
        data_client = None

# ─────────────────────────────────────────────────
# Sidebar — Add / Edit ticker form
# ─────────────────────────────────────────────────

st.sidebar.divider()
st.sidebar.header("➕ Add / Edit Ticker")

new_symbol = st.sidebar.text_input("Symbol", "").strip().upper()

if new_symbol:
    # Validate symbol input
    try:
        validated_symbol = validate_symbol(new_symbol)
        defaults = config["tickers"].get(validated_symbol, TICKER_DEFAULTS)

        buy_power = st.sidebar.number_input("Base Buy Power ($)", min_value=1.0, max_value=1000000.0, value=float(defaults["buy_power"]))
        avg_days = st.sidebar.number_input("Averaging Days (1–365)", 1, 365, int(defaults["avg_days"]))
        buy_offset = st.sidebar.number_input("Buy Offset", min_value=-50.0, max_value=50.0, value=float(defaults["buy_offset"]))
        buy_is_percent = st.sidebar.checkbox("Buy offset is %", value=bool(defaults["buy_is_percent"]))
        sell_offset = st.sidebar.number_input("Sell Offset", min_value=-50.0, max_value=100.0, value=float(defaults["sell_offset"]))
        sell_is_percent = st.sidebar.checkbox("Sell offset is %", value=bool(defaults["sell_is_percent"]))
        stop_offset = st.sidebar.number_input("Stop Offset", min_value=-50.0, max_value=50.0, value=float(defaults["stop_offset"]))
        stop_is_percent = st.sidebar.checkbox("Stop offset is %", value=bool(defaults["stop_is_percent"]))
        
        st.sidebar.divider()
        compound_enabled = st.sidebar.checkbox("Enable Compound Cap", value=bool(defaults.get("compound_enabled", False)))
        max_multiple = st.sidebar.number_input("Max Multiple of Base (e.g. 5×)", min_value=1.0, max_value=100.0, value=float(defaults.get("max_multiple", 5.0)))
        max_dollar_cap = st.sidebar.number_input("OR Max $ Cap (0 = unlimited)", min_value=0.0, max_value=10000000.0, value=float(defaults.get("max_dollar_cap", 10000.0)))

        btn_label = f"💾 Save {validated_symbol}" if validated_symbol in config["tickers"] else f"➕ Add {validated_symbol}"
        if st.sidebar.button(btn_label):
            try:
                # Validate all inputs
                validate_buy_power(buy_power)
                validate_avg_days(avg_days)
                validate_offset(buy_offset, "Buy offset")
                validate_offset(sell_offset, "Sell offset")
                validate_offset(stop_offset, "Stop offset")
                
                config["tickers"][validated_symbol] = {
                    "buy_power": buy_power,
                    "avg_days": avg_days,
                    "buy_offset": buy_offset,
                    "buy_is_percent": buy_is_percent,
                    "sell_offset": sell_offset,
                    "sell_is_percent": sell_is_percent,
                    "stop_offset": stop_offset,
                    "stop_is_percent": stop_is_percent,
                    "compound_enabled": compound_enabled,
                    "max_multiple": max_multiple,
                    "max_dollar_cap": max_dollar_cap,
                }
                config["profits"].setdefault(validated_symbol, 0.0)
                save_config(config)
                st.sidebar.success(f"✅ {validated_symbol} saved!")
                logger.info(f"Ticker {validated_symbol} saved/updated")
            except ValidationError as e:
                st.sidebar.error(f"❌ {e}")
                
    except ValidationError as e:
        st.sidebar.error(f"❌ Invalid symbol: {e}")

# Delete ticker button
st.sidebar.divider()
if config["tickers"]:
    delete_symbol = st.sidebar.selectbox("Remove Ticker", [""] + list(config["tickers"].keys()))
    if delete_symbol and st.sidebar.button(f"🗑️ Remove {delete_symbol}", type="secondary"):
        if st.session_state.get(f"confirm_delete_{delete_symbol}", False):
            config["tickers"].pop(delete_symbol, None)
            config["profits"].pop(delete_symbol, None)
            save_config(config)
            st.sidebar.success(f"✅ {delete_symbol} removed")
            logger.info(f"Ticker {delete_symbol} removed")
            st.session_state[f"confirm_delete_{delete_symbol}"] = False
            st.rerun()
        else:
            st.session_state[f"confirm_delete_{delete_symbol}"] = True
            st.sidebar.warning(f"Click again to confirm removal of {delete_symbol}")

# ─────────────────────────────────────────────────
# Main Dashboard
# ─────────────────────────────────────────────────

st.title("📈 Bracket Bot Dashboard")

# Pause banner
paused = os.path.exists(PAUSE_FILE)
if paused:
    st.error("🛑 BOT IS PAUSED — new brackets will not be placed.")
    if st.button("▶️ Resume Bot", type="primary"):
        os.remove(PAUSE_FILE)
        logger.info("Bot resumed")
        st.rerun()

# ─────────────────────────────────────────────────
# Portfolio Overview (if connected)
# ─────────────────────────────────────────────────

if trading_client:
    portfolio = get_portfolio_summary(trading_client)
    if portfolio:
        st.subheader("💼 Portfolio Overview")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Equity", f"${portfolio['equity']:,.2f}")
        with col2:
            st.metric("Cash", f"${portfolio['cash']:,.2f}")
        with col3:
            st.metric("Buying Power", f"${portfolio['buying_power']:,.2f}")
        with col4:
            day_pl_color = "normal" if portfolio['day_pl'] >= 0 else "inverse"
            st.metric("Day P/L", f"${portfolio['day_pl']:,.2f}", f"{portfolio['day_pl_pct']:.2f}%", delta_color=day_pl_color)
        
        st.divider()

# ─────────────────────────────────────────────────
# Tabs for different views
# ─────────────────────────────────────────────────

tab1, tab2, tab3, tab4 = st.tabs(["📊 Watchlist", "📈 Positions", "📜 Trade History", "📋 Logs"])

# ─────────────────────────────────────────────────
# Tab 1: Watchlist
# ─────────────────────────────────────────────────

with tab1:
    if not config["tickers"]:
        st.info("📝 Add tickers using the sidebar form to get started.")
    else:
        # Check for profit updates
        if trading_client and st.button("🔄 Check Closed Trades & Update Profits"):
            with st.spinner("Checking closed orders..."):
                messages = check_closed_orders_and_update_profits(trading_client, config)
                if messages:
                    for msg in messages:
                        st.success(msg)
                else:
                    st.info("No closed trades found since last check.")
                config = load_config()  # Reload after update
        
        data_rows = []
        total_profit = 0
        total_effective = 0
        
        for symbol, cfg in config["tickers"].items():
            profit = config["profits"].get(symbol, 0.0)
            total_profit += profit
            effective = calc_effective_power(cfg, profit)
            total_effective += effective
            
            avg, _ = get_avg_price(symbol, cfg["avg_days"], data_client)
            
            buy_price = avg * (1 + cfg["buy_offset"] / 100) if cfg["buy_is_percent"] else avg + cfg["buy_offset"]
            sell_price = avg * (1 + cfg["sell_offset"] / 100) if cfg["sell_is_percent"] else avg + cfg["sell_offset"]
            stop_price = buy_price * (1 + cfg.get("stop_offset", -10) / 100) if cfg.get("stop_is_percent", True) else buy_price + cfg.get("stop_offset", -5)
            
            has_pos, pos_info = has_open_position(symbol, trading_client)
            open_orders = get_open_orders(symbol, trading_client)
            
            if has_pos:
                status = "In-trade"
            elif open_orders:
                status = "Pending"
            else:
                status = "Waiting"

            data_rows.append({
                "Symbol": symbol,
                "Status": status,
                "Base ($)": f"${cfg['buy_power']:.0f}",
                "Profit ($)": f"${profit:.2f}",
                "Effective ($)": f"${effective:.2f}",
                "Avg Days": cfg["avg_days"],
                "Buy Level": f"${buy_price:.2f}" if avg > 0 else "—",
                "Sell Level": f"${sell_price:.2f}" if avg > 0 else "—",
                "Stop Level": f"${stop_price:.2f}" if avg > 0 else "—",
                "Open Orders": len(open_orders),
            })

        # Summary metrics
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Tickers", len(config["tickers"]))
        with col2:
            profit_delta = "+" if total_profit >= 0 else ""
            st.metric("Total Profits", f"${total_profit:.2f}")
        with col3:
            st.metric("Total Effective Power", f"${total_effective:.2f}")
        
        st.divider()
        
        # Main watchlist table
        st.dataframe(
            pd.DataFrame(data_rows),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Status": st.column_config.TextColumn(width="small"),
                "Symbol": st.column_config.TextColumn(width="small"),
            }
        )

        # Individual ticker controls
        st.subheader("🎮 Ticker Controls")
        
        for symbol, cfg in config["tickers"].items():
            profit = config["profits"].get(symbol, 0.0)
            effective = calc_effective_power(cfg, profit)
            
            with st.expander(f"**{symbol}** — Effective: ${effective:.2f} | Profit: ${profit:.2f}"):
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    if st.button("📈 Place Bracket", key=f"buy_{symbol}"):
                        if paused:
                            st.error("Bot is paused")
                        elif not trading_client:
                            st.error("Not connected to Alpaca")
                        else:
                            has_pos, _ = has_open_position(symbol, trading_client)
                            if has_pos:
                                st.warning(f"Already in position for {symbol}")
                            else:
                                msg, order_id = place_bracket(symbol, cfg, effective, trading_client, data_client, config)
                                if order_id:
                                    st.success(msg)
                                else:
                                    st.error(msg)
                
                with col2:
                    if st.button("❌ Cancel Orders", key=f"cancel_{symbol}"):
                        cancelled, errors = cancel_orders(symbol, trading_client)
                        if cancelled > 0:
                            st.success(f"Cancelled {cancelled} order(s) for {symbol}")
                        elif errors:
                            for err in errors:
                                st.error(err)
                        else:
                            st.info(f"No open orders to cancel for {symbol}")
                
                with col3:
                    if st.button("🔄 Reset Profits", key=f"reset_{symbol}"):
                        if st.session_state.get(f"confirm_reset_{symbol}", False):
                            config["profits"][symbol] = 0.0
                            save_config(config)
                            st.success(f"Profits reset for {symbol}")
                            logger.info(f"Profits reset for {symbol}")
                            st.session_state[f"confirm_reset_{symbol}"] = False
                            st.rerun()
                        else:
                            st.session_state[f"confirm_reset_{symbol}"] = True
                            st.warning("Click again to confirm reset")
                
                with col4:
                    # Show position info if in trade
                    has_pos, pos_info = has_open_position(symbol, trading_client)
                    if has_pos and pos_info:
                        pl_color = "green" if pos_info['unrealized_pl'] >= 0 else "red"
                        st.markdown(f"""
                        **Position:** {pos_info['qty']} shares  
                        **Entry:** ${pos_info['avg_entry']:.2f}  
                        **Current:** ${pos_info['current_price']:.2f}  
                        **P/L:** <span style='color:{pl_color}'>${pos_info['unrealized_pl']:.2f} ({pos_info['unrealized_plpc']:.2f}%)</span>
                        """, unsafe_allow_html=True)

# ─────────────────────────────────────────────────
# Tab 2: Positions
# ─────────────────────────────────────────────────

with tab2:
    if trading_client:
        positions = get_all_positions(trading_client)
        if positions:
            st.subheader(f"📈 Open Positions ({len(positions)})")
            
            positions_df = pd.DataFrame(positions)
            st.dataframe(
                positions_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "unrealized_pl": st.column_config.NumberColumn("P/L ($)", format="$%.2f"),
                    "unrealized_plpc": st.column_config.NumberColumn("P/L (%)", format="%.2f%%"),
                    "market_value": st.column_config.NumberColumn("Value", format="$%.2f"),
                }
            )
        else:
            st.info("No open positions")
    else:
        st.warning("Connect to Alpaca to view positions")

# ─────────────────────────────────────────────────
# Tab 3: Trade History
# ─────────────────────────────────────────────────

with tab3:
    history = load_trade_history()
    if history:
        st.subheader(f"📜 Trade History (Last {len(history)} trades)")
        
        history_df = pd.DataFrame(history)
        history_df = history_df.sort_values("timestamp", ascending=False)
        
        st.dataframe(
            history_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "profit": st.column_config.NumberColumn("Profit", format="$%.2f"),
                "price": st.column_config.NumberColumn("Price", format="$%.2f"),
            }
        )
        
        # Summary stats
        if len(history) > 0:
            total_trades = len([h for h in history if h.get("action") == "CLOSED"])
            winning_trades = len([h for h in history if h.get("action") == "CLOSED" and h.get("profit", 0) > 0])
            total_pnl = sum(h.get("profit", 0) for h in history if h.get("action") == "CLOSED")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Closed Trades", total_trades)
            with col2:
                win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
                st.metric("Win Rate", f"{win_rate:.1f}%")
            with col3:
                st.metric("Total P/L", f"${total_pnl:.2f}")
    else:
        st.info("No trade history yet")

# ─────────────────────────────────────────────────
# Tab 4: Logs
# ─────────────────────────────────────────────────

with tab4:
    st.subheader("📋 Application Logs")
    
    if os.path.exists(LOG_FILE):
        col1, col2 = st.columns([3, 1])
        with col1:
            log_lines = st.slider("Number of log lines", 10, 500, 50)
        with col2:
            if st.button("🔄 Refresh Logs"):
                st.rerun()
        
        try:
            with open(LOG_FILE, "r") as f:
                lines = f.readlines()
                recent_logs = lines[-log_lines:] if len(lines) > log_lines else lines
                st.code("".join(recent_logs), language="log")
        except Exception as e:
            st.error(f"Error reading logs: {e}")
        
        if st.button("🗑️ Clear Logs"):
            try:
                open(LOG_FILE, "w").close()
                st.success("Logs cleared")
            except Exception as e:
                st.error(f"Error clearing logs: {e}")
    else:
        st.info("No logs available yet")

# ─────────────────────────────────────────────────
# Global Actions
# ─────────────────────────────────────────────────

st.divider()
st.subheader("🎯 Global Actions")

col_a, col_b, col_c, col_d = st.columns(4)

with col_a:
    if st.button("📈 Place All Brackets", type="primary", use_container_width=True):
        if paused:
            st.error("Bot is paused.")
        elif not trading_client:
            st.error("Alpaca not connected.")
        else:
            results = []
            for symbol, cfg in config["tickers"].items():
                has_pos, _ = has_open_position(symbol, trading_client)
                if has_pos:
                    results.append(f"⏭️ {symbol}: already in position — skipped.")
                    continue
                profit = config["profits"].get(symbol, 0.0)
                effective = calc_effective_power(cfg, profit)
                msg, order_id = place_bracket(symbol, cfg, effective, trading_client, data_client, config)
                emoji = "✅" if order_id else "❌"
                results.append(f"{emoji} {symbol}: {msg}")
            
            for result in results:
                st.write(result)

with col_b:
    if st.button("❌ Cancel All Orders", type="secondary", use_container_width=True):
        if st.session_state.get("confirm_cancel_all", False):
            cancelled, errors = cancel_all_orders(trading_client)
            if cancelled != 0:
                st.success("All orders cancelled")
                logger.info("All orders cancelled by user")
            for err in errors:
                st.error(err)
            st.session_state["confirm_cancel_all"] = False
            st.rerun()
        else:
            st.session_state["confirm_cancel_all"] = True
            st.warning("⚠️ Click again to confirm cancelling ALL orders")

with col_c:
    if st.button("⏸️ Pause Bot", use_container_width=True):
        open(PAUSE_FILE, "w").close()
        logger.info("Bot paused by user")
        st.rerun()

with col_d:
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.rerun()

# ─────────────────────────────────────────────────
# Telegram Remote Control (background thread)
# ─────────────────────────────────────────────────

if TELEGRAM_TOKEN and int(TELEGRAM_USER_ID) > 0:
    if "telegram_started" not in st.session_state:
        try:
            bot = telebot.TeleBot(TELEGRAM_TOKEN)
            UID = int(TELEGRAM_USER_ID)

            def _guard(message) -> bool:
                return message.from_user.id == UID

            @bot.message_handler(commands=["start", "help"])
            def tg_start(message):
                if not _guard(message):
                    return
                help_text = """
🤖 *Bracket Bot Remote Control*

*Commands:*
/status - View all tickers status
/portfolio - View portfolio summary
/buy SYMBOL - Place bracket for symbol
/cancel SYMBOL - Cancel orders for symbol
/cancelall - Cancel ALL orders
/stop - Pause the bot
/restart - Resume the bot
/reset SYMBOL - Reset profits for symbol
/add SYMBOL buy_power avg_days buy_offset buy_% sell_offset sell_%
/history - View recent trades
                """
                bot.reply_to(message, help_text, parse_mode="Markdown")

            @bot.message_handler(commands=["status"])
            def tg_status(message):
                if not _guard(message):
                    return
                cfg_data = load_config()
                lines = ["📊 *Current Tickers:*\n"]
                for sym, cfg in cfg_data["tickers"].items():
                    profit = cfg_data["profits"].get(sym, 0.0)
                    eff = calc_effective_power(cfg, profit)
                    has_pos, _ = has_open_position(sym, trading_client)
                    state = "🟢 In-trade" if has_pos else "🟡 Waiting"
                    lines.append(f"*{sym}* | Eff: ${eff:.2f} | Profit: ${profit:.2f} | {state}")
                bot.reply_to(message, "\n".join(lines) or "No tickers configured.", parse_mode="Markdown")

            @bot.message_handler(commands=["portfolio"])
            def tg_portfolio(message):
                if not _guard(message):
                    return
                portfolio = get_portfolio_summary(trading_client)
                if portfolio:
                    text = f"""
💼 *Portfolio Summary*

Equity: ${portfolio['equity']:,.2f}
Cash: ${portfolio['cash']:,.2f}
Buying Power: ${portfolio['buying_power']:,.2f}
Day P/L: ${portfolio['day_pl']:,.2f} ({portfolio['day_pl_pct']:.2f}%)
                    """
                    bot.reply_to(message, text, parse_mode="Markdown")
                else:
                    bot.reply_to(message, "❌ Could not fetch portfolio data")

            @bot.message_handler(commands=["stop"])
            def tg_stop(message):
                if not _guard(message):
                    return
                open(PAUSE_FILE, "w").close()
                logger.info("Bot paused via Telegram")
                bot.reply_to(message, "⏸️ Bot paused. No new brackets will be placed.")

            @bot.message_handler(commands=["restart"])
            def tg_restart(message):
                if not _guard(message):
                    return
                if os.path.exists(PAUSE_FILE):
                    os.remove(PAUSE_FILE)
                    logger.info("Bot resumed via Telegram")
                bot.reply_to(message, "▶️ Bot resumed.")

            @bot.message_handler(commands=["cancel"])
            def tg_cancel(message):
                if not _guard(message):
                    return
                try:
                    parts = message.text.split(maxsplit=1)
                    if len(parts) < 2:
                        bot.reply_to(message, "Usage: /cancel SYMBOL")
                        return
                    sym = validate_symbol(parts[1])
                    cancelled, errors = cancel_orders(sym, trading_client)
                    if cancelled > 0:
                        bot.reply_to(message, f"✅ Cancelled {cancelled} order(s) for {sym}")
                    elif errors:
                        bot.reply_to(message, f"❌ Errors: {', '.join(errors)}")
                    else:
                        bot.reply_to(message, f"ℹ️ No open orders for {sym}")
                except ValidationError as e:
                    bot.reply_to(message, f"❌ {e}")
                except Exception as e:
                    bot.reply_to(message, f"❌ Error: {e}")

            @bot.message_handler(commands=["cancelall"])
            def tg_cancel_all(message):
                if not _guard(message):
                    return
                cancelled, errors = cancel_all_orders(trading_client)
                if cancelled != 0:
                    bot.reply_to(message, "✅ All orders cancelled")
                    logger.info("All orders cancelled via Telegram")
                elif errors:
                    bot.reply_to(message, f"❌ Errors: {', '.join(errors)}")

            @bot.message_handler(commands=["add"])
            def tg_add(message):
                if not _guard(message):
                    return
                try:
                    parts = message.text.split()[1:]
                    if len(parts) < 7:
                        bot.reply_to(
                            message,
                            "Usage: /add SYMBOL buy_power avg_days buy_offset buy_% sell_offset sell_%\n\n"
                            "Example: /add AAPL 500 30 -3 true 5 true",
                        )
                        return
                    
                    sym = validate_symbol(parts[0])
                    buy_power = validate_buy_power(float(parts[1]))
                    avg_days = validate_avg_days(int(parts[2]))
                    buy_offset = validate_offset(float(parts[3]), "Buy offset")
                    sell_offset = validate_offset(float(parts[5]), "Sell offset")
                    
                    cfg_data = load_config()
                    cfg_data["tickers"][sym] = {
                        "buy_power": buy_power,
                        "avg_days": avg_days,
                        "buy_offset": buy_offset,
                        "buy_is_percent": parts[4].lower() in ["true", "1", "yes", "%"],
                        "sell_offset": sell_offset,
                        "sell_is_percent": parts[6].lower() in ["true", "1", "yes", "%"],
                        "stop_offset": float(parts[7]) if len(parts) > 7 else -6.0,
                        "stop_is_percent": parts[8].lower() in ["true", "1", "yes", "%"] if len(parts) > 8 else True,
                        "compound_enabled": False,
                        "max_multiple": 5.0,
                        "max_dollar_cap": 10000.0,
                    }
                    cfg_data["profits"].setdefault(sym, 0.0)
                    save_config(cfg_data)
                    logger.info(f"Ticker {sym} added via Telegram")
                    bot.reply_to(message, f"✅ Added/updated {sym}")
                except ValidationError as e:
                    bot.reply_to(message, f"❌ Validation error: {e}")
                except (ValueError, IndexError) as e:
                    bot.reply_to(message, f"❌ Invalid input: {e}")
                except Exception as e:
                    bot.reply_to(message, f"❌ Error: {e}")

            @bot.message_handler(commands=["buy"])
            def tg_buy(message):
                if not _guard(message):
                    return
                try:
                    parts = message.text.split(maxsplit=1)
                    if len(parts) < 2:
                        bot.reply_to(message, "Usage: /buy SYMBOL")
                        return
                    
                    sym = validate_symbol(parts[1])
                    cfg_data = load_config()
                    
                    if sym not in cfg_data["tickers"]:
                        bot.reply_to(message, f"❌ {sym} not found in configuration")
                        return
                    
                    if os.path.exists(PAUSE_FILE):
                        bot.reply_to(message, "⏸️ Bot is paused. Use /restart first.")
                        return
                    
                    has_pos, _ = has_open_position(sym, trading_client)
                    if has_pos:
                        bot.reply_to(message, f"⚠️ Already in position for {sym}")
                        return
                    
                    cfg = cfg_data["tickers"][sym]
                    profit = cfg_data["profits"].get(sym, 0.0)
                    effective = calc_effective_power(cfg, profit)
                    msg, order_id = place_bracket(sym, cfg, effective, trading_client, data_client, cfg_data)
                    
                    emoji = "✅" if order_id else "❌"
                    bot.reply_to(message, f"{emoji} {msg}")
                    
                except ValidationError as e:
                    bot.reply_to(message, f"❌ {e}")
                except Exception as e:
                    bot.reply_to(message, f"❌ Error: {e}")

            @bot.message_handler(commands=["reset"])
            def tg_reset(message):
                if not _guard(message):
                    return
                try:
                    parts = message.text.split(maxsplit=1)
                    if len(parts) < 2:
                        bot.reply_to(message, "Usage: /reset SYMBOL")
                        return
                    
                    sym = validate_symbol(parts[1])
                    cfg_data = load_config()
                    
                    if sym not in cfg_data["profits"]:
                        bot.reply_to(message, f"❌ {sym} not found")
                        return
                    
                    cfg_data["profits"][sym] = 0.0
                    save_config(cfg_data)
                    logger.info(f"Profits reset for {sym} via Telegram")
                    bot.reply_to(message, f"✅ Profits reset for {sym}")
                    
                except ValidationError as e:
                    bot.reply_to(message, f"❌ {e}")
                except Exception as e:
                    bot.reply_to(message, f"❌ Error: {e}")

            @bot.message_handler(commands=["history"])
            def tg_history(message):
                if not _guard(message):
                    return
                history = load_trade_history()
                if not history:
                    bot.reply_to(message, "📜 No trade history yet")
                    return
                
                # Get last 10 trades
                recent = history[-10:]
                lines = ["📜 *Recent Trades:*\n"]
                for trade in reversed(recent):
                    ts = trade.get("timestamp", "")[:10]
                    sym = trade.get("symbol", "")
                    action = trade.get("action", "")
                    profit = trade.get("profit", 0)
                    lines.append(f"{ts} | {sym} | {action} | P/L: ${profit:.2f}")
                
                bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")

            # Start polling in background thread
            threading.Thread(
                target=lambda: bot.infinity_polling(timeout=10, long_polling_timeout=5),
                daemon=True,
            ).start()

            st.session_state["telegram_started"] = True
            st.sidebar.success("✅ Telegram remote control ACTIVE")
            logger.info("Telegram bot started successfully")

        except Exception as e:
            st.sidebar.error(f"Telegram setup failed: {e}")
            logger.error(f"Telegram setup failed: {e}")
    else:
        st.sidebar.info("✅ Telegram running")

# ─────────────────────────────────────────────────
# Footer
# ─────────────────────────────────────────────────

st.divider()
st.caption(f"📊 Bracket Bot Dashboard v2.0 | Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Mode: {'📝 Paper' if PAPER_MODE else '💰 Live'}")
