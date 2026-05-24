"""Edge route request/response contracts and security helpers."""
import secrets
from typing import Optional

from fastapi import Header, HTTPException
from pydantic import BaseModel

import deps


_RATE_WINDOW = 60        # seconds

_RATE_LIMIT = 60        # requests per minute

_rate_limits: dict = {}  # ip -> [(timestamp, count), ...]

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

class TrailingRequest(BaseModel):
    """Request for /api/tickers/{symbol}/trailing endpoint."""
    trailing_percent: float

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
