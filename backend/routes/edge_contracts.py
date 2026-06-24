"""Edge route request/response contracts and security helpers."""
import math
import secrets
from enum import Enum
from typing import Any, Dict, Literal, Optional

from fastapi import Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

import deps


_RATE_WINDOW = 60  # seconds
_RATE_LIMIT = 60  # requests per minute
_rate_limits: dict = {}  # ip -> [(timestamp, count), ...]


def _validate_finite_positive_trailing_percent(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    percent = float(value)
    if not math.isfinite(percent):
        raise ValueError("trailing_percent must be finite")
    if percent <= 0:
        raise ValueError("trailing_percent must be greater than 0")
    return percent


class SignalRequest(BaseModel):
    """Signal request from Edge.
    
    Can include:
    - action: buy/sell/stop (legacy decision)
    - ORB data: orb_high, orb_low, orb_breakout
    - RSI: rsi
    - Patterns: pattern (hs, dtb)
    - Direction: signal_type (bullish/bearish/neutral)
    """
    action: str = "signal"  # Default to signal mode
    confidence: float = 1.0
    bracket: Optional[dict] = None
    decision: str = "hold"  # Legacy field
    price: Optional[float] = None
    trailing_percent: Optional[float] = None
    
    # Signal fields
    rsi: Optional[float] = None
    signal_type: Optional[str] = None  # bullish, bearish, neutral
    orb_high: Optional[float] = None
    orb_low: Optional[float] = None
    pattern: Optional[str] = None  # hs, dtb, etc
    volatility: Optional[float] = None
    volume: Optional[float] = None

class SignalResponse(BaseModel):
    """Signal response to Edge."""
    status: str
    symbol: str
    action: str = "signal"
    decision: str = "hold"
    confidence: float = 1.0
    order_id: Optional[str] = None
    message: str = ""


class PulseHandoffAction(str, Enum):
    BUY = "buy"
    SELL = "sell"
    STOP_BUYING = "stop_buying"
    STOP_ALL = "stop_all"
    REGULAR_STOP = "regular_stop"
    TRAILING_STOP = "trailing_stop"
    OPENING_TRAILING_STOP = "opening_trailing_stop"
    TIGHTEN_STOP = "tighten_stop"
    TIGHTEN_TRAILING_STOP = "tighten_trailing_stop"
    DCA = "dca"
    EMERGENCY_EXIT = "emergency_exit"


class PulseHandoffMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"


class PulseHandoffStopType(str, Enum):
    REGULAR = "regular"
    TRAILING = "trailing"
    TIGHTEN = "tighten"
    TIGHTEN_TRAILING = "tighten_trailing"


class PulseHandoffDcaPlan(BaseModel):
    steps: Optional[int] = Field(default=None, ge=1)
    interval_seconds: Optional[int] = Field(default=None, ge=0)
    allocation_pct: Optional[float] = Field(default=None, ge=0.0, le=100.0)

    model_config = ConfigDict(extra="allow")


class PulseHandoffRequest(BaseModel):
    contract_version: Literal["edge.pulse.handoff.v1"] = "edge.pulse.handoff.v1"
    symbol: str
    action: PulseHandoffAction
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = ""
    mode: PulseHandoffMode
    orb_session: str = "market_open"
    stop_type: Optional[PulseHandoffStopType] = None
    trailing_percent: Optional[float] = Field(default=None, gt=0.0)
    dca: Optional[PulseHandoffDcaPlan] = None
    idempotency_key: str = Field(min_length=1)
    source: Literal["sentinel_edge"] = "sentinel_edge"
    created_at: float = Field(gt=0.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    @field_validator("symbol", mode="before")
    @classmethod
    def _normalise_symbol(cls, value: Any) -> str:
        symbol = str(value or "").strip().upper()
        if not symbol:
            raise ValueError("symbol is required")
        return symbol

    @field_validator("reason", "orb_session", "idempotency_key", mode="before")
    @classmethod
    def _strip_text(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("trailing_percent")
    @classmethod
    def _validate_trailing_percent(cls, value: Optional[float]) -> Optional[float]:
        return _validate_finite_positive_trailing_percent(value)

    @model_validator(mode="after")
    def _validate_action_context(self) -> "PulseHandoffRequest":
        required_stop_types = {
            PulseHandoffAction.REGULAR_STOP: PulseHandoffStopType.REGULAR,
            PulseHandoffAction.TRAILING_STOP: PulseHandoffStopType.TRAILING,
            PulseHandoffAction.OPENING_TRAILING_STOP: PulseHandoffStopType.TRAILING,
            PulseHandoffAction.TIGHTEN_STOP: PulseHandoffStopType.TIGHTEN,
            PulseHandoffAction.TIGHTEN_TRAILING_STOP: PulseHandoffStopType.TIGHTEN_TRAILING,
        }
        trailing_actions = {
            PulseHandoffAction.TRAILING_STOP,
            PulseHandoffAction.OPENING_TRAILING_STOP,
            PulseHandoffAction.TIGHTEN_TRAILING_STOP,
        }
        required_stop_type = required_stop_types.get(self.action)
        if required_stop_type is not None:
            if self.stop_type is None:
                raise ValueError(f"stop_type is required for {self.action.value} handoff actions")
            if self.stop_type != required_stop_type:
                raise ValueError(
                    f"stop_type must be {required_stop_type.value} for {self.action.value} handoff actions"
                )

        if self.action in trailing_actions and self.trailing_percent is None:
            raise ValueError("trailing_percent is required for trailing handoff actions")

        if self.stop_type in {
            PulseHandoffStopType.TRAILING,
            PulseHandoffStopType.TIGHTEN_TRAILING,
        } and self.trailing_percent is None:
            raise ValueError("trailing_percent is required when stop_type is trailing")

        if self.action == PulseHandoffAction.DCA and self.dca is None:
            raise ValueError("dca is required for dca handoff actions")

        return self


def _current_position(symbol: str) -> dict:
    """Return the latest in-memory position snapshot for a symbol."""
    return deps.engine._positions.get(symbol, {})


def _check_rate_limit(client_ip: str) -> bool:
    """Check if client is within rate limit."""
    import time
    now = time.time()
    
    # Clean old entries
    if client_ip in _rate_limits:
        _rate_limits[client_ip] = [
            (ts, cnt) for ts, cnt in _rate_limits[client_ip]
            if now - ts < _RATE_WINDOW
        ]
    
    # Count requests in window
    total = sum(cnt for _, cnt in _rate_limits.get(client_ip, []))
    if total >= _RATE_LIMIT:
        return False
    
    # Add this request
    if client_ip not in _rate_limits:
        _rate_limits[client_ip] = []
    _rate_limits[client_ip].append((now, 1))
    
    return True

async def validate_api_key(
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
) -> bool:
    """Validate the Edge integration API key from X-API-Key or Authorization."""
    expected = await deps.db.settings.find_one({"key": "edge_api_key"}, {"_id": 0})
    expected_key = expected.get("value", "") if expected else ""
    if not expected_key:
        raise HTTPException(503, "Edge API key is not configured")
    provided_key = x_api_key or ""
    if not provided_key and authorization:
        provided_key = authorization.removeprefix("Bearer ").strip()
    if not provided_key or not secrets.compare_digest(provided_key, expected_key):
        raise HTTPException(401, "Invalid API key")
    return True

class DecisionRequest(BaseModel):
    """Request for /api/tickers/{symbol}/decision endpoint.
    
    Edge sends: {"symbol": "TSLA", "decision": "buy", ...}
    """
    symbol: str
    decision: str  # buy, sell, hold, stop, enable_trailing_stop, stop_buying, emergency_stop
    price: Optional[float] = None
    trailing_percent: Optional[float] = None
    confidence: float = 1.0

    @field_validator("trailing_percent")
    @classmethod
    def _validate_trailing_percent(cls, value: Optional[float]) -> Optional[float]:
        return _validate_finite_positive_trailing_percent(value)

class TrailingRequest(BaseModel):
    """Request for /api/tickers/{symbol}/trailing endpoint."""
    trailing_percent: float

    @field_validator("trailing_percent")
    @classmethod
    def _validate_trailing_percent(cls, value: float) -> float:
        return float(_validate_finite_positive_trailing_percent(value))

class SignalEvalRequest(BaseModel):
    """Request for signal evaluation."""
    symbol: str
    price: float
    orb_high: Optional[float] = None
    orb_low: Optional[float] = None
    volume: float = 0
    atr: float = 0
    price_change_pct: float = 0
    # Optional observation from Pulse (6th scoring layer)
    observation: Optional[dict] = None

class SignalEvalResponse(BaseModel):
    """Signal evaluation response."""
    symbol: str
    direction: str  # bullish, bearish, neutral
    strength: float  # -10 to +10
    volume_ratio: float = 1.0
    volume_zscore: float = 0.0
    observation_applied: bool = False  # Whether pattern observation was used
