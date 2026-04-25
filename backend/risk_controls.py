"""Risk Controls Module.

Provides pre-trade risk gateway, kill switches, exposure limits, and trading controls.
"""
import os
import logging
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from fastapi import HTTPException, status


logger = logging.getLogger(__name__)


class KillSwitchLevel(str, Enum):
    """Hierarchical kill switch levels."""
    GLOBAL = "global"       # Full system halt
    DESK = "desk"          # All desks halted
    ACCOUNT = "account"     # Account-level halt
    STRATEGY = "strategy"   # Strategy-specific halt
    BROKER = "broker"      # Broker-specific halt


class OrderRestriction(str, Enum):
    """Order restrictions."""
    NONE = "none"
    CLOSE_ONLY = "close_only"     # Only close existing positions
    NO_NEW_ENTRIES = "no_new_entries"  # No new entry orders
    CANCEL_ALL = "cancel_all"     # Cancel all pending orders
    HARD_BLOCK = "hard_block"   # Block all trading


@dataclass
class ExposureLimit:
    """Exposure limit configuration."""
    limit_id: str
    level: str  # portfolio, account, sector, asset_class, symbol
    level_id: str  # specific ID at this level
    max_notional: float = 0.0
    max_daily_loss: float = 0.0
    max_position_size: float = 0.0
    max_orders_per_minute: int = 0
    soft_limit: float = 0.0  # Warning threshold
    is_enabled: bool = True
    
    # Tracking
    current_notional: float = 0.0
    current_position: float = 0.0
    daily_pnl: float = 0.0
    orders_count: int = 0


@dataclass
class KillSwitch:
    """Kill switch state."""
    switch_id: str
    level: KillSwitchLevel
    target_id: str  # desk/account/strategy/broker ID
    is_active: bool = False
    triggered_by: str = ""
    triggered_at: datetime = None
    reason: str = ""
    
    def activate(self, triggered_by: str, reason: str = ""):
        """Activate the kill switch."""
        self.is_active = True
        self.triggered_by = triggered_by
        self.triggered_at = datetime.utcnow()
        self.reason = reason
        
    def deactivate(self):
        """Deactivate the kill switch."""
        self.is_active = False
        self.triggered_by = ""
        self.triggered_at = None
        self.reason = ""


@dataclass 
class RiskCheckResult:
    """Result of a risk check."""
    is_allowed: bool
    restriction: OrderRestriction = OrderRestriction.NONE
    message: str = ""
    rejected_fields: Dict[str, Any] = field(default_factory=dict)


class RiskControls:
    """Risk controls manager."""
    
    def __init__(self):
        self._exposure_limits: Dict[str, ExposureLimit] = {}
        self._kill_switches: Dict[str, KillSwitch] = {}
        self._order_restrictions: Dict[str, OrderRestriction] = {}
        self._symbol_restrictions: set = set()
        self._fat_finger_limits: Dict[str, float] = {}  # symbol -> max order size
        
    def add_exposure_limit(self, limit: ExposureLimit):
        """Add or update an exposure limit."""
        self._exposure_limits[f"{limit.level}:{limit.level_id}"] = limit
        logger.info(f"Added exposure limit: {limit.limit_id}")
        
    def get_exposure_limit(self, level: str, level_id: str) -> Optional[ExposureLimit]:
        """Get an exposure limit."""
        return self._exposure_limits.get(f"{level}:{level_id}")
    
    def update_exposure(self, level: str, level_id: str, notional_delta: float = 0.0, 
                     position_delta: float = 0.0, pnl_delta: float = 0.0, order_count: int = 0):
        """Update current exposure for a limit."""
        key = f"{level}:{level_id}"
        if key in self._exposure_limits:
            limit = self._exposure_limits[key]
            limit.current_notional += notional_delta
            limit.current_position += position_delta
            limit.daily_pnl += pnl_delta
            limit.orders_count += order_count
            
    def check_exposure_limit(self, level: str, level_id: str) -> RiskCheckResult:
        """Check if exposure is within limits."""
        key = f"{level}:{level_id}"
        limit = self._exposure_limits.get(key)
        
        if not limit or not limit.is_enabled:
            return RiskCheckResult(is_allowed=True)
        
        # Check notional limit
        if limit.max_notional > 0 and limit.current_notional > limit.max_notional:
            return RiskCheckResult(
                is_allowed=False,
                restriction=OrderRestriction.HARD_BLOCK,
                message=f"Notional limit exceeded: ${limit.current_notional} > ${limit.max_notional}",
                rejected_fields={"notional": limit.current_notional}
            )
        
        # Check position size
        if limit.max_position_size > 0 and abs(limit.current_position) > limit.max_position_size:
            return RiskCheckResult(
                is_allowed=False,
                restriction=OrderRestriction.HARD_BLOCK,
                message=f"Position size exceeded: {limit.current_position} > {limit.max_position_size}",
                rejected_fields={"position": limit.current_position}
            )
        
        # Check daily loss
        if limit.max_daily_loss > 0 and limit.daily_pnl < -limit.max_daily_loss:
            return RiskCheckResult(
                is_allowed=False,
                restriction=OrderRestriction.HARD_BLOCK,
                message=f"Daily loss limit exceeded: ${limit.daily_pnl} < -${limit.max_daily_loss}",
                rejected_fields={"daily_pnl": limit.daily_pnl}
            )
        
        # Check soft limit warning
        if limit.soft_limit > 0 and limit.current_notional >= limit.soft_limit:
            logger.warning(f"Soft limit warning: {limit.limit_id} at {limit.current_notional >= limit.soft_limit*0.9:.1%}")
        
        # Check order rate
        if limit.max_orders_per_minute > 0 and limit.orders_count >= limit.max_orders_per_minute:
            return RiskCheckResult(
                is_allowed=False,
                restriction=OrderRestriction.CANCEL_ALL,
                message=f"Order rate limit exceeded: {limit.orders_count} >= {limit.max_orders_per_minute}/min",
                rejected_fields={"orders_count": limit.orders_count}
            )
        
        return RiskCheckResult(is_allowed=True)
    
    def add_kill_switch(self, level: KillSwitchLevel, target_id: str) -> KillSwitch:
        """Add a kill switch."""
        switch_id = f"{level.value}:{target_id}"
        if switch_id not in self._kill_switches:
            self._kill_switches[switch_id] = KillSwitch(
                switch_id=switch_id,
                level=level,
                target_id=target_id
            )
        return self._kill_switches[switch_id]
    
    def activate_kill_switch(self, level: KillSwitchLevel, target_id: str, 
                            triggered_by: str, reason: str = "") -> bool:
        """Activate a kill switch."""
        switch_id = f"{level.value}:{target_id}"
        if switch_id in self._kill_switches:
            self._kill_switches[switch_id].activate(triggered_by, reason)
            logger.warning(f"Kill switch activated: {switch_id} by {triggered_by}: {reason}")
            return True
        return False
    
    def deactivate_kill_switch(self, level: KillSwitchLevel, target_id: str) -> bool:
        """Deactivate a kill switch."""
        switch_id = f"{level.value}:{target_id}"
        if switch_id in self._kill_switches:
            self._kill_switches[switch_id].deactivate()
            logger.info(f"Kill switch deactivated: {switch_id}")
            return True
        return False
    
    def isTradingAllowed(self, account: str = None, desk: str = None,
                        strategy: str = None, broker: str = None) -> tuple:
        """Check if trading is allowed at any level.
        
        Returns (is_allowed, restriction, message)
        """
        # Check global kill switch
        if "global" in self._kill_switches:
            ks = self._kill_switches["global:global"]
            if ks.is_active:
                return (False, OrderRestriction.HARD_BLOCK, 
                       f"Global kill switch active: {ks.reason}")
        
        # Check desk kill switch
        if desk and f"desk:{desk}" in self._kill_switches:
            ks = self._kill_switches[f"desk:{desk}"]
            if ks.is_active:
                return (False, OrderRestriction.HARD_BLOCK,
                       f"Desk {desk} halted: {ks.reason}")
        
        # Check account kill switch
        if account and f"account:{account}" in self._kill_switches:
            ks = self._kill_switches[f"account:{account}"]
            if ks.is_active:
                return (False, OrderRestriction.HARD_BLOCK,
                       f"Account {account} halted: {ks.reason}")
        
        # Check strategy kill switch
        if strategy and f"strategy:{strategy}" in self._kill_switches:
            ks = self._kill_switches[f"strategy:{strategy}"]
            if ks.is_active:
                return (False, OrderRestriction.HARD_BLOCK,
                       f"Strategy {strategy} halted: {ks.reason}")
        
        # Check broker kill switch
        if broker and f"broker:{broker}" in self._kill_switches:
            ks = self._kill_switches[f"broker:{broker}"]
            if ks.is_active:
                return (False, OrderRestriction.HARD_BLOCK,
                       f"Broker {broker} halted: {ks.reason}")
        
        # Check order restrictions
        if account and account in self._order_restrictions:
            restriction = self._order_restrictions[account]
            if restriction != OrderRestriction.NONE:
                return (False, restriction, f"Account {account} has restriction: {restriction.value}")
        
        return (True, OrderRestriction.NONE, "")
    
    def set_restriction(self, target: str, restriction: OrderRestriction):
        """Set an order restriction."""
        self._order_restrictions[target] = restriction
        logger.info(f"Set restriction for {target}: {restriction.value}")
        
    def add_restricted_symbol(self, symbol: str):
        """Add a restricted symbol (cannot trade)."""
        self._symbol_restrictions.add(symbol.upper())
        
    def remove_restricted_symbol(self, symbol: str):
        """Remove a restricted symbol."""
        self._symbol_restrictions.discard(symbol.upper())
        
    def is_symbol_allowed(self, symbol: str) -> bool:
        """Check if a symbol is allowed for trading."""
        return symbol.upper() not in self._symbol_restrictions
    
    def check_fat_finger(self, symbol: str, order_value: float) -> RiskCheckResult:
        """Check for fat-finger orders (unusually large)."""
        symbol_upper = symbol.upper()
        max_order = self._fat_finger_limits.get(symbol_upper, 0)
        
        if max_order > 0 and order_value > max_order:
            return RiskCheckResult(
                is_allowed=False,
                restriction=OrderRestriction.HARD_BLOCK,
                message=f"Order value ${order_value} exceeds fat-finger limit ${max_order} for {symbol}",
                rejected_fields={"order_value": order_value, "max_allowed": max_order}
            )
        
        return RiskCheckResult(is_allowed=True)
    
    def set_fat_finger_limit(self, symbol: str, max_order_value: float):
        """Set a fat-finger limit for a symbol."""
        self._fat_finger_limits[symbol.upper()] = max_order_value
        logger.info(f"Set fat-finger limit for {symbol}: ${max_order_value}")
        
    def check_order(self, symbol: str, order_value: float, account: str = None,
                   desk: str = None, strategy: str = None, broker: str = None) -> RiskCheckResult:
        """Comprehensive pre-trade risk check."""
        # Check symbol restrictions
        if not self.is_symbol_allowed(symbol):
            return RiskCheckResult(
                is_allowed=False,
                restriction=OrderRestriction.HARD_BLOCK,
                message=f"Symbol {symbol} is restricted",
                rejected_fields={"symbol": symbol}
            )
        
        # Check fat finger
        fat_finger_result = self.check_fat_finger(symbol, order_value)
        if not fat_finger_result.is_allowed:
            return fat_finger_result
        
        # Check kill switches
        is_allowed, restriction, message = self.isTradingAllowed(
            account=account, desk=desk, strategy=strategy, broker=broker
        )
        if not is_allowed:
            return RiskCheckResult(
                is_allowed=False,
                restriction=restriction,
                message=message,
                rejected_fields={"account": account, "desk": desk, "strategy": strategy}
            )
        
        # Check account-level exposure if specified
        if account:
            exposure_result = self.check_exposure_limit("account", account)
            if not exposure_result.is_allowed:
                return exposure_result
            
        # Check portfolio-level exposure
        exposure_result = self.check_exposure_limit("portfolio", "default")
        if not exposure_result.is_allowed:
            return exposure_result
        
        return RiskCheckResult(is_allowed=True)
    
    def get_all_kill_switches(self) -> List[Dict[str, Any]]:
        """Get all kill switches with their state."""
        return [
            {
                "switch_id": ks.switch_id,
                "level": ks.level.value,
                "target_id": ks.target_id,
                "is_active": ks.is_active,
                "triggered_by": ks.triggered_by,
                "triggered_at": ks.triggered_at.isoformat() if ks.triggered_at else None,
                "reason": ks.reason
            }
            for ks in self._kill_switches.values()
        ]
    
    def get_all_limits(self) -> List[Dict[str, Any]]:
        """Get all exposure limits with current values."""
        result = []
        for limit in self._exposure_limits.values():
            result.append({
                "limit_id": limit.limit_id,
                "level": limit.level,
                "level_id": limit.level_id,
                "max_notional": limit.max_notional,
                "max_daily_loss": limit.max_daily_loss,
                "max_position_size": limit.max_position_size,
                "soft_limit": limit.soft_limit,
                "current_notional": limit.current_notional,
                "current_position": limit.current_position,
                "daily_pnl": limit.daily_pnl,
                "orders_count": limit.orders_count,
                "is_enabled": limit.is_enabled
            })
        return result


# Global risk controls instance
risk_controls = RiskControls()


# Public exports
__all__ = [
    "KillSwitchLevel",
    "OrderRestriction", 
    "ExposureLimit",
    "KillSwitch",
    "RiskCheckResult",
    "RiskControls",
    "risk_controls",
]