"""Command builders and serializers for Edge integration.

Provides convenience functions to build command documents from
existing trade and position data in the Pulse system.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from shared.commands import (
    CommandType,
    TradingMode,
    MarketState,
    BrokerConnectionState,
    OrderFilled,
    PositionUpdate,
    AccountUpdate,
    PulseStatus,
    BrokerStatus,
    AutoStopTriggered,
)

logger = logging.getLogger("SentinelPulse.CommandsUtils")


# --- OrderFilled builders ---

def build_order_filled(
    symbol: str,
    side: str,
    quantity: float,
    price: float,
    order_type: str = "market",
    avg_entry: float = 0.0,
    position_qty: float = 0.0,
    pnl: float = 0.0,
    pnl_percent: float = 0.0,
    trading_mode: str = "paper",
    broker_id: str = "",
    reason: str = "",
    order_id: str = "",
    execution_id: str = "",
) -> OrderFilled:
    """Build an ORDER_FILLED command from trade execution data.
    
    Args:
        symbol: Ticker symbol.
        side: BUY or SELL.
        quantity: Number of shares.
        price: Fill price.
        order_type: Order type (market, limit, stop).
        avg_entry: Average entry price (for position tracking).
        position_qty: Position quantity after fill.
        pnl: Realized P&L (for sells).
        pnl_percent: P&L as percentage.
        trading_mode: paper or live.
        broker_id: Broker identifier.
        reason: Execution reason.
        order_id: Broker order ID.
        execution_id: Execution/ fill ID.
        
    Returns:
        OrderFilled command document.
    """
    return OrderFilled(
        symbol=symbol,
        side=side.upper(),
        quantity=quantity,
        price=price,
        total_value=round(quantity * price, 2),
        order_type=order_type,
        order_id=order_id,
        execution_id=execution_id,
        avg_entry=avg_entry,
        position_qty=position_qty,
        pnl=round(pnl, 2),
        pnl_percent=round(pnl_percent, 2),
        trading_mode=trading_mode,
        broker_id=broker_id,
        reason=reason,
    )


def build_order_filled_from_trade(
    trade: Dict[str, Any],
    position_qty: float = 0.0,
    avg_entry: float = 0.0,
) -> OrderFilled:
    """Build an ORDER_FILLED command from a trade record.
    
    Args:
        trade: Trade record from trades collection.
        position_qty: Current position quantity.
        avg_entry: Current average entry price.
        
    Returns:
        OrderFilled command document.
    """
    return build_order_filled(
        symbol=trade.get("symbol", ""),
        side=trade.get("side", ""),
        quantity=trade.get("quantity", 0),
        price=trade.get("price", 0),
        order_type=trade.get("order_type", "market"),
        avg_entry=avg_entry,
        position_qty=position_qty,
        pnl=trade.get("pnl", 0),
        pnl_percent=0.0,  # Calculate separately if needed
        trading_mode=trade.get("trading_mode", "paper"),
        broker_id=trade.get("broker_id", ""),
        reason=trade.get("reason", ""),
    )


# --- PositionUpdate builders ---

def build_position_update(
    symbol: str,
    quantity: float,
    avg_entry: float,
    current_price: float,
    trading_mode: str = "paper",
    broker_id: str = "",
) -> PositionUpdate:
    """Build a POSITION_UPDATE command.
    
    Args:
        symbol: Ticker symbol.
        quantity: Number of shares held.
        avg_entry: Average entry price.
        current_price: Current market price.
        trading_mode: paper or live.
        broker_id: Broker identifier.
        
    Returns:
        PositionUpdate command document.
    """
    market_value = round(quantity * current_price, 2)
    cost_basis = round(quantity * avg_entry, 2)
    unrealized_pnl = round(market_value - cost_basis, 2)
    
    # Calculate percentage
    unrealized_pnl_percent = 0.0
    if cost_basis > 0:
        unrealized_pnl_percent = round((unrealized_pnl / cost_basis) * 100, 2)
    
    return PositionUpdate(
        symbol=symbol,
        quantity=quantity,
        avg_entry=avg_entry,
        current_price=current_price,
        market_value=market_value,
        cost_basis=cost_basis,
        unrealized_pnl=unrealized_pnl,
        unrealized_pnl_percent=unrealized_pnl_percent,
        trading_mode=trading_mode,
        broker_id=broker_id,
    )


def build_position_update_from_engine(
    symbol: str,
    position: Dict[str, float],
    current_price: float,
    trading_mode: str = "paper",
) -> PositionUpdate:
    """Build a POSITION_UPDATE from engine position data.
    
    Args:
        symbol: Ticker symbol.
        position: Position dict from engine (with qty, avg_entry keys).
        current_price: Current market price.
        trading_mode: paper or live.
        
    Returns:
        PositionUpdate command document.
    """
    return build_position_update(
        symbol=symbol,
        quantity=position.get("qty", 0),
        avg_entry=position.get("avg_entry", 0),
        current_price=current_price,
        trading_mode=trading_mode,
        broker_id=position.get("broker_id", ""),
    )


# --- AccountUpdate builders ---

def build_account_update(
    account_balance: float,
    allocated: float,
    available: float,
    cash_reserve: float,
    total_realized_pnl: float,
    total_unrealized_pnl: float,
    positions: List[Dict[str, Any]],
    trading_mode: str = "paper",
) -> AccountUpdate:
    """Build an ACCOUNT_UPDATE command.
    
    Args:
        account_balance: Total account balance.
        allocated: Allocated capital.
        available: Available capital.
        cash_reserve: Cash reserve amount.
        total_realized_pnl: Total realized P&L.
        total_unrealized_pnl: Total unrealized P&L.
        positions: List of position dicts.
        trading_mode: paper or live.
        
    Returns:
        AccountUpdate command document.
    """
    return AccountUpdate(
        account_balance=round(account_balance, 2),
        allocated=round(allocated, 2),
        available=round(available, 2),
        cash_reserve=round(cash_reserve, 2),
        total_realized_pnl=round(total_realized_pnl, 2),
        total_unrealized_pnl=round(total_unrealized_pnl, 2),
        open_positions=len(positions),
        positions=positions,
        trading_mode=trading_mode,
    )


# --- PulseStatus builders ---

def build_pulse_status(
    running: bool,
    paused: bool,
    trading_mode: str,
    market_state: str,
    market_open: bool,
    simulate_24_7: bool = False,
    market_hours_only: bool = True,
    yfinance: bool = False,
    telegram: bool = False,
    ws_clients: int = 0,
    brokers_connected: int = 0,
    open_markets: list[str] = None,
) -> PulseStatus:
    """Build a PULSE_STATUS heartbeat command.
    
    Args:
        running: Whether trading loop is running.
        paused: Whether trading is paused.
        trading_mode: paper or live.
        market_state: open, closed, pre_market, after_hours.
        market_open: Whether market is currently open.
        simulate_24_7: Whether 24/7 simulation is enabled.
        market_hours_only: Whether trading is market hours only.
        yfinance: Whether yfinance is available.
        telegram: Whether Telegram is running.
        ws_clients: Number of WebSocket clients.
        brokers_connected: Number of connected brokers.
        
    Returns:
        PulseStatus command document.
    """
    return PulseStatus(
        status="online",
        running=running,
        paused=paused,
        trading_mode=trading_mode,
        market_state=market_state,
        market_open=market_open,
        simulate_24_7=simulate_24_7,
        market_hours_only=market_hours_only,
        yfinance=yfinance,
        telegram=telegram,
        ws_clients=ws_clients,
        brokers_connected=brokers_connected,
        open_markets=open_markets or [],
    )


# --- BrokerStatus builders ---

def build_broker_status(
    broker_id: str,
    broker_name: str,
    state: str,
    connected: bool,
    error_message: str = "",
    trading_mode: str = "paper",
) -> BrokerStatus:
    """Build a BROKER_STATUS command.
    
    Args:
        broker_id: Broker identifier.
        broker_name: Broker display name.
        state: connected, disconnected, or error.
        connected: Whether broker is connected.
        error_message: Error message if disconnected/error.
        trading_mode: paper or live.
        
    Returns:
        BrokerStatus command document.
    """
    return BrokerStatus(
        broker_id=broker_id,
        broker_name=broker_name,
        state=state,
        connected=connected,
        error_message=error_message,
        last_heartbeat=datetime.now(timezone.utc).isoformat(),
        trading_mode=trading_mode,
    )


# --- AutoStopTriggered builders ---

def build_auto_stop_triggered(
    symbol: str,
    stop_type: str,
    triggered_price: float,
    current_price: float,
    quantity: float,
    avg_entry: float,
    stop_threshold: float,
    stop_is_percent: bool,
    trading_mode: str = "paper",
    broker_id: str = "",
    reason: str = "",
) -> AutoStopTriggered:
    """Build an AUTO_STOP_TRIGGERED command.
    
    Args:
        symbol: Ticker symbol.
        stop_type: Type of stop (trailing, hard, time-based, etc.).
        triggered_price: Price that triggered the stop.
        current_price: Current market price.
        quantity: Position quantity being stopped.
        avg_entry: Average entry price.
        stop_threshold: Stop threshold value.
        stop_is_percent: Whether stop threshold is a percentage.
        trading_mode: paper or live.
        broker_id: Broker identifier.
        reason: Detailed reason.
        
    Returns:
        AutoStopTriggered command document.
    """
    market_value = round(quantity * current_price, 2)
    cost_basis = round(quantity * avg_entry, 2)
    unrealized_pnl = round(market_value - cost_basis, 2)
    
    unrealized_pnl_percent = 0.0
    if cost_basis > 0:
        unrealized_pnl_percent = round((unrealized_pnl / cost_basis) * 100, 2)
    
    return AutoStopTriggered(
        symbol=symbol,
        stop_type=stop_type,
        triggered_price=triggered_price,
        current_price=current_price,
        quantity=quantity,
        avg_entry=avg_entry,
        unrealized_pnl=unrealized_pnl,
        unrealized_pnl_percent=unrealized_pnl_percent,
        stop_threshold=stop_threshold,
        stop_is_percent=stop_is_percent,
        trading_mode=trading_mode,
        broker_id=broker_id,
        reason=reason,
    )


# --- Serialization helpers ---

def serialize_command(command: Any) -> Dict[str, Any]:
    """Serialize a command to a dictionary for MongoDB insertion.
    
    Args:
        command: Command instance (OrderFilled, PositionUpdate, etc.).
        
    Returns:
        Dictionary representation.
    """
    return command.model_dump()


def serialize_command_for_json(command: Any) -> Dict[str, Any]:
    """Serialize a command to JSON-safe dictionary.
    
    Handles datetime conversion and other nonJSON-safe types.
    
    Args:
        command: Command instance.
        
    Returns:
        JSON-safe dictionary.
    """
    data = command.model_dump()
    
    # Ensure all datetime fields are strings
    if "timestamp" in data and isinstance(data["timestamp"], datetime):
        data["timestamp"] = data["timestamp"].isoformat()
    
    return data


# --- Batch helpers ---

def batch_position_updates(
    positions: Dict[str, Dict[str, float]],
    prices: Dict[str, float],
    trading_mode: str = "paper",
) -> List[PositionUpdate]:
    """Build batch position updates for multiple positions.
    
    Args:
        positions: Dict mapping symbol -> position data (qty, avg_entry).
        prices: Dict mapping symbol -> current price.
        trading_mode: paper or live.
        
    Returns:
        List of PositionUpdate commands.
    """
    updates = []
    
    for symbol, position in positions.items():
        if position.get("qty", 0) <= 0:
            continue
        
        current_price = prices.get(symbol, 0)
        if current_price <= 0:
            continue
        
        update = build_position_update_from_engine(
            symbol=symbol,
            position=position,
            current_price=current_price,
            trading_mode=trading_mode,
        )
        updates.append(update)
    
    return updates