"""Resilience primitive types used by BrokerResilience."""
import asyncio
import time as sync_time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class CircuitState(str, Enum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Blocking all calls
    HALF_OPEN = "half_open" # Testing with one call

class BrokerResilienceConfig:
    """Per-broker resilience configuration."""
    # Rate limiting (token bucket)
    max_rps: float = 10.0           # Max requests per second sustained
    burst: int = 20                 # Burst capacity
    cooldown_ms: int = 100          # Min ms between requests (legacy, use max_rps)
    
    # Circuit breaker
    failure_threshold: int = 5      # Failures to trip circuit
    failure_window_seconds: int = 60  # Sliding window for counting failures
    recovery_timeout_seconds: int = 60  # How long circuit stays open
    half_open_max_calls: int = 2    # Test calls in half-open state
    
    # Behavior
    skip_during_opening: bool = False  # Skip this broker during market opening (first 15 min)
    
    @classmethod
    def for_broker(cls, broker_type: str) -> "BrokerResilienceConfig":
        """Get default config based on broker type/risk level."""
        # Conservative defaults for high-risk brokers
        DEFAULTS = {
            "robinhood": cls(
                max_rps=2.0, burst=5, cooldown_ms=800,
                failure_threshold=3, recovery_timeout_seconds=120,
                skip_during_opening=True,
            ),
            "webull": cls(
                max_rps=3.0, burst=6, cooldown_ms=600,
                failure_threshold=3, recovery_timeout_seconds=120,
                skip_during_opening=True,
            ),
            "alpaca": cls(
                max_rps=20.0, burst=30, cooldown_ms=100,
                failure_threshold=5, recovery_timeout_seconds=30,
            ),
            "ibkr": cls(
                max_rps=10.0, burst=20, cooldown_ms=200,
                failure_threshold=5, recovery_timeout_seconds=45,
            ),
            "tradier": cls(
                max_rps=15.0, burst=25, cooldown_ms=150,
                failure_threshold=5, recovery_timeout_seconds=30,
            ),
            "tradestation": cls(
                max_rps=10.0, burst=15, cooldown_ms=200,
                failure_threshold=5, recovery_timeout_seconds=45,
            ),
            "schwab": cls(
                max_rps=5.0, burst=10, cooldown_ms=400,
                failure_threshold=4, recovery_timeout_seconds=90,
            ),
        }
        broker_key = broker_type.lower().split("_")[0]
        return DEFAULTS.get(broker_key, cls())

class CircuitBreakerState:
    """Runtime state for a circuit breaker."""
    state: CircuitState = CircuitState.CLOSED
    failure_timestamps: deque = field(default_factory=lambda: deque(maxlen=100))
    last_failure_time: Optional[datetime] = None
    opened_at: Optional[datetime] = None
    half_open_successes: int = 0
    total_failures: int = 0
    total_successes: int = 0
    consecutive_failures: int = 0

class CircuitOpenError(Exception):
    """Raised when attempting to call a broker with an open circuit."""
    def __init__(self, broker_id: str, recovery_seconds: int):
        self.broker_id = broker_id
        self.recovery_seconds = recovery_seconds
        super().__init__(f"Circuit breaker OPEN for {broker_id}. Retry in {recovery_seconds}s")

class RateLimitExceededError(Exception):
    """Raised when rate limit would be exceeded."""
    def __init__(self, broker_id: str, wait_ms: int):
        self.broker_id = broker_id
        self.wait_ms = wait_ms
        super().__init__(f"Rate limit for {broker_id}. Wait {wait_ms}ms")

class TokenBucket:
    """
    Accurate token bucket rate limiter that properly enforces both burst and sustained rates.
    
    Unlike aiolimiter which is a leaky bucket, this is a true token bucket:
    - Tokens accumulate up to max_capacity (burst)
    - Tokens refill at rate tokens per second
    - Each acquire() consumes one token
    - If no tokens, wait until one becomes available
    
    This ensures:
    - Burst: You can make up to max_capacity requests instantly
    - Sustained: You cannot exceed rate requests/second over time
    """
    
    def __init__(self, rate: float, capacity: int):
        """
        Args:
            rate: Tokens added per second (max_rps)
            capacity: Maximum tokens (burst size)
        """
        self.rate = rate
        self.capacity = capacity
        self._tokens = float(capacity)
        self._last_update = sync_time.monotonic()
        self._lock = asyncio.Lock()
    
    async def acquire(self, timeout: Optional[float] = None) -> None:
        """
        Acquire a token, waiting if necessary.
        
        Args:
            timeout: Maximum seconds to wait (None = wait forever)
        """
        deadline = None if timeout is None else sync_time.monotonic() + timeout
        
        async with self._lock:
            while self._tokens < 1:
                if deadline is not None:
                    wait_time = (1 - self._tokens) / self.rate
                    if sync_time.monotonic() + wait_time > deadline:
                        raise RateLimitExceededError("bucket", int(wait_time * 1000))
                
                # Calculate wait time and release lock
                wait_time = (1 - self._tokens) / self.rate
                
                # Release lock while sleeping
                self._lock.release()
                try:
                    await asyncio.sleep(wait_time)
                finally:
                    await self._lock.acquire()
                
                self._refill()
            
            self._tokens -= 1
    
    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = sync_time.monotonic()
        elapsed = now - self._last_update
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
        self._last_update = now
    
    @property
    def available_tokens(self) -> float:
        """Get current available tokens."""
        self._refill()
        return self._tokens

class _BrokerCallContext:
    """
    Async context manager for broker calls that auto-records success/failure.
    
    Usage:
        async with resilience.acquire(broker_id) as ctx:
            result = await broker.place_order(...)
    """
    
    def __init__(self, resilience: "BrokerResilience", broker_id: str):
        self._resilience = resilience
        self._broker_id = broker_id
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            await self._resilience.record_failure(self._broker_id, exc_val)
        else:
            await self._resilience.record_success(self._broker_id)
        return False  # Don't suppress exceptions
