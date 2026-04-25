"""Pydantic schemas for Sentinel Pulse."""
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
import re

from pydantic import BaseModel, Field, ConfigDict, field_validator


def validate_symbol(symbol: str) -> str:
    """Validate ticker symbol format."""
    if not symbol:
        raise ValueError("Symbol cannot be empty")
    # Allow alphanumeric + common exchange suffixes
    if not re.match(r"^[A-Z]{1,5}(:[A-Z]{1,5})?$", symbol.upper()):
        raise ValueError(f"Invalid symbol format: {symbol}")
    return symbol.upper()


class TickerConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str = Field(..., description="Ticker symbol")
    base_power: float = Field(100.0, ge=0, le=100000, description="Base power (max position size)")
    avg_days: int = Field(30, ge=1, le=365, description="Average days for calculation")
    buy_offset: float = Field(-3.0, ge=-50, le=0, description="Buy offset percentage")
    buy_percent: bool = True
    buy_order_type: str = "limit"
    sell_offset: float = Field(3.0, ge=0, le=50, description="Sell offset percentage")
    sell_percent: bool = True
    sell_order_type: str = "limit"
    stop_offset: float = Field(-6.0, ge=-50, le=0, description="Stop loss offset percentage")
    stop_percent: bool = True
    stop_order_type: str = "limit"
    trailing_enabled: bool = False
    trailing_percent: float = Field(2.0, ge=0, le=50, description="Trailing stop percentage")
    trailing_percent_mode: bool = True
    trailing_order_type: str = "limit"
    wait_day_after_buy: bool = False
    compound_profits: bool = True
    max_daily_loss: float = Field(0, ge=0, le=100, description="Max daily loss percentage")
    max_consecutive_losses: int = Field(0, ge=0, le=20, description="Max consecutive losses before auto-stop")
    auto_stopped: bool = False
    auto_stop_reason: str = ""
    auto_rebracket: bool = False
    rebracket_threshold: float = Field(2.0, ge=0, le=50, description="Rebracket threshold percentage")
    rebracket_spread: float = Field(0.80, ge=0.1, le=1.0, description="Rebracket spread")
    rebracket_cooldown: int = Field(0, ge=0, le=1440, description="Rebracket cooldown in minutes")
    rebracket_lookback: int = Field(10, ge=1, le=100, description="Rebracket lookback days")
    rebracket_buffer: float = Field(0.10, ge=0, le=1.0, description="Rebracket buffer percentage")
    rebracket_min_drift: float = Field(0.50, ge=0, le=10, description="Minimum price movement to trigger rebracket")
    
    @field_validator('symbol')
    @classmethod
    def validate_symbol_field(cls, v: str) -> str:
        return validate_symbol(v)
    enabled: bool = True
    strategy: str = "custom"
    broker_id: str = ""
    broker_ids: List[str] = []
    broker_allocations: Dict[str, float] = {}
    sort_order: int = 0
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    # Partial fills (scale in / scale out)
    partial_fills_enabled: bool = False
    buy_legs: list = []   # [{"alloc_pct": 50, "offset": -3.0, "is_percent": True}]
    sell_legs: list = []  # [{"alloc_pct": 60, "offset": 3.0, "is_percent": True}]
    # Time-based risk rules (per-ticker)
    lock_trailing_at_open: bool = False
    halve_stop_at_open: bool = False
    # Opening Bell Mode - forced trailing stop during first 30 mins
    opening_bell_enabled: bool = False
    opening_bell_trail_value: float = 1.0
    opening_bell_trail_is_percent: bool = True
    # Market / exchange (determines trading hours, currency, opening bell time)
    market: str = "US"
    # Pluggable strategy system
    strategy_config: Dict[str, Any] = {}   # per-ticker params for signal strategies


class TickerCreate(BaseModel):
    symbol: str
    base_power: float = 100.0
    market: Optional[str] = None  # Auto-detected from symbol suffix if not provided


class TickerUpdate(BaseModel):
    base_power: Optional[float] = None
    avg_days: Optional[int] = None
    buy_offset: Optional[float] = None
    buy_percent: Optional[bool] = None
    buy_order_type: Optional[str] = None
    sell_offset: Optional[float] = None
    sell_percent: Optional[bool] = None
    sell_order_type: Optional[str] = None
    stop_offset: Optional[float] = None
    stop_percent: Optional[bool] = None
    stop_order_type: Optional[str] = None
    trailing_enabled: Optional[bool] = None
    trailing_percent: Optional[float] = None
    trailing_percent_mode: Optional[bool] = None
    trailing_order_type: Optional[str] = None
    wait_day_after_buy: Optional[bool] = None
    compound_profits: Optional[bool] = None
    max_daily_loss: Optional[float] = None
    max_consecutive_losses: Optional[int] = None
    auto_stopped: Optional[bool] = None
    auto_stop_reason: Optional[str] = None
    auto_rebracket: Optional[bool] = None
    rebracket_threshold: Optional[float] = None
    rebracket_spread: Optional[float] = None
    rebracket_cooldown: Optional[int] = None
    rebracket_lookback: Optional[int] = None
    rebracket_buffer: Optional[float] = None
    rebracket_min_drift: Optional[float] = None
    enabled: Optional[bool] = None
    strategy: Optional[str] = None
    partial_fills_enabled: Optional[bool] = None
    buy_legs: Optional[list] = None
    sell_legs: Optional[list] = None
    lock_trailing_at_open: Optional[bool] = None
    halve_stop_at_open: Optional[bool] = None
    opening_bell_enabled: Optional[bool] = None
    opening_bell_trail_value: Optional[float] = None
    opening_bell_trail_is_percent: Optional[bool] = None
    market: Optional[str] = None
    strategy_config: Optional[Dict[str, Any]] = None


class TradeRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str
    side: str
    price: float
    quantity: float
    reason: str = ""
    pnl: float = 0.0
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    order_type: str = ""
    rule_mode: str = ""
    entry_price: float = 0.0
    target_price: float = 0.0
    total_value: float = 0.0
    buy_power: float = 0.0
    avg_price: float = 0.0
    sell_target: float = 0.0
    stop_target: float = 0.0
    trail_high: float = 0.0
    trail_trigger: float = 0.0
    trail_value: float = 0.0
    trail_mode: str = ""
    trading_mode: str = "paper"
    broker_results: list = []


class Position(BaseModel):
    model_config = ConfigDict(extra="ignore")
    symbol: str
    quantity: float = 0.0
    avg_entry: float = 0.0
    current_price: float = 0.0
    unrealized_pnl: float = 0.0


class TelegramConfig(BaseModel):
    bot_token: str = ""
    chat_ids: List[str] = []


class SettingsUpdate(BaseModel):
    telegram: Optional[TelegramConfig] = None
    simulate_24_7: Optional[bool] = None
    increment_step: Optional[float] = None
    decrement_step: Optional[float] = None
    account_balance: Optional[float] = None
    market_hours_only: Optional[bool] = None
    # Auto mode switching
    live_during_market_hours: Optional[bool] = None
    paper_after_hours: Optional[bool] = None
    # Pattern detection (Pulse → Edge)
    pattern_detection_enabled: Optional[bool] = None
    pattern_min_confidence: Optional[float] = None
    pattern_send_to_edge: Optional[bool] = None


class BetaRegistration(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone: str = ""
    ssn_last4: str
    address_street: str
    address_city: str
    address_state: str
    address_zip: str
    address_country: str
    agreement_accepted: bool
    agreement_version: str = "1.0"
    jurisdiction: str = ""
    registered_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class FeedbackReport(BaseModel):
    type: str = "bug"
    subject: str
    description: str
    error_log: str = ""


class PresetStrategy(BaseModel):
    name: str
    avg_days: int
    buy_offset: float
    buy_percent: bool
    sell_offset: float
    sell_percent: bool
    stop_offset: float
    stop_percent: bool
    trailing_enabled: bool
    trailing_percent: float
    trailing_percent_mode: bool = True


class BrokerTestRequest(BaseModel):
    credentials: Dict[str, str]
