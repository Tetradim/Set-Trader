"""Command schemas for Edge ↔ Pulse integration.

Pulse communicates with Edge via MongoDB change streams and REST endpoints.
These schemas define the command documents that Pulse inserts into the
commands collection for Edge to consume.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CommandType(str, Enum):
    """Command types for Edge ← Pulse communication."""
    ORDER_FILLED = "ORDER_FILLED"        # Trade executed
    POSITION_UPDATE = "POSITION_UPDATE"  # Real-time P&L
    ACCOUNT_UPDATE = "ACCOUNT_UPDATE"   # Account metrics
    PULSE_STATUS = "PULSE_STATUS"       # Heartbeat (trading mode, market state)
    BROKER_STATUS = "BROKER_STATUS"      # Broker connectivity
    AUTO_STOP_TRIGGERED = "AUTO_STOP_TRIGGERED"  # Auto-stop fired


class TradingMode(str, Enum):
    """Trading mode indicators."""
    PAPER = "paper"
    LIVE = "live"


class MarketState(str, Enum):
    """Market state indicators."""
    OPEN = "open"
    CLOSED = "closed"
    PRE_MARKET = "pre_market"
    AFTER_HOURS = "after_hours"


class BrokerConnectionState(str, Enum):
    """Broker connection states."""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"


class OrderFilled(BaseModel):
    """ORDER_FILLED command - Trade executed.
    
    Inserted into commands collection after a trade fill is executed.
    Edge listens to change streams on this collection.
    """
    command_type: str = Field(default=CommandType.ORDER_FILLED, description="Command type identifier")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(), description="ISO timestamp")
    
    # Trade details
    symbol: str = Field(description="Ticker symbol")
    side: str = Field(description="BUY or SELL")
    quantity: float = Field(description="Number of shares")
    price: float = Field(description="Fill price")
    total_value: float = Field(description="Total value (quantity * price)")
    
    # Execution details
    order_type: str = Field(default="market", description="Order type: market, limit, stop")
    order_id: str = Field(default="", description="Broker order ID")
    execution_id: str = Field(default="", description="Execution/ fill ID")
    
    # Position context
    avg_entry: float = Field(default=0.0, description="Average entry price")
    position_qty: float = Field(default=0.0, description="Position quantity after fill")
    
    # P&L (for sells)
    pnl: float = Field(default=0.0, description="Realized P&L")
    pnl_percent: float = Field(default=0.0, description="P&L as percentage")
    
    # Trading context
    trading_mode: str = Field(default=TradingMode.PAPER, description="paper or live")
    broker_id: str = Field(default="", description="Broker identifier")
    reason: str = Field(default="", description="Execution reason (signal, trailing, etc.)")
    
    # Metadata
    source: str = Field(default="pulse", description="Source system")
    version: str = Field(default="1.0", description="Schema version")


class PositionUpdate(BaseModel):
    """POSITION_UPDATE command - Real-time P&L.
    
    Broadcast when position values change significantly or on a heartbeat.
    """
    command_type: str = Field(default=CommandType.POSITION_UPDATE, description="Command type identifier")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(), description="ISO timestamp")
    
    # Position details
    symbol: str = Field(description="Ticker symbol")
    quantity: float = Field(description="Number of shares held")
    avg_entry: float = Field(description="Average entry price")
    current_price: float = Field(description="Current market price")
    
    # P&L calculations
    market_value: float = Field(description="Market value (quantity * current_price)")
    cost_basis: float = Field(description="Cost basis (quantity * avg_entry)")
    unrealized_pnl: float = Field(description="Unrealized P&L")
    unrealized_pnl_percent: float = Field(description="Unrealized P&L percentage")
    
    # Trading context
    trading_mode: str = Field(default=TradingMode.PAPER, description="paper or live")
    broker_id: str = Field(default="", description="Broker identifier")
    
    # Metadata
    source: str = Field(default="pulse", description="Source system")
    version: str = Field(default="1.0", description="Schema version")


class AccountUpdate(BaseModel):
    """ACCOUNT_UPDATE command - Account metrics.
    
    Broadcast when account metrics change significantly or on a heartbeat.
    """
    command_type: str = Field(default=CommandType.ACCOUNT_UPDATE, description="Command type identifier")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(), description="ISO timestamp")
    
    # Account totals
    account_balance: float = Field(description="Total account balance")
    allocated: float = Field(description="Allocated capital")
    available: float = Field(description="Available capital")
    cash_reserve: float = Field(description="Cash reserve")
    
    # P&L
    total_realized_pnl: float = Field(description="Total realized P&L")
    total_unrealized_pnl: float = Field(description="Total unrealized P&L")
    
    # Positions
    open_positions: int = Field(description="Number of open positions")
    positions: List[Dict[str, Any]] = Field(default_factory=list, description="Position details")
    
    # Trading context
    trading_mode: str = Field(default=TradingMode.PAPER, description="paper or live")
    
    # Metadata
    source: str = Field(default="pulse", description="Source system")
    version: str = Field(default="1.0", description="Schema version")


class PulseStatus(BaseModel):
    """PULSE_STATUS - Heartbeat with trading mode and market state.
    
    Sent periodically so Edge knows Pulse is alive and in which mode.
    Also used for circuit breaker health checks.
    """
    command_type: str = Field(default=CommandType.PULSE_STATUS, description="Command type identifier")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(), description="ISO timestamp")
    
    # Status
    status: str = Field(default="online", description="Server status")
    running: bool = Field(description="Whether trading loop is running")
    paused: bool = Field(description="Whether trading is paused")
    
    # Mode
    trading_mode: str = Field(default=TradingMode.PAPER, description="paper or live")
    market_state: str = Field(default=MarketState.CLOSED, description="open, closed, pre_market, after_hours")
    market_open: bool = Field(description="Whether market is currently open")
    
    # Engine details
    simulate_24_7: bool = Field(description="Whether 24/7 simulation is enabled")
    market_hours_only: bool = Field(description="Whether trading is market hours only")
    
    # Multi-market support (NEW)
    open_markets: list[str] = Field(default=[], description="List of currently open markets (US, HK, AU, etc.)")
    
    # Dependencies
    yfinance: bool = Field(description="Whether yfinance is available")
    telegram: bool = Field(description="Whether Telegram is running")
    ws_clients: int = Field(description="Number of WebSocket clients")
    brokers_connected: int = Field(description="Number of connected brokers")
    
    # Metadata
    source: str = Field(default="pulse", description="Source system")
    version: str = Field(default="1.0", description="Schema version")


class BrokerStatus(BaseModel):
    """BROKER_STATUS - Broker connectivity status.
    
    Broadcast when broker connection state changes.
    """
    command_type: str = Field(default=CommandType.BROKER_STATUS, description="Command type identifier")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(), description="ISO timestamp")
    
    # Broker details
    broker_id: str = Field(description="Broker identifier")
    broker_name: str = Field(default="", description="Broker display name")
    state: str = Field(description="connected, disconnected, or error")
    
    # Connection details
    connected: bool = Field(description="Whether broker is connected")
    error_message: str = Field(default="", description="Error message if disconnected/error")
    last_heartbeat: str = Field(default="", description="Last successful heartbeat timestamp")
    
    # Trading mode context
    trading_mode: str = Field(default=TradingMode.PAPER, description="paper or live")
    
    # Metadata
    source: str = Field(default="pulse", description="Source system")
    version: str = Field(default="1.0", description="Schema version")


class AutoStopTriggered(BaseModel):
    """AUTO_STOP_TRIGGERED - Auto-stop event fired.
    
    Broadcast when an auto-stop rule is triggered.
    """
    command_type: str = Field(default=CommandType.AUTO_STOP_TRIGGERED, description="Command type identifier")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(), description="ISO timestamp")
    
    # Stop details
    symbol: str = Field(description="Ticker symbol")
    stop_type: str = Field(description="Type of stop: trailing, hard, time-based, etc.")
    
    # Execution details
    triggered_price: float = Field(description="Price that triggered the stop")
    current_price: float = Field(description="Current market price")
    quantity: float = Field(description="Position quantity being stopped")
    
    # Position context
    avg_entry: float = Field(description="Average entry price")
    unrealized_pnl: float = Field(description="Unrealized P&L at trigger")
    unrealized_pnl_percent: float = Field(description="Unrealized P&L percentage")
    
    # Stop configuration that triggered
    stop_threshold: float = Field(description="Stop threshold value")
    stop_is_percent: bool = Field(description="Whether stop threshold is a percentage")
    
    # Trading context
    trading_mode: str = Field(default=TradingMode.PAPER, description="paper or live")
    broker_id: str = Field(default="", description="Broker identifier")
    reason: str = Field(default="", description="Detailed reason")
    
    # Metadata
    source: str = Field(default="pulse", description="Source system")
    version: str = Field(default="1.0", description="Schema version")


# Type mapping for command deserialization
COMMAND_TYPE_MAP: Dict[str, type] = {
    CommandType.ORDER_FILLED: OrderFilled,
    CommandType.POSITION_UPDATE: PositionUpdate,
    CommandType.ACCOUNT_UPDATE: AccountUpdate,
    CommandType.PULSE_STATUS: PulseStatus,
    CommandType.BROKER_STATUS: BrokerStatus,
    CommandType.AUTO_STOP_TRIGGERED: AutoStopTriggered,
}


def get_command_class(command_type: str) -> Optional[type]:
    """Get the command class for a given command type string."""
    return COMMAND_TYPE_MAP.get(command_type)