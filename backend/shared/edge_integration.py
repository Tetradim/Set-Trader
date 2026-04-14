"""Edge integration helper for sending commands to Edge.

This module provides integration between Pulse's trading engine and Edge's MongoDB.
It sends commands after trade fills and handles the heartbeat.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import deps
from shared import (
    edge_client,
    build_order_filled,
    build_position_update,
    build_account_update,
    build_pulse_status,
    build_broker_status,
    build_auto_stop_triggered,
    TradingMode,
    MarketState,
)

logger = logging.getLogger("SentinelPulse.EdgeIntegration")


async def send_order_filled_command(
    symbol: str,
    side: str,
    quantity: float,
    price: float,
    order_type: str = "market",
    avg_entry: float = 0.0,
    position_qty: float = 0.0,
    pnl: float = 0.0,
    trading_mode: str = "paper",
    broker_id: str = "",
    reason: str = "",
) -> bool:
    """Send ORDER_FILLED command to Edge after a trade executes.
    
    Args:
        symbol: Ticker symbol.
        side: BUY or SELL.
        quantity: Number of shares.
        price: Fill price.
        order_type: Order type (market, limit, stop).
        avg_entry: Average entry price.
        position_qty: Position quantity after fill.
        pnl: Realized P&L (for sells).
        trading_mode: paper or live.
        broker_id: Broker identifier.
        reason: Execution reason.
        
    Returns:
        True if command was sent successfully.
    """
    if not edge_client.is_enabled or not edge_client.is_connected:
        return False
    
    # Calculate P&L percentage
    pnl_percent = 0.0
    if avg_entry > 0 and side.upper() == "SELL":
        pnl_percent = ((price - avg_entry) / avg_entry) * 100
    
    order_cmd = build_order_filled(
        symbol=symbol,
        side=side,
        quantity=quantity,
        price=price,
        order_type=order_type,
        avg_entry=avg_entry,
        position_qty=position_qty,
        pnl=pnl,
        pnl_percent=pnl_percent,
        trading_mode=trading_mode,
        broker_id=broker_id,
        reason=reason,
    )
    
    result = await edge_client.send_order_filled(order_cmd)
    if result:
        logger.debug(f"Edge: ORDER_FILLED sent for {symbol}")
    return result


async def send_position_update_command(
    symbol: str,
    quantity: float,
    avg_entry: float,
    current_price: float,
    trading_mode: str = "paper",
    broker_id: str = "",
) -> bool:
    """Send POSITION_UPDATE command to Edge.
    
    Args:
        symbol: Ticker symbol.
        quantity: Number of shares held.
        avg_entry: Average entry price.
        current_price: Current market price.
        trading_mode: paper or live.
        broker_id: Broker identifier.
        
    Returns:
        True if command was sent successfully.
    """
    if not edge_client.is_enabled or not edge_client.is_connected:
        return False
    
    if quantity <= 0:
        return False
    
    pos_update = build_position_update(
        symbol=symbol,
        quantity=quantity,
        avg_entry=avg_entry,
        current_price=current_price,
        trading_mode=trading_mode,
        broker_id=broker_id,
    )
    
    return await edge_client.send_position_update(pos_update)


async def send_account_update_command() -> bool:
    """Send ACCOUNT_UPDATE command to Edge.
    
    Gathers current account metrics and sends to Edge.
    
    Returns:
        True if command was sent successfully.
    """
    if not edge_client.is_enabled or not edge_client.is_connected:
        return False
    
    try:
        # Get account balances
        balance_doc = await deps.db.settings.find_one({"key": "account_balance"}, {"_id": 0})
        account_balance = round(balance_doc.get("value", 0), 2) if balance_doc else 0
        
        cash_doc = await deps.db.settings.find_one({"key": "cash_reserve"}, {"_id": 0})
        cash_reserve = round(cash_doc.get("value", 0), 2) if cash_doc else 0
        
        # Get allocated capital
        tickers = await deps.db.tickers.find({}, {"_id": 0, "base_power": 1}).to_list(100)
        allocated = round(sum(t.get("base_power", 0) for t in tickers), 2)
        available = round(account_balance - allocated, 2)
        
        # Get positions
        positions = []
        total_unrealized_pnl = 0.0
        
        for sym, position in deps.engine._positions.items():
            if position.get("qty", 0) <= 0:
                continue
            
            current_price = await deps.price_service.get_price(sym)
            qty = position.get("qty", 0)
            avg_entry = position.get("avg_entry", 0)
            
            market_value = round(qty * current_price, 2)
            cost_basis = round(qty * avg_entry, 2)
            unrealized_pnl = round(market_value - cost_basis, 2)
            total_unrealized_pnl += unrealized_pnl
            
            positions.append({
                "symbol": sym,
                "quantity": qty,
                "avg_entry": avg_entry,
                "current_price": current_price,
                "market_value": market_value,
                "unrealized_pnl": unrealized_pnl,
            })
        
        # Get total realized P&L
        profits_list = await deps.db.profits.find({}, {"_id": 0}).to_list(100)
        total_realized_pnl = round(sum(p.get("total_pnl", 0) for p in profits_list), 2)
        
        trading_mode = "paper" if deps.engine.simulate_24_7 else "live"
        
        acc_update = build_account_update(
            account_balance=account_balance,
            allocated=allocated,
            available=available,
            cash_reserve=cash_reserve,
            total_realized_pnl=total_realized_pnl,
            total_unrealized_pnl=total_unrealized_pnl,
            positions=positions,
            trading_mode=trading_mode,
        )
        
        return await edge_client.send_account_update(acc_update)
    except Exception as e:
        logger.error(f"Failed to send ACCOUNT_UPDATE: {e}")
        return False


def determine_market_state() -> str:
    """Determine the current market state.
    
    Returns:
        Market state string: open, closed, pre_market, after_hours
    """
    if deps.engine.simulate_24_7:
        return MarketState.OPEN
    
    if not deps.engine.is_market_open():
        return MarketState.CLOSED
    
    # Could add pre_market and after_hours detection here
    return MarketState.OPEN


async def send_pulse_status_command() -> bool:
    """Send PULSE_STATUS heartbeat to Edge.
    
    Returns:
        True if command was sent successfully.
    """
    if not edge_client.is_enabled or not edge_client.is_connected:
        return False
    
    trading_mode = "paper" if deps.engine.simulate_24_7 else "live"
    market_state = determine_market_state()
    
    connected_brokers = sum(1 for _ in deps.broker_mgr._adapters)
    
    # Get list of open markets (for multi-market support)
    open_markets = deps.engine.get_open_markets()
    
    status = build_pulse_status(
        running=deps.engine.running,
        paused=deps.engine.paused,
        trading_mode=trading_mode,
        market_state=market_state,
        market_open=deps.engine.is_market_open(),
        simulate_24_7=deps.engine.simulate_24_7,
        market_hours_only=deps.engine.market_hours_only,
        yfinance=deps.YF_AVAILABLE,
        telegram=deps.telegram_service.running,
        ws_clients=len(deps.ws_manager.active),
        brokers_connected=connected_brokers,
        open_markets=open_markets,  # NEW: multi-market support
    )
    
    return await edge_client.send_pulse_status(status)


async def send_broker_status_command(
    broker_id: str,
    broker_name: str,
    connected: bool,
    error_message: str = "",
) -> bool:
    """Send BROKER_STATUS update to Edge.
    
    Args:
        broker_id: Broker identifier.
        broker_name: Broker display name.
        connected: Whether broker is connected.
        error_message: Error message if disconnected/error.
        
    Returns:
        True if command was sent successfully.
    """
    if not edge_client.is_enabled or not edge_client.is_connected:
        return False
    
    trading_mode = "paper" if deps.engine.simulate_24_7 else "live"
    state = "connected" if connected else ("error" if error_message else "disconnected")
    
    broker_status = build_broker_status(
        broker_id=broker_id,
        broker_name=broker_name,
        state=state,
        connected=connected,
        error_message=error_message,
        trading_mode=trading_mode,
    )
    
    return await edge_client.send_broker_status(broker_status)


async def send_auto_stop_triggered_command(
    symbol: str,
    stop_type: str,
    triggered_price: float,
    current_price: float,
    quantity: float,
    avg_entry: float,
    stop_threshold: float,
    stop_is_percent: bool,
    reason: str = "",
) -> bool:
    """Send AUTO_STOP_TRIGGERED event to Edge.
    
    Args:
        symbol: Ticker symbol.
        stop_type: Type of stop (trailing, hard, time-based).
        triggered_price: Price that triggered the stop.
        current_price: Current market price.
        quantity: Position quantity being stopped.
        avg_entry: Average entry price.
        stop_threshold: Stop threshold value.
        stop_is_percent: Whether stop threshold is a percentage.
        reason: Detailed reason.
        
    Returns:
        True if command was sent successfully.
    """
    if not edge_client.is_enabled or not edge_client.is_connected:
        return False
    
    trading_mode = "paper" if deps.engine.simulate_24_7 else "live"
    
    # Get broker_id from ticker
    ticker = await deps.db.tickers.find_one({"symbol": symbol}, {"_id": 0})
    broker_id = ticker.get("broker_id", "") if ticker else ""
    
    stop_event = build_auto_stop_triggered(
        symbol=symbol,
        stop_type=stop_type,
        triggered_price=triggered_price,
        current_price=current_price,
        quantity=quantity,
        avg_entry=avg_entry,
        stop_threshold=stop_threshold,
        stop_is_percent=stop_is_percent,
        trading_mode=trading_mode,
        broker_id=broker_id,
        reason=reason,
    )
    
    return await edge_client.send_auto_stop_triggered(stop_event)


# --- Background tasks ---


async def pulse_status_heartbeat_loop(interval: int = 30):
    """Background task to send PULSE_STATUS heartbeat to Edge.
    
    Args:
        interval: Seconds between heartbeats.
    """
    while True:
        try:
            await send_pulse_status_command()
        except Exception as e:
            logger.error(f"Failed to send PULSE_STATUS heartbeat: {e}")
        await asyncio.sleep(interval)


async def start_edge_heartbeat():
    """Start the Edge heartbeat background task."""
    if not edge_client.is_enabled:
        logger.info("Edge integration disabled - skipping heartbeat")
        return
    
    logger.info("Starting Edge heartbeat task")
    asyncio.create_task(pulse_status_heartbeat_loop())


# --- Trading engine hooks ---


async def on_trade_executed(trade_data: dict) -> None:
    """Hook to call after trade execution.
    
    This function is called by the trading engine after a trade is executed.
    It sends an ORDER_FILLED command to Edge.
    
    Args:
        trade_data: Trade record dictionary.
    """
    try:
        # Get current position
        symbol = trade_data.get("symbol", "")
        position = deps.engine._positions.get(symbol, {})
        position_qty = position.get("qty", 0)
        avg_entry = position.get("avg_entry", 0)
        
        await send_order_filled_command(
            symbol=symbol,
            side=trade_data.get("side", ""),
            quantity=trade_data.get("quantity", 0),
            price=trade_data.get("price", 0),
            order_type=trade_data.get("order_type", "market"),
            avg_entry=avg_entry,
            position_qty=position_qty,
            pnl=trade_data.get("pnl", 0),
            trading_mode=trade_data.get("trading_mode", "paper"),
            broker_id=trade_data.get("broker_id", ""),
            reason=trade_data.get("reason", ""),
        )
    except Exception as e:
        logger.error(f"Failed to send ORDER_FILLED for {trade_data.get('symbol')}: {e}")