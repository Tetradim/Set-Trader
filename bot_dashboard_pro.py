# bot_dashboard_pro.py
# Run with: streamlit run bot_dashboard_pro.py
# Enhanced Pro Version with Scheduling, Risk Management, Alerts, and Analytics

import json
import os
import threading
import logging
import time
import statistics
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List, Tuple, Callable
from dataclasses import dataclass, asdict, field
from enum import Enum
from collections import defaultdict
import hashlib
import csv
import io

import pandas as pd
import streamlit as st
import telebot
from jsonschema import validate, ValidationError as JsonValidationError
from alpaca.data import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce, OrderStatus
from alpaca.trading.requests import (
    LimitOrderRequest, StopLossRequest, TakeProfitRequest,
    MarketOrderRequest, StopOrderRequest, TrailingStopOrderRequest
)

# ─────────────────────────────────────────────────
# Logging Setup
# ─────────────────────────────────────────────────

LOG_FILE = "bot_dashboard.log"
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

logger = logging.getLogger("BracketBotPro")
logger.setLevel(logging.DEBUG)

file_handler = logging.FileHandler(LOG_FILE, mode='a')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))

if not logger.handlers:
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

# ─────────────────────────────────────────────────
# Constants & Enums
# ─────────────────────────────────────────────────

CONFIG_FILE = "ticker_config.json"
PAUSE_FILE = "pause.flag"
TRADES_HISTORY_FILE = "trades_history.json"
ALERTS_FILE = "price_alerts.json"
SCHEDULES_FILE = "schedules.json"
RISK_SETTINGS_FILE = "risk_settings.json"
ANALYTICS_FILE = "analytics_data.json"

class TradeStatus(Enum):
    WAITING = "Waiting"
    IN_TRADE = "In-trade"
    PENDING_ORDER = "Pending"
    FILLED = "Filled"

class OrderType(Enum):
    BRACKET = "bracket"
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    TRAILING_STOP = "trailing_stop"

class AlertCondition(Enum):
    ABOVE = "above"
    BELOW = "below"
    CROSSES_ABOVE = "crosses_above"
    CROSSES_BELOW = "crosses_below"
    PERCENT_CHANGE = "percent_change"

class ScheduleFrequency(Enum):
    ONCE = "once"
    DAILY = "daily"
    WEEKLY = "weekly"
    MARKET_OPEN = "market_open"
    MARKET_CLOSE = "market_close"

# Market hours (EST)
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 30
MARKET_CLOSE_HOUR = 16
MARKET_CLOSE_MINUTE = 0

# ─────────────────────────────────────────────────
# Configuration Schemas
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
        "strategy": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "notes": {"type": "string"},
        "enabled": {"type": "boolean"},
        "trailing_stop_percent": {"type": "number", "minimum": 0.1, "maximum": 50},
    },
    "required": ["buy_power", "avg_days", "buy_offset", "buy_is_percent", 
                 "sell_offset", "sell_is_percent", "stop_offset", "stop_is_percent"],
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
    "strategy": "bracket",
    "tags": [],
    "notes": "",
    "enabled": True,
    "trailing_stop_percent": 5.0,
}

RISK_DEFAULTS = {
    "max_daily_loss": 500.0,
    "max_daily_loss_percent": 5.0,
    "max_position_size": 5000.0,
    "max_positions": 10,
    "max_single_trade_risk": 100.0,
    "daily_trade_limit": 50,
    "require_confirmation_above": 1000.0,
    "enabled": True,
    "pause_on_daily_loss": True,
    # Price deviation limits - deny if buy price too far from current price
    "max_price_deviation_percent": 10.0,  # Max % difference from current price
    "max_price_deviation_dollar": 0.0,    # Max $ difference (0 = disabled)
    "price_deviation_check_enabled": True,
}

# ─────────────────────────────────────────────────
# Validation Helpers
# ─────────────────────────────────────────────────

class ValidationError(Exception):
    pass

def validate_symbol(symbol: str) -> str:
    if not symbol:
        raise ValidationError("Symbol cannot be empty")
    symbol = symbol.strip().upper()
    if not symbol.replace(".", "").isalpha():
        raise ValidationError(f"Invalid symbol '{symbol}'")
    if len(symbol) > 5:
        raise ValidationError(f"Symbol too long: '{symbol}'")
    return symbol

def validate_buy_power(value: float) -> float:
    if value < 1:
        raise ValidationError("Buy power must be at least $1")
    if value > 1000000:
        raise ValidationError("Buy power cannot exceed $1,000,000")
    return float(value)

def validate_avg_days(value: int) -> int:
    if value < 1 or value > 365:
        raise ValidationError("Averaging days must be 1-365")
    return int(value)

def validate_offset(value: float, name: str, min_val: float = -50, max_val: float = 100) -> float:
    if value < min_val or value > max_val:
        raise ValidationError(f"{name} must be between {min_val} and {max_val}")
    return float(value)

# ─────────────────────────────────────────────────
# File Persistence Helpers
# ─────────────────────────────────────────────────

def load_json_file(filepath: str, default: Any = None) -> Any:
    if default is None:
        default = {}
    if not os.path.exists(filepath):
        return default
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load {filepath}: {e}")
        return default

def save_json_file(filepath: str, data: Any) -> bool:
    try:
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, default=str)
        return True
    except Exception as e:
        logger.error(f"Failed to save {filepath}: {e}")
        return False

def load_config() -> dict:
    default = {"tickers": {}, "profits": {}, "tracked_orders": {}}
    data = load_json_file(CONFIG_FILE, default)
    data.setdefault("profits", {})
    data.setdefault("tickers", {})
    data.setdefault("tracked_orders", {})
    return data

def save_config(config: dict) -> bool:
    return save_json_file(CONFIG_FILE, config)

def load_risk_settings() -> dict:
    return load_json_file(RISK_SETTINGS_FILE, RISK_DEFAULTS.copy())

def save_risk_settings(settings: dict) -> bool:
    return save_json_file(RISK_SETTINGS_FILE, settings)

def load_alerts() -> List[dict]:
    return load_json_file(ALERTS_FILE, [])

def save_alerts(alerts: List[dict]) -> bool:
    return save_json_file(ALERTS_FILE, alerts)

def load_schedules() -> List[dict]:
    return load_json_file(SCHEDULES_FILE, [])

def save_schedules(schedules: List[dict]) -> bool:
    return save_json_file(SCHEDULES_FILE, schedules)

def load_trade_history() -> List[dict]:
    return load_json_file(TRADES_HISTORY_FILE, [])

def save_trade_history(history: List[dict]) -> bool:
    return save_json_file(TRADES_HISTORY_FILE, history[-1000:])

def load_analytics() -> dict:
    default = {"daily_pnl": {}, "trade_stats": {}, "performance_metrics": {}}
    return load_json_file(ANALYTICS_FILE, default)

def save_analytics(data: dict) -> bool:
    return save_json_file(ANALYTICS_FILE, data)

# ─────────────────────────────────────────────────
# Market Hours Helpers
# ─────────────────────────────────────────────────

def is_market_open() -> bool:
    """Check if US market is currently open (simplified)"""
    now = datetime.now()
    # Check weekday (0=Monday, 6=Sunday)
    if now.weekday() >= 5:
        return False
    
    market_open = now.replace(hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MINUTE, second=0)
    market_close = now.replace(hour=MARKET_CLOSE_HOUR, minute=MARKET_CLOSE_MINUTE, second=0)
    
    return market_open <= now <= market_close

def get_next_market_open() -> datetime:
    """Get next market open time"""
    now = datetime.now()
    next_open = now.replace(hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MINUTE, second=0, microsecond=0)
    
    if now >= next_open:
        next_open += timedelta(days=1)
    
    # Skip weekends
    while next_open.weekday() >= 5:
        next_open += timedelta(days=1)
    
    return next_open

def time_until_market_open() -> timedelta:
    """Time until next market open"""
    return get_next_market_open() - datetime.now()

# ─────────────────────────────────────────────────
# Risk Management
# ─────────────────────────────────────────────────

class RiskManager:
    def __init__(self, settings: dict):
        self.settings = settings
        self.daily_trades = 0
        self.daily_pnl = 0.0
        self.last_reset_date = datetime.now().date()
    
    def reset_daily_counters(self):
        today = datetime.now().date()
        if today > self.last_reset_date:
            self.daily_trades = 0
            self.daily_pnl = 0.0
            self.last_reset_date = today
            logger.info("Daily risk counters reset")
    
    def can_trade(self, trade_value: float, symbol: str = "") -> Tuple[bool, str]:
        """Check if trade is allowed based on risk settings"""
        if not self.settings.get("enabled", True):
            return True, ""
        
        self.reset_daily_counters()
        
        # Check daily trade limit
        if self.daily_trades >= self.settings.get("daily_trade_limit", 50):
            return False, "Daily trade limit reached"
        
        # Check max position size
        if trade_value > self.settings.get("max_position_size", 5000):
            return False, f"Trade exceeds max position size (${self.settings['max_position_size']})"
        
        # Check daily loss limit
        max_daily_loss = self.settings.get("max_daily_loss", 500)
        if self.daily_pnl < -max_daily_loss:
            if self.settings.get("pause_on_daily_loss", True):
                return False, f"Daily loss limit reached (${max_daily_loss})"
        
        return True, ""
    
    def check_price_deviation(self, buy_price: float, current_price: float, symbol: str = "") -> Tuple[bool, str]:
        """
        Check if buy price deviates too much from current market price.
        Returns (is_allowed, reason) - False means order should be denied.
        """
        if not self.settings.get("enabled", True):
            return True, ""
        
        if not self.settings.get("price_deviation_check_enabled", True):
            return True, ""
        
        if current_price <= 0 or buy_price <= 0:
            return True, ""  # Can't check without valid prices
        
        # Calculate deviation
        price_diff = abs(buy_price - current_price)
        percent_diff = (price_diff / current_price) * 100
        
        # Check percent deviation
        max_percent = self.settings.get("max_price_deviation_percent", 10.0)
        if max_percent > 0 and percent_diff > max_percent:
            return False, (
                f"Price deviation too high: Buy ${buy_price:.2f} vs Current ${current_price:.2f} "
                f"({percent_diff:.1f}% > {max_percent}% limit)"
            )
        
        # Check dollar deviation
        max_dollar = self.settings.get("max_price_deviation_dollar", 0.0)
        if max_dollar > 0 and price_diff > max_dollar:
            return False, (
                f"Price deviation too high: Buy ${buy_price:.2f} vs Current ${current_price:.2f} "
                f"(${price_diff:.2f} > ${max_dollar:.2f} limit)"
            )
        
        return True, ""
    
    def record_trade(self, pnl: float = 0.0):
        self.daily_trades += 1
        self.daily_pnl += pnl
    
    def get_status(self) -> dict:
        self.reset_daily_counters()
        return {
            "daily_trades": self.daily_trades,
            "daily_trade_limit": self.settings.get("daily_trade_limit", 50),
            "daily_pnl": self.daily_pnl,
            "max_daily_loss": self.settings.get("max_daily_loss", 500),
            "risk_enabled": self.settings.get("enabled", True),
        }

# Global risk manager instance
risk_settings = load_risk_settings()
risk_manager = RiskManager(risk_settings)

# ─────────────────────────────────────────────────
# Price Alerts System
# ─────────────────────────────────────────────────

class AlertManager:
    def __init__(self):
        self.alerts = load_alerts()
        self.last_prices = {}
        self.triggered_alerts = []
    
    def add_alert(self, symbol: str, condition: str, price: float, 
                  message: str = "", notify_telegram: bool = True) -> str:
        alert_id = hashlib.md5(f"{symbol}{condition}{price}{time.time()}".encode()).hexdigest()[:8]
        
        alert = {
            "id": alert_id,
            "symbol": validate_symbol(symbol),
            "condition": condition,
            "target_price": price,
            "message": message or f"{symbol} {condition} ${price}",
            "notify_telegram": notify_telegram,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "triggered": False,
            "triggered_at": None,
        }
        
        self.alerts.append(alert)
        save_alerts(self.alerts)
        logger.info(f"Alert created: {alert_id} - {symbol} {condition} ${price}")
        return alert_id
    
    def remove_alert(self, alert_id: str) -> bool:
        self.alerts = [a for a in self.alerts if a["id"] != alert_id]
        save_alerts(self.alerts)
        return True
    
    def check_alerts(self, data_client) -> List[dict]:
        """Check all alerts against current prices"""
        triggered = []
        
        for alert in self.alerts:
            if alert.get("triggered"):
                continue
            
            symbol = alert["symbol"]
            try:
                quote = data_client.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=symbol))
                if symbol in quote:
                    current_price = float(quote[symbol].ask_price)
                    last_price = self.last_prices.get(symbol, current_price)
                    
                    condition = alert["condition"]
                    target = alert["target_price"]
                    
                    is_triggered = False
                    
                    if condition == "above" and current_price >= target:
                        is_triggered = True
                    elif condition == "below" and current_price <= target:
                        is_triggered = True
                    elif condition == "crosses_above" and last_price < target <= current_price:
                        is_triggered = True
                    elif condition == "crosses_below" and last_price > target >= current_price:
                        is_triggered = True
                    
                    if is_triggered:
                        alert["triggered"] = True
                        alert["triggered_at"] = datetime.now(timezone.utc).isoformat()
                        alert["triggered_price"] = current_price
                        triggered.append(alert)
                        logger.info(f"Alert triggered: {alert['id']} - {alert['message']}")
                    
                    self.last_prices[symbol] = current_price
                    
            except Exception as e:
                logger.error(f"Error checking alert for {symbol}: {e}")
        
        if triggered:
            save_alerts(self.alerts)
        
        return triggered
    
    def get_active_alerts(self) -> List[dict]:
        return [a for a in self.alerts if not a.get("triggered")]
    
    def get_triggered_alerts(self) -> List[dict]:
        return [a for a in self.alerts if a.get("triggered")]

# ─────────────────────────────────────────────────
# Scheduling System
# ─────────────────────────────────────────────────

class ScheduleManager:
    def __init__(self):
        self.schedules = load_schedules()
    
    def add_schedule(self, symbol: str, action: str, frequency: str,
                     time_str: str = "", params: dict = None) -> str:
        schedule_id = hashlib.md5(f"{symbol}{action}{frequency}{time.time()}".encode()).hexdigest()[:8]
        
        schedule = {
            "id": schedule_id,
            "symbol": validate_symbol(symbol),
            "action": action,  # "place_bracket", "cancel_orders", "check_position"
            "frequency": frequency,
            "time": time_str,  # "09:35" or empty for market_open/close
            "params": params or {},
            "enabled": True,
            "last_run": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        
        self.schedules.append(schedule)
        save_schedules(self.schedules)
        logger.info(f"Schedule created: {schedule_id} - {symbol} {action} {frequency}")
        return schedule_id
    
    def remove_schedule(self, schedule_id: str) -> bool:
        self.schedules = [s for s in self.schedules if s["id"] != schedule_id]
        save_schedules(self.schedules)
        return True
    
    def toggle_schedule(self, schedule_id: str) -> bool:
        for schedule in self.schedules:
            if schedule["id"] == schedule_id:
                schedule["enabled"] = not schedule["enabled"]
                save_schedules(self.schedules)
                return schedule["enabled"]
        return False
    
    def get_due_schedules(self) -> List[dict]:
        """Get schedules that should run now"""
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        due = []
        
        for schedule in self.schedules:
            if not schedule.get("enabled", True):
                continue
            
            last_run = schedule.get("last_run")
            if last_run:
                last_run_dt = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
                # Prevent running more than once per minute
                if (now - last_run_dt.replace(tzinfo=None)).total_seconds() < 60:
                    continue
            
            frequency = schedule["frequency"]
            should_run = False
            
            if frequency == "market_open":
                # Run at market open (9:30 AM)
                if current_time == f"{MARKET_OPEN_HOUR:02d}:{MARKET_OPEN_MINUTE:02d}":
                    should_run = True
            elif frequency == "market_close":
                # Run near market close (3:55 PM)
                if current_time == "15:55":
                    should_run = True
            elif frequency == "daily":
                target_time = schedule.get("time", "09:35")
                if current_time == target_time:
                    should_run = True
            elif frequency == "once":
                target_time = schedule.get("time", "")
                if target_time and current_time == target_time and not last_run:
                    should_run = True
            
            if should_run:
                due.append(schedule)
        
        return due
    
    def mark_run(self, schedule_id: str):
        for schedule in self.schedules:
            if schedule["id"] == schedule_id:
                schedule["last_run"] = datetime.now(timezone.utc).isoformat()
                save_schedules(self.schedules)
                break

# ─────────────────────────────────────────────────
# Analytics & Performance Tracking
# ─────────────────────────────────────────────────

class AnalyticsManager:
    def __init__(self):
        self.data = load_analytics()
    
    def record_trade(self, symbol: str, pnl: float, trade_type: str):
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Daily P&L
        if today not in self.data["daily_pnl"]:
            self.data["daily_pnl"][today] = 0.0
        self.data["daily_pnl"][today] += pnl
        
        # Per-symbol stats
        if symbol not in self.data["trade_stats"]:
            self.data["trade_stats"][symbol] = {
                "total_trades": 0, "wins": 0, "losses": 0,
                "total_pnl": 0.0, "best_trade": 0.0, "worst_trade": 0.0,
                "avg_win": 0.0, "avg_loss": 0.0,
            }
        
        stats = self.data["trade_stats"][symbol]
        stats["total_trades"] += 1
        stats["total_pnl"] += pnl
        
        if pnl > 0:
            stats["wins"] += 1
            stats["best_trade"] = max(stats["best_trade"], pnl)
        else:
            stats["losses"] += 1
            stats["worst_trade"] = min(stats["worst_trade"], pnl)
        
        save_analytics(self.data)
    
    def get_performance_summary(self) -> dict:
        history = load_trade_history()
        closed_trades = [t for t in history if t.get("action") == "CLOSED"]
        
        if not closed_trades:
            return {"total_trades": 0, "win_rate": 0, "total_pnl": 0, "avg_pnl": 0}
        
        profits = [t.get("profit", 0) for t in closed_trades]
        wins = [p for p in profits if p > 0]
        losses = [p for p in profits if p < 0]
        
        return {
            "total_trades": len(closed_trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": len(wins) / len(closed_trades) * 100 if closed_trades else 0,
            "total_pnl": sum(profits),
            "avg_pnl": statistics.mean(profits) if profits else 0,
            "avg_win": statistics.mean(wins) if wins else 0,
            "avg_loss": statistics.mean(losses) if losses else 0,
            "best_trade": max(profits) if profits else 0,
            "worst_trade": min(profits) if profits else 0,
            "profit_factor": abs(sum(wins) / sum(losses)) if losses and sum(losses) != 0 else 0,
        }
    
    def get_daily_pnl_series(self, days: int = 30) -> pd.DataFrame:
        daily = self.data.get("daily_pnl", {})
        if not daily:
            return pd.DataFrame()
        
        df = pd.DataFrame([
            {"date": k, "pnl": v} for k, v in daily.items()
        ])
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").tail(days)
        df["cumulative"] = df["pnl"].cumsum()
        return df
    
    def get_symbol_performance(self) -> pd.DataFrame:
        stats = self.data.get("trade_stats", {})
        if not stats:
            return pd.DataFrame()
        
        rows = []
        for symbol, s in stats.items():
            win_rate = s["wins"] / s["total_trades"] * 100 if s["total_trades"] > 0 else 0
            rows.append({
                "symbol": symbol,
                "trades": s["total_trades"],
                "wins": s["wins"],
                "losses": s["losses"],
                "win_rate": win_rate,
                "total_pnl": s["total_pnl"],
                "best": s["best_trade"],
                "worst": s["worst_trade"],
            })
        
        return pd.DataFrame(rows).sort_values("total_pnl", ascending=False)

# Initialize managers
alert_manager = AlertManager()
schedule_manager = ScheduleManager()
analytics_manager = AnalyticsManager()

# ─────────────────────────────────────────────────
# Trading Functions
# ─────────────────────────────────────────────────

def get_current_price(symbol: str, data_client) -> Tuple[float, str]:
    """Get current price for a symbol"""
    if not data_client:
        return 0.0, "Data client not connected"
    try:
        quote = data_client.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=symbol))
        if symbol in quote:
            return float(quote[symbol].ask_price), ""
        return 0.0, f"No quote data for {symbol}"
    except Exception as e:
        return 0.0, str(e)

def get_avg_price(symbol: str, days: int, data_client) -> Tuple[float, str]:
    if not data_client:
        return 0.0, "Data client not connected"
    try:
        symbol = validate_symbol(symbol)
        days = validate_avg_days(days)
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
            return 0.0, f"No historical data for {symbol}"
        avg = float(bars["close"].tail(days).mean())
        return avg, ""
    except Exception as e:
        return 0.0, str(e)

def has_open_position(symbol: str, trading_client) -> Tuple[bool, Optional[dict]]:
    if not trading_client:
        return False, None
    try:
        position = trading_client.get_open_position(symbol)
        return True, {
            "qty": int(position.qty),
            "avg_entry": float(position.avg_entry_price),
            "current_price": float(position.current_price),
            "unrealized_pl": float(position.unrealized_pl),
            "unrealized_plpc": float(position.unrealized_plpc) * 100
        }
    except:
        return False, None

def get_open_orders(symbol: str, trading_client) -> List[dict]:
    if not trading_client:
        return []
    try:
        orders = trading_client.get_orders(filter={"symbol": symbol, "status": "open"})
        return [{"id": str(o.id), "symbol": o.symbol, "side": str(o.side),
                 "qty": int(o.qty), "type": str(o.type),
                 "limit_price": float(o.limit_price) if o.limit_price else None}
                for o in orders]
    except:
        return []

def cancel_orders(symbol: str, trading_client) -> Tuple[int, List[str]]:
    if not trading_client:
        return 0, ["Not connected"]
    cancelled, errors = 0, []
    try:
        orders = trading_client.get_orders(filter={"symbol": symbol, "status": "open"})
        for order in orders:
            try:
                trading_client.cancel_order_by_id(order.id)
                cancelled += 1
            except Exception as e:
                errors.append(str(e))
    except Exception as e:
        errors.append(str(e))
    return cancelled, errors

def cancel_all_orders(trading_client) -> Tuple[int, List[str]]:
    if not trading_client:
        return 0, ["Not connected"]
    try:
        trading_client.cancel_orders()
        return -1, []
    except Exception as e:
        return 0, [str(e)]

def calc_effective_power(cfg: dict, profit: float) -> float:
    effective = cfg["buy_power"] + profit
    if cfg.get("compound_enabled", False):
        cap_multiple = cfg["buy_power"] * cfg.get("max_multiple", 5.0)
        cap_dollar = cfg.get("max_dollar_cap") or float("inf")
        effective = min(effective, cap_multiple, cap_dollar)
    return max(effective, 0)

def place_bracket(symbol: str, cfg: dict, effective_power: float,
                  trading_client, data_client, config: dict) -> Tuple[str, Optional[str]]:
    """Place bracket order with risk checks"""
    if not trading_client:
        return "Not connected", None

    try:
        symbol = validate_symbol(symbol)
    except ValidationError as e:
        return str(e), None

    # Risk check - trade value
    can_trade, reason = risk_manager.can_trade(effective_power, symbol)
    if not can_trade:
        return f"Risk limit: {reason}", None

    avg, error = get_avg_price(symbol, cfg["avg_days"], data_client)
    if error:
        return f"Price fetch failed: {error}", None

    buy_price = round(avg * (1 + cfg["buy_offset"] / 100) if cfg["buy_is_percent"]
                      else avg + cfg["buy_offset"], 2)
    sell_price = round(avg * (1 + cfg["sell_offset"] / 100) if cfg["sell_is_percent"]
                       else avg + cfg["sell_offset"], 2)
    stop_price = round(buy_price * (1 + cfg.get("stop_offset", -10) / 100) if cfg.get("stop_is_percent", True)
                       else buy_price + cfg.get("stop_offset", -5), 2)

    if buy_price <= 0 or sell_price <= buy_price or stop_price >= buy_price:
        return "Invalid price calculation", None

    # Risk check - price deviation from current market price
    current_price, price_error = get_current_price(symbol, data_client)
    if current_price > 0:
        deviation_ok, deviation_reason = risk_manager.check_price_deviation(buy_price, current_price, symbol)
        if not deviation_ok:
            logger.warning(f"Order denied for {symbol}: {deviation_reason}")
            return f"Risk limit: {deviation_reason}", None

    qty = int(effective_power // buy_price)
    if qty < 1:
        return f"Insufficient power (need ${buy_price:.2f})", None

    try:
        order_data = LimitOrderRequest(
            symbol=symbol, qty=qty, side=OrderSide.BUY,
            time_in_force=TimeInForce.GTC, limit_price=buy_price,
            order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(limit_price=sell_price),
            stop_loss=StopLossRequest(stop_price=stop_price),
        )
        order = trading_client.submit_order(order_data=order_data)
        order_id = str(order.id)

        config.setdefault("tracked_orders", {})
        config["tracked_orders"][order_id] = {
            "symbol": symbol, "qty": qty, "buy_price": buy_price,
            "sell_price": sell_price, "stop_price": stop_price,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        save_config(config)
        risk_manager.record_trade()

        # Record in history
        history = load_trade_history()
        history.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbol": symbol, "order_id": order_id, "action": "BRACKET_PLACED",
            "qty": qty, "price": buy_price, "profit": 0
        })
        save_trade_history(history)

        msg = f"Bracket: {symbol} | Qty: {qty} | Buy ${buy_price} | Sell ${sell_price} | Stop ${stop_price}"
        logger.info(msg)
        return msg, order_id

    except Exception as e:
        return f"Order failed: {e}", None

def place_market_order(symbol: str, qty: int, side: str, trading_client) -> Tuple[str, Optional[str]]:
    """Place a market order"""
    if not trading_client:
        return "Not connected", None
    try:
        order_side = OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL
        order = trading_client.submit_order(MarketOrderRequest(
            symbol=symbol, qty=qty, side=order_side, time_in_force=TimeInForce.DAY
        ))
        return f"Market {side}: {qty} {symbol}", str(order.id)
    except Exception as e:
        return f"Failed: {e}", None

def place_trailing_stop(symbol: str, qty: int, trail_percent: float, trading_client) -> Tuple[str, Optional[str]]:
    """Place trailing stop order"""
    if not trading_client:
        return "Not connected", None
    try:
        order = trading_client.submit_order(TrailingStopOrderRequest(
            symbol=symbol, qty=qty, side=OrderSide.SELL,
            time_in_force=TimeInForce.GTC, trail_percent=trail_percent
        ))
        return f"Trailing stop: {qty} {symbol} @ {trail_percent}%", str(order.id)
    except Exception as e:
        return f"Failed: {e}", None

def check_closed_orders_and_update_profits(trading_client, config: dict) -> List[str]:
    """Check for closed orders and update profits"""
    if not trading_client:
        return []
    
    messages = []
    tracked = config.get("tracked_orders", {})
    to_remove = []
    
    for order_id, info in tracked.items():
        try:
            order = trading_client.get_order_by_id(order_id)
            symbol = info["symbol"]
            
            if order.status == OrderStatus.FILLED:
                has_pos, _ = has_open_position(symbol, trading_client)
                if not has_pos:
                    buy_price, qty = info["buy_price"], info["qty"]
                    
                    try:
                        closed = trading_client.get_orders(
                            filter={"symbol": symbol, "status": "closed", "limit": 10}
                        )
                        exit_price = None
                        for o in closed:
                            if o.side == OrderSide.SELL and o.filled_avg_price:
                                exit_price = float(o.filled_avg_price)
                                break
                        
                        if exit_price:
                            profit = (exit_price - buy_price) * qty
                            config["profits"][symbol] = config["profits"].get(symbol, 0) + profit
                            
                            # Record
                            history = load_trade_history()
                            history.append({
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "symbol": symbol, "order_id": order_id, "action": "CLOSED",
                                "qty": qty, "price": exit_price, "profit": profit
                            })
                            save_trade_history(history)
                            
                            risk_manager.record_trade(profit)
                            analytics_manager.record_trade(symbol, profit, "bracket")
                            
                            msg = f"{symbol}: Closed. P/L: ${profit:.2f}"
                            messages.append(msg)
                            logger.info(msg)
                    except:
                        pass
                    to_remove.append(order_id)
            
            elif order.status in [OrderStatus.CANCELED, OrderStatus.EXPIRED, OrderStatus.REJECTED]:
                to_remove.append(order_id)
        except Exception as e:
            if "not found" in str(e).lower():
                to_remove.append(order_id)
    
    for oid in to_remove:
        config["tracked_orders"].pop(oid, None)
    
    if to_remove:
        save_config(config)
    
    return messages

def get_portfolio_summary(trading_client) -> Optional[dict]:
    if not trading_client:
        return None
    try:
        acc = trading_client.get_account()
        return {
            "equity": float(acc.equity),
            "cash": float(acc.cash),
            "buying_power": float(acc.buying_power),
            "portfolio_value": float(acc.portfolio_value),
            "day_pl": float(acc.equity) - float(acc.last_equity),
            "day_pl_pct": ((float(acc.equity) / float(acc.last_equity)) - 1) * 100 if float(acc.last_equity) > 0 else 0
        }
    except:
        return None

def get_all_positions(trading_client) -> List[dict]:
    if not trading_client:
        return []
    try:
        positions = trading_client.get_all_positions()
        return [{"symbol": p.symbol, "qty": int(p.qty),
                 "avg_entry": float(p.avg_entry_price),
                 "current_price": float(p.current_price),
                 "market_value": float(p.market_value),
                 "unrealized_pl": float(p.unrealized_pl),
                 "unrealized_plpc": float(p.unrealized_plpc) * 100}
                for p in positions]
    except:
        return []

# ─────────────────────────────────────────────────
# Background Workers
# ─────────────────────────────────────────────────

def start_background_workers(trading_client, data_client, telegram_bot=None):
    """Start all background monitoring threads"""
    
    def profit_monitor():
        while True:
            try:
                config = load_config()
                msgs = check_closed_orders_and_update_profits(trading_client, config)
                for msg in msgs:
                    if telegram_bot:
                        try:
                            telegram_bot.send_message(st.session_state.get("telegram_uid", 0), f"📊 {msg}")
                        except:
                            pass
            except Exception as e:
                logger.error(f"Profit monitor error: {e}")
            time.sleep(60)
    
    def alert_monitor():
        while True:
            try:
                if data_client:
                    triggered = alert_manager.check_alerts(data_client)
                    for alert in triggered:
                        msg = f"🔔 ALERT: {alert['message']} (triggered at ${alert.get('triggered_price', 0):.2f})"
                        logger.info(msg)
                        if telegram_bot and alert.get("notify_telegram"):
                            try:
                                telegram_bot.send_message(st.session_state.get("telegram_uid", 0), msg)
                            except:
                                pass
            except Exception as e:
                logger.error(f"Alert monitor error: {e}")
            time.sleep(30)
    
    def schedule_executor():
        while True:
            try:
                if os.path.exists(PAUSE_FILE):
                    time.sleep(60)
                    continue
                
                due = schedule_manager.get_due_schedules()
                config = load_config()
                
                for schedule in due:
                    symbol = schedule["symbol"]
                    action = schedule["action"]
                    
                    try:
                        if action == "place_bracket":
                            if symbol in config["tickers"]:
                                cfg = config["tickers"][symbol]
                                if cfg.get("enabled", True):
                                    has_pos, _ = has_open_position(symbol, trading_client)
                                    if not has_pos:
                                        profit = config["profits"].get(symbol, 0)
                                        effective = calc_effective_power(cfg, profit)
                                        msg, _ = place_bracket(symbol, cfg, effective, trading_client, data_client, config)
                                        logger.info(f"Scheduled: {msg}")
                                        if telegram_bot:
                                            try:
                                                telegram_bot.send_message(st.session_state.get("telegram_uid", 0), f"⏰ Scheduled: {msg}")
                                            except:
                                                pass
                        
                        elif action == "cancel_orders":
                            cancelled, _ = cancel_orders(symbol, trading_client)
                            logger.info(f"Scheduled cancel: {symbol} - {cancelled} orders")
                        
                        schedule_manager.mark_run(schedule["id"])
                        
                    except Exception as e:
                        logger.error(f"Schedule execution error: {e}")
                
            except Exception as e:
                logger.error(f"Schedule executor error: {e}")
            time.sleep(30)
    
    threading.Thread(target=profit_monitor, daemon=True).start()
    threading.Thread(target=alert_monitor, daemon=True).start()
    threading.Thread(target=schedule_executor, daemon=True).start()
    logger.info("Background workers started")

# ─────────────────────────────────────────────────
# Export Functions
# ─────────────────────────────────────────────────

def export_config_csv() -> str:
    config = load_config()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Symbol", "Buy Power", "Avg Days", "Buy Offset", "Buy %", 
                     "Sell Offset", "Sell %", "Stop Offset", "Stop %", 
                     "Compound", "Max Multiple", "Max Cap", "Profit", "Enabled"])
    
    for symbol, cfg in config["tickers"].items():
        profit = config["profits"].get(symbol, 0)
        writer.writerow([
            symbol, cfg["buy_power"], cfg["avg_days"], cfg["buy_offset"],
            cfg["buy_is_percent"], cfg["sell_offset"], cfg["sell_is_percent"],
            cfg["stop_offset"], cfg["stop_is_percent"], cfg.get("compound_enabled", False),
            cfg.get("max_multiple", 5), cfg.get("max_dollar_cap", 10000),
            profit, cfg.get("enabled", True)
        ])
    
    return output.getvalue()

def export_trades_csv() -> str:
    history = load_trade_history()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Timestamp", "Symbol", "Action", "Qty", "Price", "Profit"])
    
    for trade in history:
        writer.writerow([
            trade.get("timestamp", ""),
            trade.get("symbol", ""),
            trade.get("action", ""),
            trade.get("qty", 0),
            trade.get("price", 0),
            trade.get("profit", 0)
        ])
    
    return output.getvalue()

# ─────────────────────────────────────────────────
# Streamlit UI
# ─────────────────────────────────────────────────

st.set_page_config(
    page_title="Bracket Bot Pro",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .stMetric { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                padding: 15px; border-radius: 10px; border: 1px solid #0f3460; }
    .profit-positive { color: #00ff88; }
    .profit-negative { color: #ff4444; }
    div[data-testid="stMetricValue"] { font-size: 24px; }
    .market-open { color: #00ff88; font-weight: bold; }
    .market-closed { color: #ff6b6b; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

config = load_config()

# ─────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────

st.sidebar.title("⚙️ Settings")

API_KEY = st.sidebar.text_input("Alpaca API Key", type="password", value=os.getenv("ALPACA_API_KEY", ""))
API_SECRET = st.sidebar.text_input("Alpaca API Secret", type="password", value=os.getenv("ALPACA_SECRET_KEY", ""))
PAPER_MODE = st.sidebar.checkbox("Paper Trading", value=True)

st.sidebar.divider()
TELEGRAM_TOKEN = st.sidebar.text_input("Telegram Token", type="password", value=os.getenv("TELEGRAM_TOKEN", ""))
TELEGRAM_USER_ID = st.sidebar.number_input("Telegram User ID", min_value=0, value=int(os.getenv("TELEGRAM_USER_ID", "0")))

trading_client = None
data_client = None
telegram_bot = None

if API_KEY and API_SECRET:
    try:
        trading_client = TradingClient(API_KEY, API_SECRET, paper=PAPER_MODE)
        data_client = StockHistoricalDataClient(API_KEY, API_SECRET)
        st.sidebar.success("✅ Alpaca connected")
        
        if "workers_started" not in st.session_state:
            if TELEGRAM_TOKEN and TELEGRAM_USER_ID > 0:
                telegram_bot = telebot.TeleBot(TELEGRAM_TOKEN)
                st.session_state["telegram_uid"] = TELEGRAM_USER_ID
            start_background_workers(trading_client, data_client, telegram_bot)
            st.session_state["workers_started"] = True
    except Exception as e:
        st.sidebar.error(f"Connection failed: {e}")
else:
    st.sidebar.warning("Enter Alpaca credentials")

# Market status
market_status = "🟢 OPEN" if is_market_open() else "🔴 CLOSED"
st.sidebar.markdown(f"**Market:** {market_status}")

if not is_market_open():
    next_open = time_until_market_open()
    hours = int(next_open.total_seconds() // 3600)
    mins = int((next_open.total_seconds() % 3600) // 60)
    st.sidebar.caption(f"Opens in: {hours}h {mins}m")

# ─────────────────────────────────────────────────
# Add Ticker Form
# ─────────────────────────────────────────────────

st.sidebar.divider()
st.sidebar.header("➕ Add Ticker")

new_symbol = st.sidebar.text_input("Symbol", "").strip().upper()
if new_symbol:
    try:
        validated = validate_symbol(new_symbol)
        defaults = config["tickers"].get(validated, TICKER_DEFAULTS)
        
        buy_power = st.sidebar.number_input("Buy Power ($)", 1.0, 1000000.0, float(defaults["buy_power"]))
        avg_days = st.sidebar.number_input("Avg Days", 1, 365, int(defaults["avg_days"]))
        
        col1, col2 = st.sidebar.columns(2)
        with col1:
            buy_offset = st.sidebar.number_input("Buy Offset", -50.0, 50.0, float(defaults["buy_offset"]))
            buy_is_pct = st.sidebar.checkbox("Buy %", value=defaults["buy_is_percent"])
        with col2:
            sell_offset = st.sidebar.number_input("Sell Offset", -50.0, 100.0, float(defaults["sell_offset"]))
            sell_is_pct = st.sidebar.checkbox("Sell %", value=defaults["sell_is_percent"])
        
        stop_offset = st.sidebar.number_input("Stop Offset", -50.0, 50.0, float(defaults["stop_offset"]))
        stop_is_pct = st.sidebar.checkbox("Stop %", value=defaults["stop_is_percent"])
        
        compound = st.sidebar.checkbox("Compound", value=defaults.get("compound_enabled", False))
        if compound:
            max_mult = st.sidebar.number_input("Max Multiple", 1.0, 100.0, float(defaults.get("max_multiple", 5)))
            max_cap = st.sidebar.number_input("Max Cap ($)", 0.0, 10000000.0, float(defaults.get("max_dollar_cap", 10000)))
        else:
            max_mult, max_cap = 5.0, 10000.0
        
        tags_input = st.sidebar.text_input("Tags (comma-separated)", ",".join(defaults.get("tags", [])))
        notes = st.sidebar.text_area("Notes", defaults.get("notes", ""), height=60)
        
        if st.sidebar.button(f"💾 Save {validated}"):
            config["tickers"][validated] = {
                "buy_power": buy_power, "avg_days": avg_days,
                "buy_offset": buy_offset, "buy_is_percent": buy_is_pct,
                "sell_offset": sell_offset, "sell_is_percent": sell_is_pct,
                "stop_offset": stop_offset, "stop_is_percent": stop_is_pct,
                "compound_enabled": compound, "max_multiple": max_mult, "max_dollar_cap": max_cap,
                "tags": [t.strip() for t in tags_input.split(",") if t.strip()],
                "notes": notes, "enabled": True, "strategy": "bracket",
                "trailing_stop_percent": 5.0,
            }
            config["profits"].setdefault(validated, 0.0)
            save_config(config)
            st.sidebar.success(f"✅ Saved {validated}")
            st.rerun()
    except ValidationError as e:
        st.sidebar.error(str(e))

# ─────────────────────────────────────────────────
# Main Dashboard
# ─────────────────────────────────────────────────

st.title("📈 Bracket Bot Pro")

paused = os.path.exists(PAUSE_FILE)
if paused:
    st.error("🛑 BOT PAUSED")
    if st.button("▶️ Resume"):
        os.remove(PAUSE_FILE)
        st.rerun()

# Portfolio & Risk Overview
if trading_client:
    col1, col2 = st.columns([2, 1])
    
    with col1:
        portfolio = get_portfolio_summary(trading_client)
        if portfolio:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Equity", f"${portfolio['equity']:,.2f}")
            c2.metric("Cash", f"${portfolio['cash']:,.2f}")
            c3.metric("Buying Power", f"${portfolio['buying_power']:,.2f}")
            c4.metric("Day P/L", f"${portfolio['day_pl']:,.2f}", f"{portfolio['day_pl_pct']:.2f}%")
    
    with col2:
        risk_status = risk_manager.get_status()
        st.markdown("**Risk Status**")
        st.progress(risk_status["daily_trades"] / max(risk_status["daily_trade_limit"], 1))
        st.caption(f"Trades: {risk_status['daily_trades']}/{risk_status['daily_trade_limit']} | P/L: ${risk_status['daily_pnl']:.2f}")

st.divider()

# Tabs
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "📊 Watchlist", "📈 Positions", "🔔 Alerts", "⏰ Schedules", 
    "📜 History", "📉 Analytics", "⚙️ Settings"
])

# ─────────────────────────────────────────────────
# Tab 1: Watchlist
# ─────────────────────────────────────────────────

with tab1:
    if not config["tickers"]:
        st.info("Add tickers in the sidebar")
    else:
        # Filter controls
        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            all_tags = set()
            for cfg in config["tickers"].values():
                all_tags.update(cfg.get("tags", []))
            filter_tag = st.selectbox("Filter by tag", ["All"] + sorted(all_tags))
        with col2:
            filter_status = st.selectbox("Filter by status", ["All", "Waiting", "In-trade", "Pending"])
        with col3:
            if st.button("🔄 Check Profits"):
                msgs = check_closed_orders_and_update_profits(trading_client, config)
                for m in msgs:
                    st.success(m)
                config = load_config()
        
        data_rows = []
        total_profit = 0
        
        for symbol, cfg in config["tickers"].items():
            if not cfg.get("enabled", True):
                continue
            if filter_tag != "All" and filter_tag not in cfg.get("tags", []):
                continue
            
            profit = config["profits"].get(symbol, 0)
            total_profit += profit
            effective = calc_effective_power(cfg, profit)
            
            has_pos, pos_info = has_open_position(symbol, trading_client)
            orders = get_open_orders(symbol, trading_client)
            
            if has_pos:
                status = "In-trade"
            elif orders:
                status = "Pending"
            else:
                status = "Waiting"
            
            if filter_status != "All" and status != filter_status:
                continue
            
            avg, _ = get_avg_price(symbol, cfg["avg_days"], data_client)
            buy_price = avg * (1 + cfg["buy_offset"] / 100) if cfg["buy_is_percent"] else avg + cfg["buy_offset"]
            
            # Check current price and deviation
            current_price, _ = get_current_price(symbol, data_client)
            deviation_ok = True
            deviation_info = ""
            if current_price > 0 and buy_price > 0:
                price_diff = abs(buy_price - current_price)
                pct_diff = (price_diff / current_price) * 100
                deviation_ok, _ = risk_manager.check_price_deviation(buy_price, current_price, symbol)
                deviation_info = f"{pct_diff:.1f}%"
            
            data_rows.append({
                "Symbol": symbol,
                "Status": status,
                "Base": f"${cfg['buy_power']:.0f}",
                "Profit": f"${profit:.2f}",
                "Effective": f"${effective:.2f}",
                "Current": f"${current_price:.2f}" if current_price > 0 else "—",
                "Buy @": f"${buy_price:.2f}" if avg > 0 else "—",
                "Deviation": deviation_info,
                "Risk OK": "✅" if deviation_ok else "❌",
                "Tags": ", ".join(cfg.get("tags", [])),
            })
        
        # Summary
        c1, c2, c3 = st.columns(3)
        c1.metric("Tickers", len([r for r in data_rows]))
        c2.metric("Total Profit", f"${total_profit:.2f}")
        perf = analytics_manager.get_performance_summary()
        c3.metric("Win Rate", f"{perf.get('win_rate', 0):.1f}%")
        
        if data_rows:
            st.dataframe(pd.DataFrame(data_rows), use_container_width=True, hide_index=True)
        
        # Ticker actions
        st.subheader("Actions")
        for symbol in config["tickers"]:
            cfg = config["tickers"][symbol]
            if not cfg.get("enabled", True):
                continue
            
            profit = config["profits"].get(symbol, 0)
            effective = calc_effective_power(cfg, profit)
            
            with st.expander(f"**{symbol}** | ${effective:.2f} effective"):
                c1, c2, c3, c4, c5 = st.columns(5)
                
                with c1:
                    if st.button("📈 Bracket", key=f"b_{symbol}"):
                        if not paused and trading_client:
                            msg, _ = place_bracket(symbol, cfg, effective, trading_client, data_client, config)
                            st.write(msg)
                
                with c2:
                    if st.button("❌ Cancel", key=f"c_{symbol}"):
                        n, _ = cancel_orders(symbol, trading_client)
                        st.write(f"Cancelled {n}")
                
                with c3:
                    if st.button("🔄 Reset P/L", key=f"r_{symbol}"):
                        config["profits"][symbol] = 0
                        save_config(config)
                        st.rerun()
                
                with c4:
                    if st.button("⏸️ Disable", key=f"d_{symbol}"):
                        config["tickers"][symbol]["enabled"] = False
                        save_config(config)
                        st.rerun()
                
                with c5:
                    if st.button("🗑️ Remove", key=f"rm_{symbol}"):
                        config["tickers"].pop(symbol, None)
                        config["profits"].pop(symbol, None)
                        save_config(config)
                        st.rerun()
        
        # Global actions
        st.divider()
        c1, c2, c3, c4 = st.columns(4)
        
        with c1:
            if st.button("📈 Place All Brackets", type="primary"):
                if not paused and trading_client:
                    for sym, cfg in config["tickers"].items():
                        if cfg.get("enabled", True):
                            has_pos, _ = has_open_position(sym, trading_client)
                            if not has_pos:
                                profit = config["profits"].get(sym, 0)
                                eff = calc_effective_power(cfg, profit)
                                msg, _ = place_bracket(sym, cfg, eff, trading_client, data_client, config)
                                st.write(f"{sym}: {msg}")
        
        with c2:
            if st.button("❌ Cancel All"):
                cancel_all_orders(trading_client)
                st.success("All cancelled")
        
        with c3:
            if st.button("⏸️ Pause Bot"):
                open(PAUSE_FILE, "w").close()
                st.rerun()
        
        with c4:
            st.download_button("📥 Export CSV", export_config_csv(), "tickers.csv", "text/csv")

# ─────────────────────────────────────────────────
# Tab 2: Positions
# ─────────────────────────────────────────────────

with tab2:
    if trading_client:
        positions = get_all_positions(trading_client)
        if positions:
            st.subheader(f"Open Positions ({len(positions)})")
            df = pd.DataFrame(positions)
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            total_unrealized = sum(p["unrealized_pl"] for p in positions)
            st.metric("Total Unrealized P/L", f"${total_unrealized:.2f}")
        else:
            st.info("No open positions")
    else:
        st.warning("Connect to Alpaca")

# ─────────────────────────────────────────────────
# Tab 3: Alerts
# ─────────────────────────────────────────────────

with tab3:
    st.subheader("🔔 Price Alerts")
    
    # Add alert form
    with st.form("add_alert"):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            alert_symbol = st.text_input("Symbol").upper()
        with c2:
            alert_condition = st.selectbox("Condition", ["above", "below", "crosses_above", "crosses_below"])
        with c3:
            alert_price = st.number_input("Price ($)", min_value=0.01)
        with c4:
            alert_telegram = st.checkbox("Telegram", value=True)
        
        if st.form_submit_button("➕ Add Alert"):
            try:
                aid = alert_manager.add_alert(alert_symbol, alert_condition, alert_price, notify_telegram=alert_telegram)
                st.success(f"Alert {aid} created")
            except Exception as e:
                st.error(str(e))
    
    # Active alerts
    active = alert_manager.get_active_alerts()
    if active:
        st.markdown("**Active Alerts**")
        for alert in active:
            c1, c2 = st.columns([4, 1])
            with c1:
                st.write(f"🔔 {alert['symbol']} {alert['condition']} ${alert['target_price']:.2f}")
            with c2:
                if st.button("🗑️", key=f"del_alert_{alert['id']}"):
                    alert_manager.remove_alert(alert["id"])
                    st.rerun()
    else:
        st.info("No active alerts")
    
    # Triggered
    triggered = alert_manager.get_triggered_alerts()
    if triggered:
        st.markdown("**Triggered Alerts**")
        for alert in triggered[-10:]:
            st.write(f"✅ {alert['symbol']} {alert['condition']} ${alert['target_price']:.2f} @ {alert.get('triggered_at', '')[:10]}")

# ─────────────────────────────────────────────────
# Tab 4: Schedules
# ─────────────────────────────────────────────────

with tab4:
    st.subheader("⏰ Scheduled Tasks")
    
    with st.form("add_schedule"):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            sched_symbol = st.text_input("Symbol").upper()
        with c2:
            sched_action = st.selectbox("Action", ["place_bracket", "cancel_orders"])
        with c3:
            sched_freq = st.selectbox("Frequency", ["market_open", "market_close", "daily", "once"])
        with c4:
            sched_time = st.text_input("Time (HH:MM)", "09:35")
        
        if st.form_submit_button("➕ Add Schedule"):
            try:
                sid = schedule_manager.add_schedule(sched_symbol, sched_action, sched_freq, sched_time)
                st.success(f"Schedule {sid} created")
            except Exception as e:
                st.error(str(e))
    
    schedules = load_schedules()
    if schedules:
        for sched in schedules:
            c1, c2, c3 = st.columns([3, 1, 1])
            with c1:
                status = "✅" if sched.get("enabled") else "⏸️"
                st.write(f"{status} {sched['symbol']} - {sched['action']} @ {sched['frequency']} {sched.get('time', '')}")
            with c2:
                if st.button("Toggle", key=f"tog_{sched['id']}"):
                    schedule_manager.toggle_schedule(sched["id"])
                    st.rerun()
            with c3:
                if st.button("🗑️", key=f"del_sched_{sched['id']}"):
                    schedule_manager.remove_schedule(sched["id"])
                    st.rerun()
    else:
        st.info("No schedules")

# ─────────────────────────────────────────────────
# Tab 5: Trade History
# ─────────────────────────────────────────────────

with tab5:
    history = load_trade_history()
    if history:
        st.subheader(f"Trade History ({len(history)} records)")
        
        df = pd.DataFrame(history).sort_values("timestamp", ascending=False)
        st.dataframe(df.head(100), use_container_width=True, hide_index=True)
        
        st.download_button("📥 Export Trades", export_trades_csv(), "trades.csv", "text/csv")
    else:
        st.info("No trade history")

# ─────────────────────────────────────────────────
# Tab 6: Analytics
# ─────────────────────────────────────────────────

with tab6:
    st.subheader("📉 Performance Analytics")
    
    perf = analytics_manager.get_performance_summary()
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Trades", perf.get("total_trades", 0))
    c2.metric("Win Rate", f"{perf.get('win_rate', 0):.1f}%")
    c3.metric("Total P/L", f"${perf.get('total_pnl', 0):.2f}")
    c4.metric("Profit Factor", f"{perf.get('profit_factor', 0):.2f}")
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Wins", perf.get("wins", 0))
    c2.metric("Losses", perf.get("losses", 0))
    c3.metric("Avg Win", f"${perf.get('avg_win', 0):.2f}")
    c4.metric("Avg Loss", f"${perf.get('avg_loss', 0):.2f}")
    
    # Daily P/L chart
    daily_pnl = analytics_manager.get_daily_pnl_series(30)
    if not daily_pnl.empty:
        st.subheader("Daily P/L (30 days)")
        st.line_chart(daily_pnl.set_index("date")["cumulative"])
    
    # Per-symbol performance
    symbol_perf = analytics_manager.get_symbol_performance()
    if not symbol_perf.empty:
        st.subheader("Per-Symbol Performance")
        st.dataframe(symbol_perf, use_container_width=True, hide_index=True)

# ─────────────────────────────────────────────────
# Tab 7: Settings
# ─────────────────────────────────────────────────

with tab7:
    st.subheader("⚙️ Risk Management")
    
    risk = load_risk_settings()
    
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**General Limits**")
        risk["enabled"] = st.checkbox("Enable Risk Management", value=risk.get("enabled", True))
        risk["max_daily_loss"] = st.number_input("Max Daily Loss ($)", 0.0, 100000.0, float(risk.get("max_daily_loss", 500)))
        risk["max_position_size"] = st.number_input("Max Position Size ($)", 0.0, 1000000.0, float(risk.get("max_position_size", 5000)))
        risk["daily_trade_limit"] = st.number_input("Daily Trade Limit", 1, 1000, int(risk.get("daily_trade_limit", 50)))
    
    with c2:
        st.markdown("**Position Limits**")
        risk["max_positions"] = st.number_input("Max Positions", 1, 100, int(risk.get("max_positions", 10)))
        risk["pause_on_daily_loss"] = st.checkbox("Pause on Daily Loss", value=risk.get("pause_on_daily_loss", True))
        risk["require_confirmation_above"] = st.number_input("Confirm Above ($)", 0.0, 100000.0, float(risk.get("require_confirmation_above", 1000)))
    
    st.divider()
    st.markdown("### 🎯 Price Deviation Protection")
    st.caption("Deny bracket orders if buy price is too far from current market price")
    
    c1, c2, c3 = st.columns(3)
    with c1:
        risk["price_deviation_check_enabled"] = st.checkbox(
            "Enable Price Deviation Check", 
            value=risk.get("price_deviation_check_enabled", True),
            help="Block orders if calculated buy price differs too much from current price"
        )
    with c2:
        risk["max_price_deviation_percent"] = st.number_input(
            "Max Deviation (%)", 
            0.0, 100.0, 
            float(risk.get("max_price_deviation_percent", 10.0)),
            help="Maximum allowed % difference between buy price and current price. Set 0 to disable."
        )
    with c3:
        risk["max_price_deviation_dollar"] = st.number_input(
            "Max Deviation ($)", 
            0.0, 10000.0, 
            float(risk.get("max_price_deviation_dollar", 0.0)),
            help="Maximum allowed $ difference. Set 0 to disable dollar-based check."
        )
    
    # Show example calculation
    if risk["price_deviation_check_enabled"]:
        st.info(
            f"**Example:** If current price is $100 and your buy offset calculates to $85:\n"
            f"- Deviation = 15% (${15:.2f})\n"
            f"- With {risk['max_price_deviation_percent']}% limit → {'❌ DENIED' if 15 > risk['max_price_deviation_percent'] else '✅ ALLOWED'}"
        )
    
    if st.button("💾 Save Risk Settings"):
        save_risk_settings(risk)
        risk_manager.settings = risk
        st.success("Saved")
    
    st.divider()
    st.subheader("📋 Logs")
    
    if os.path.exists(LOG_FILE):
        log_lines = st.slider("Lines", 10, 500, 50)
        with open(LOG_FILE, "r") as f:
            lines = f.readlines()[-log_lines:]
        st.code("".join(lines), language="log")
        
        if st.button("🗑️ Clear Logs"):
            open(LOG_FILE, "w").close()
            st.success("Cleared")

# ─────────────────────────────────────────────────
# Telegram Bot
# ─────────────────────────────────────────────────

if TELEGRAM_TOKEN and TELEGRAM_USER_ID > 0 and "telegram_started" not in st.session_state:
    try:
        bot = telebot.TeleBot(TELEGRAM_TOKEN)
        UID = int(TELEGRAM_USER_ID)
        st.session_state["telegram_uid"] = UID

        def guard(m):
            return m.from_user.id == UID

        @bot.message_handler(commands=["start", "help"])
        def tg_help(m):
            if not guard(m): return
            bot.reply_to(m, """🤖 *Bracket Bot Pro*
/status - Tickers status
/portfolio - Account info
/risk - Risk status & deviation limits
/setdeviation percent 15 - Set max % deviation
/setdeviation dollar 5 - Set max $ deviation
/buy SYMBOL - Place bracket
/cancel SYMBOL - Cancel orders
/cancelall - Cancel all
/alert SYMBOL above/below PRICE - Set alert
/schedule SYMBOL market_open - Add schedule
/stop - Pause bot
/restart - Resume bot
/reset SYMBOL - Reset P/L""", parse_mode="Markdown")

        @bot.message_handler(commands=["status"])
        def tg_status(m):
            if not guard(m): return
            cfg = load_config()
            lines = ["📊 *Status*\n"]
            for sym, c in cfg["tickers"].items():
                if not c.get("enabled"): continue
                profit = cfg["profits"].get(sym, 0)
                eff = calc_effective_power(c, profit)
                has_pos, _ = has_open_position(sym, trading_client)
                st = "🟢" if has_pos else "🟡"
                lines.append(f"{st} *{sym}* ${eff:.0f} | P/L ${profit:.2f}")
            bot.reply_to(m, "\n".join(lines), parse_mode="Markdown")

        @bot.message_handler(commands=["portfolio"])
        def tg_portfolio(m):
            if not guard(m): return
            p = get_portfolio_summary(trading_client)
            if p:
                bot.reply_to(m, f"💼 Equity: ${p['equity']:,.0f}\nCash: ${p['cash']:,.0f}\nDay P/L: ${p['day_pl']:,.2f}")

        @bot.message_handler(commands=["risk"])
        def tg_risk(m):
            if not guard(m): return
            r = risk_manager.get_status()
            settings = risk_manager.settings
            dev_pct = settings.get("max_price_deviation_percent", 10)
            dev_dollar = settings.get("max_price_deviation_dollar", 0)
            dev_enabled = "✅" if settings.get("price_deviation_check_enabled", True) else "❌"
            bot.reply_to(m, 
                f"🛡️ *Risk Status*\n"
                f"Trades: {r['daily_trades']}/{r['daily_trade_limit']}\n"
                f"P/L: ${r['daily_pnl']:.2f}\n\n"
                f"*Price Deviation:* {dev_enabled}\n"
                f"Max %: {dev_pct}%\n"
                f"Max $: ${dev_dollar:.2f}",
                parse_mode="Markdown"
            )

        @bot.message_handler(commands=["setdeviation"])
        def tg_setdeviation(m):
            if not guard(m): return
            try:
                parts = m.text.split()
                if len(parts) < 3:
                    bot.reply_to(m, "Usage: /setdeviation percent 15\nOr: /setdeviation dollar 5")
                    return
                
                setting_type = parts[1].lower()
                value = float(parts[2])
                
                risk = load_risk_settings()
                if setting_type in ["percent", "pct", "%"]:
                    risk["max_price_deviation_percent"] = value
                    bot.reply_to(m, f"✅ Max deviation set to {value}%")
                elif setting_type in ["dollar", "$", "usd"]:
                    risk["max_price_deviation_dollar"] = value
                    bot.reply_to(m, f"✅ Max deviation set to ${value}")
                else:
                    bot.reply_to(m, "Use 'percent' or 'dollar'")
                    return
                
                save_risk_settings(risk)
                risk_manager.settings = risk
            except Exception as e:
                bot.reply_to(m, f"Error: {e}")

        @bot.message_handler(commands=["buy"])
        def tg_buy(m):
            if not guard(m): return
            try:
                sym = m.text.split()[1].upper()
                cfg = load_config()
                if sym not in cfg["tickers"]:
                    bot.reply_to(m, f"❌ {sym} not found")
                    return
                c = cfg["tickers"][sym]
                profit = cfg["profits"].get(sym, 0)
                eff = calc_effective_power(c, profit)
                msg, _ = place_bracket(sym, c, eff, trading_client, data_client, cfg)
                bot.reply_to(m, msg)
            except:
                bot.reply_to(m, "Usage: /buy SYMBOL")

        @bot.message_handler(commands=["cancel"])
        def tg_cancel(m):
            if not guard(m): return
            try:
                sym = m.text.split()[1].upper()
                n, _ = cancel_orders(sym, trading_client)
                bot.reply_to(m, f"Cancelled {n} orders")
            except:
                bot.reply_to(m, "Usage: /cancel SYMBOL")

        @bot.message_handler(commands=["cancelall"])
        def tg_cancelall(m):
            if not guard(m): return
            cancel_all_orders(trading_client)
            bot.reply_to(m, "✅ All orders cancelled")

        @bot.message_handler(commands=["alert"])
        def tg_alert(m):
            if not guard(m): return
            try:
                parts = m.text.split()
                sym, cond, price = parts[1].upper(), parts[2], float(parts[3])
                aid = alert_manager.add_alert(sym, cond, price)
                bot.reply_to(m, f"✅ Alert {aid} created")
            except:
                bot.reply_to(m, "Usage: /alert SYMBOL above/below PRICE")

        @bot.message_handler(commands=["schedule"])
        def tg_schedule(m):
            if not guard(m): return
            try:
                parts = m.text.split()
                sym, freq = parts[1].upper(), parts[2]
                sid = schedule_manager.add_schedule(sym, "place_bracket", freq)
                bot.reply_to(m, f"✅ Schedule {sid} created")
            except:
                bot.reply_to(m, "Usage: /schedule SYMBOL market_open/daily")

        @bot.message_handler(commands=["stop"])
        def tg_stop(m):
            if not guard(m): return
            open(PAUSE_FILE, "w").close()
            bot.reply_to(m, "⏸️ Bot paused")

        @bot.message_handler(commands=["restart"])
        def tg_restart(m):
            if not guard(m): return
            if os.path.exists(PAUSE_FILE):
                os.remove(PAUSE_FILE)
            bot.reply_to(m, "▶️ Bot resumed")

        @bot.message_handler(commands=["reset"])
        def tg_reset(m):
            if not guard(m): return
            try:
                sym = m.text.split()[1].upper()
                cfg = load_config()
                cfg["profits"][sym] = 0
                save_config(cfg)
                bot.reply_to(m, f"✅ {sym} P/L reset")
            except:
                bot.reply_to(m, "Usage: /reset SYMBOL")

        threading.Thread(target=lambda: bot.infinity_polling(timeout=10), daemon=True).start()
        st.session_state["telegram_started"] = True
        st.sidebar.success("✅ Telegram active")
    except Exception as e:
        st.sidebar.error(f"Telegram error: {e}")

# Footer
st.divider()
st.caption(f"📈 Bracket Bot Pro v3.0 | {datetime.now().strftime('%Y-%m-%d %H:%M')} | {'📝 Paper' if PAPER_MODE else '💰 Live'} | Market: {market_status}")
