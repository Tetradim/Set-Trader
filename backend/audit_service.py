"""Structured Audit Log Service.

Logs all significant actions for debugging and compliance:
- User setting changes
- Manual sells
- Rebracket triggers
- Broker API calls (success/failure)
- Trading engine events
"""
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Literal
from enum import Enum

import deps


class AuditEventType(str, Enum):
    # Settings
    SETTING_CHANGED = "SETTING_CHANGED"
    TICKER_CREATED = "TICKER_CREATED"
    TICKER_UPDATED = "TICKER_UPDATED"
    TICKER_DELETED = "TICKER_DELETED"
    
    # Trading
    BUY_EXECUTED = "BUY_EXECUTED"
    SELL_EXECUTED = "SELL_EXECUTED"
    STOP_TRIGGERED = "STOP_TRIGGERED"
    TRAILING_STOP_TRIGGERED = "TRAILING_STOP_TRIGGERED"
    MANUAL_SELL = "MANUAL_SELL"
    REBRACKET_TRIGGERED = "REBRACKET_TRIGGERED"
    
    # Broker
    BROKER_CONNECTED = "BROKER_CONNECTED"
    BROKER_DISCONNECTED = "BROKER_DISCONNECTED"
    BROKER_API_CALL = "BROKER_API_CALL"
    BROKER_API_ERROR = "BROKER_API_ERROR"
    BROKER_RATE_LIMITED = "BROKER_RATE_LIMITED"
    BROKER_CIRCUIT_OPEN = "BROKER_CIRCUIT_OPEN"
    BROKER_CIRCUIT_CLOSED = "BROKER_CIRCUIT_CLOSED"
    
    # Engine
    ENGINE_STARTED = "ENGINE_STARTED"
    ENGINE_STOPPED = "ENGINE_STOPPED"
    ENGINE_PAUSED = "ENGINE_PAUSED"
    ENGINE_RESUMED = "ENGINE_RESUMED"
    MODE_SWITCHED = "MODE_SWITCHED"
    
    # Alerts
    TELEGRAM_SENT = "TELEGRAM_SENT"
    TELEGRAM_FAILED = "TELEGRAM_FAILED"
    
    # System
    SYSTEM_ERROR = "SYSTEM_ERROR"
    PRICE_FEED_SWITCHED = "PRICE_FEED_SWITCHED"


class AuditService:
    """Service for structured audit logging."""
    
    def __init__(self):
        self.collection_name = "audit_logs"
    
    async def log(
        self,
        event_type: AuditEventType,
        details: Dict[str, Any],
        symbol: Optional[str] = None,
        broker_id: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> str:
        """
        Log an audit event.
        
        Returns the inserted document ID as string.
        """
        doc = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type.value,
            "symbol": symbol,
            "broker_id": broker_id,
            "success": success,
            "error_message": error_message,
            "details": details,
        }
        
        result = await deps.db[self.collection_name].insert_one(doc)
        
        # Also log to console for immediate visibility
        status = "OK" if success else "FAIL"
        sym_str = f"[{symbol}]" if symbol else ""
        broker_str = f"[{broker_id}]" if broker_id else ""
        deps.logger.info(f"AUDIT {event_type.value} {sym_str}{broker_str} [{status}] {details}")
        
        return str(result.inserted_id)
    
    async def log_setting_change(
        self,
        setting_name: str,
        old_value: Any,
        new_value: Any,
        source: str = "user",
    ):
        """Log a settings change."""
        await self.log(
            AuditEventType.SETTING_CHANGED,
            {
                "setting": setting_name,
                "old_value": old_value,
                "new_value": new_value,
                "source": source,
            },
        )
    
    async def log_ticker_change(
        self,
        event_type: Literal["created", "updated", "deleted"],
        symbol: str,
        changes: Optional[Dict[str, Any]] = None,
    ):
        """Log a ticker configuration change."""
        type_map = {
            "created": AuditEventType.TICKER_CREATED,
            "updated": AuditEventType.TICKER_UPDATED,
            "deleted": AuditEventType.TICKER_DELETED,
        }
        await self.log(
            type_map[event_type],
            {"changes": changes or {}},
            symbol=symbol,
        )
    
    async def log_trade(
        self,
        event_type: AuditEventType,
        symbol: str,
        price: float,
        quantity: float,
        reason: str,
        pnl: Optional[float] = None,
        broker_id: Optional[str] = None,
        order_result: Optional[Dict] = None,
    ):
        """Log a trade execution."""
        await self.log(
            event_type,
            {
                "price": price,
                "quantity": quantity,
                "reason": reason,
                "pnl": pnl,
                "total_value": round(price * quantity, 2),
                "order_result": order_result,
            },
            symbol=symbol,
            broker_id=broker_id,
        )
    
    async def log_broker_api(
        self,
        broker_id: str,
        endpoint: str,
        method: str,
        success: bool,
        response_time_ms: Optional[float] = None,
        error_message: Optional[str] = None,
        request_data: Optional[Dict] = None,
    ):
        """Log a broker API call."""
        await self.log(
            AuditEventType.BROKER_API_CALL if success else AuditEventType.BROKER_API_ERROR,
            {
                "endpoint": endpoint,
                "method": method,
                "response_time_ms": response_time_ms,
                "request_data": request_data,
            },
            broker_id=broker_id,
            success=success,
            error_message=error_message,
        )
    
    async def log_rebracket(
        self,
        symbol: str,
        direction: str,
        old_buy: float,
        old_sell: float,
        new_buy: float,
        new_sell: float,
        trigger_price: float,
    ):
        """Log a rebracket event."""
        await self.log(
            AuditEventType.REBRACKET_TRIGGERED,
            {
                "direction": direction,
                "old_buy": old_buy,
                "old_sell": old_sell,
                "new_buy": new_buy,
                "new_sell": new_sell,
                "trigger_price": trigger_price,
            },
            symbol=symbol,
        )
    
    async def log_rate_limit(
        self,
        broker_id: str,
        current_count: int,
        limit: int,
        window_seconds: int,
    ):
        """Log a rate limit hit."""
        await self.log(
            AuditEventType.BROKER_RATE_LIMITED,
            {
                "current_count": current_count,
                "limit": limit,
                "window_seconds": window_seconds,
            },
            broker_id=broker_id,
            success=False,
            error_message=f"Rate limit exceeded: {current_count}/{limit} requests in {window_seconds}s",
        )
    
    async def log_circuit_breaker(
        self,
        broker_id: str,
        state: Literal["open", "closed"],
        failure_count: int,
        threshold: int,
    ):
        """Log circuit breaker state change."""
        event = AuditEventType.BROKER_CIRCUIT_OPEN if state == "open" else AuditEventType.BROKER_CIRCUIT_CLOSED
        await self.log(
            event,
            {
                "state": state,
                "failure_count": failure_count,
                "threshold": threshold,
            },
            broker_id=broker_id,
            success=state == "closed",
        )
    
    async def get_logs(
        self,
        event_types: Optional[list] = None,   # list → $in query; single-item list works too
        event_type: Optional[str] = None,      # legacy single-type param (kept for back-compat)
        symbol: Optional[str] = None,
        broker_id: Optional[str] = None,
        success: Optional[bool] = None,
        limit: int = 100,
        skip: int = 0,
    ) -> list:
        """Query audit logs with filters."""
        query = {}
        # event_types (list) takes precedence over legacy single event_type
        effective_types = event_types or ([event_type] if event_type else None)
        if effective_types:
            if len(effective_types) == 1:
                query["event_type"] = effective_types[0]
            else:
                query["event_type"] = {"$in": effective_types}
        if symbol:
            query["symbol"] = symbol
        if broker_id:
            query["broker_id"] = broker_id
        if success is not None:
            query["success"] = success

        cursor = deps.db[self.collection_name].find(
            query,
            {"_id": 0},
        ).sort("timestamp", -1).skip(skip).limit(limit)

        return await cursor.to_list(limit)


# Singleton instance
audit_service = AuditService()
