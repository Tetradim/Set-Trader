"""Shared module for Edge ↔ Pulse integration.

This module provides:
- commands.py: Command schemas (ORDER_FILLED, POSITION_UPDATE, etc.)
- mongo_client.py: MongoDB client for sending commands to Edge
- commands_utils.py: Command builders and serializers
- edge_integration.py: Integration helper for trading engine hooks
"""
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
    COMMAND_TYPE_MAP,
    get_command_class,
)

from shared.mongo_client import (
    EdgeMongoClient,
    edge_client,
    init_edge_client,
)

from shared.commands_utils import (
    build_order_filled,
    build_order_filled_from_trade,
    build_position_update,
    build_position_update_from_engine,
    build_account_update,
    build_pulse_status,
    build_broker_status,
    build_auto_stop_triggered,
    serialize_command,
    serialize_command_for_json,
    batch_position_updates,
)

from shared.edge_integration import (
    send_order_filled_command,
    send_position_update_command,
    send_account_update_command,
    send_pulse_status_command,
    send_broker_status_command,
    send_auto_stop_triggered_command,
    start_edge_heartbeat,
    on_trade_executed,
)

__all__ = [
    # Commands
    "CommandType",
    "TradingMode",
    "MarketState", 
    "BrokerConnectionState",
    "OrderFilled",
    "PositionUpdate",
    "AccountUpdate",
    "PulseStatus",
    "BrokerStatus",
    "AutoStopTriggered",
    "COMMAND_TYPE_MAP",
    "get_command_class",
    
    # MongoDB client
    "EdgeMongoClient",
    "edge_client",
    "init_edge_client",
    
    # Command builders
    "build_order_filled",
    "build_order_filled_from_trade",
    "build_position_update",
    "build_position_update_from_engine",
    "build_account_update",
    "build_pulse_status",
    "build_broker_status",
    "build_auto_stop_triggered",
    "serialize_command",
    "serialize_command_for_json",
    "batch_position_updates",
    
    # Edge integration
    "send_order_filled_command",
    "send_position_update_command",
    "send_account_update_command",
    "send_pulse_status_command",
    "send_broker_status_command",
    "send_auto_stop_triggered_command",
    "start_edge_heartbeat",
    "on_trade_executed",
]