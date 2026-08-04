"""Pydantic schemas for Sentinel Pulse."""
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
import re

from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator


def validate_symbol(symbol: str) -> str:
    """Validate ticker symbol format."""
    if not symbol:
        raise ValueError("Symbol cannot be empty")
    normalized = symbol.upper()
    # Allow common US and foreign ticker formats such as AAPL, BRK-B, BHP.AX, and 7203.T.
    if not re.match(r"^(?=.{1,20}$)[A-Z0-9]+(?:[.-][A-Z0-9]+)*$", normalized):
        raise ValueError(f"Invalid symbol format: {symbol}")
    return normalized


class TickerConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str = Field(..., description="Ticker symbol")
    base_power: float = Field(100.0, ge=0, le=100000, description="Base power (max position size)")
    avg_days: int = Field(30, ge=1, le=365, description="Average days for calculation")
    buy_offset: float = Field(-3.0, ge=-50, le=99999, description="Buy percentage offset or absolute price")
    buy_percent: bool = True
    buy_order_type: str = "limit"
    sell_offset: float = Field(3.0, ge=0, le=99999, description="Sell percentage offset or absolute price")
    sell_percent: bool = True
    sell_order_type: str = "limit"
    stop_offset: float = Field(-6.0, ge=-50, le=99999, description="Stop percentage offset or absolute price")
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
    rebracket_threshold: float = Field(2.0, ge=0, le=99999, description="Absolute price drift required to rebracket")
    rebracket_spread: float = Field(0.80, ge=0.01, le=99999, description="Absolute price width of the new bracket")
    rebracket_cooldown: int = Field(0, ge=0, le=3600, description="Cooldown between rebrackets in seconds")
    rebracket_lookback: int = Field(10, ge=2, le=100, description="Recent price sample count for rebracket anchoring")
    rebracket_buffer: float = Field(0.10, ge=0, le=99999, description="Absolute price buffer below the recent anchor")
    rebracket_min_drift: float = Field(0.50, ge=0, le=99999, description="Minimum absolute price movement to trigger rebracket")

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
    # Passive range scalping (resting limit buy -> confirmed fill -> resting limit sell)
    passive_range_enabled: bool = False
    price_tick_size: float = Field(0, ge=0, le=1000, description="Explicit price tick; 0 infers from price")
    passive_reentry_seconds: int = Field(0, ge=0, le=86400)
    passive_order_ttl_seconds: int = Field(300, ge=0, le=86400)
    passive_max_hold_seconds: int = Field(0, ge=0, le=2592000)
    passive_cancel_on_partial: bool = True
    passive_fractional_shares: bool = False
    passive_paper_min_touches: int = Field(2, ge=1, le=100)

    @model_validator(mode="after")
    def validate_price_modes(self):
        # Preserve the legacy percentage ranges regardless of execution mode.
        if self.buy_percent and not -50 <= self.buy_offset <= 0:
            raise ValueError("buy_offset must be between -50 and 0 when buy_percent is enabled")
        if self.sell_percent and not 0 <= self.sell_offset <= 50:
            raise ValueError("sell_offset must be between 0 and 50 when sell_percent is enabled")
        if self.stop_percent and not -50 <= self.stop_offset <= 0:
            raise ValueError("stop_offset must be between -50 and 0 when stop_percent is enabled")

        # Passive orders always use exact limit/trigger prices, so their absolute
        # values must be executable. Non-passive market configurations retain
        # their historical tolerance for ignored sentinel offsets.
        if self.passive_range_enabled:
            if self.buy_percent:
                pass
            elif self.buy_offset <= 0:
                raise ValueError("passive range buy_offset must be a positive absolute price")

            if self.sell_percent:
                pass
            elif self.sell_offset <= 0:
                raise ValueError("passive range sell_offset must be a positive absolute price")

            if self.stop_percent:
                pass
            elif self.stop_offset <= 0:
                raise ValueError("passive range stop_offset must be a positive absolute price")

            if not self.buy_percent and not self.sell_percent and self.buy_offset >= self.sell_offset:
                raise ValueError("passive range absolute buy price must be below the sell price")
            if not self.buy_percent and not self.stop_percent and self.stop_offset >= self.buy_offset:
                raise ValueError("passive range absolute stop price must be below the buy price")

        return self


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
    broker_id: Optional[str] = None
    broker_ids: Optional[List[str]] = None
    broker_allocations: Optional[Dict[str, float]] = None
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
    passive_range_enabled: Optional[bool] = None
    price_tick_size: Optional[float] = None
    passive_reentry_seconds: Optional[int] = None
    passive_order_ttl_seconds: Optional[int] = None
    passive_max_hold_seconds: Optional[int] = None
    passive_cancel_on_partial: Optional[bool] = None
    passive_fractional_shares: Optional[bool] = None
    passive_paper_min_touches: Optional[int] = None


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


class GlobalDailyDrawdownConfig(BaseModel):
    enabled: bool = False
    limit: float = Field(3.0, ge=0)
    type: str = Field("percent", pattern="^(percent|cash)$")


class SettingsUpdate(BaseModel):
    telegram: Optional[TelegramConfig] = None
    simulate_24_7: Optional[bool] = None
    live_trading_confirmation: Optional[str] = Field(None, max_length=64)
    live_trading_operator_secret: Optional[str] = Field(None, max_length=512)
    increment_step: Optional[float] = None
    decrement_step: Optional[float] = None
    account_balance: Optional[float] = None
    global_daily_drawdown: Optional[GlobalDailyDrawdownConfig] = None
    market_hours_only: Optional[bool] = None
    # Auto mode switching
    live_during_market_hours: Optional[bool] = None
    paper_after_hours: Optional[bool] = None
    # Pattern detection (Pulse → Edge)
    pattern_detection_enabled: Optional[bool] = None
    pattern_min_confidence: Optional[float] = None
    pattern_send_to_edge: Optional[bool] = None
    edge_retry_max_attempts: Optional[int] = Field(None, ge=0, le=100)


class BetaRegistration(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone: str = ""
    address_street: str = ""
    address_city: str = ""
    address_state: str = ""
    address_zip: str = ""
    address_country: str = ""
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
