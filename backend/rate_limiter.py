"""Rate Limiter and Circuit Breaker for Broker API Calls.

Provides configurable rate limiting and circuit breaker patterns
to protect against API abuse and handle broker failures gracefully.
"""
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Callable, Any
from dataclasses import dataclass, field
from collections import deque
from enum import Enum

import deps


class CircuitState(str, Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"      # Failing, rejecting calls
    HALF_OPEN = "half_open"  # Testing if recovered


@dataclass
class BrokerRateLimitConfig:
    """Configuration for a broker's rate limits."""
    requests_per_minute: int = 60
    requests_per_second: int = 5
    burst_limit: int = 10  # Max concurrent requests
    
    # Circuit breaker settings
    failure_threshold: int = 5  # Failures before opening circuit
    recovery_timeout_seconds: int = 60  # How long to wait before half-open
    success_threshold: int = 2  # Successes needed to close circuit


@dataclass
class BrokerRateLimitState:
    """Runtime state for a broker's rate limiting."""
    # Rate limiting
    request_timestamps: deque = field(default_factory=lambda: deque(maxlen=1000))
    concurrent_requests: int = 0
    
    # Circuit breaker
    circuit_state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[datetime] = None
    circuit_opened_at: Optional[datetime] = None


# Default configs for known brokers
DEFAULT_BROKER_CONFIGS: Dict[str, BrokerRateLimitConfig] = {
    "alpaca": BrokerRateLimitConfig(
        requests_per_minute=200,
        requests_per_second=10,
        burst_limit=20,
        failure_threshold=5,
        recovery_timeout_seconds=30,
    ),
    "robinhood": BrokerRateLimitConfig(
        requests_per_minute=30,  # Very conservative for Robinhood
        requests_per_second=2,
        burst_limit=5,
        failure_threshold=3,
        recovery_timeout_seconds=120,  # Longer recovery for RH
    ),
    "webull": BrokerRateLimitConfig(
        requests_per_minute=30,
        requests_per_second=2,
        burst_limit=5,
        failure_threshold=3,
        recovery_timeout_seconds=120,
    ),
    "ibkr": BrokerRateLimitConfig(
        requests_per_minute=100,
        requests_per_second=5,
        burst_limit=15,
        failure_threshold=5,
        recovery_timeout_seconds=60,
    ),
    "tradier": BrokerRateLimitConfig(
        requests_per_minute=120,
        requests_per_second=5,
        burst_limit=15,
        failure_threshold=5,
        recovery_timeout_seconds=45,
    ),
    "default": BrokerRateLimitConfig(),  # Fallback
}


class RateLimiter:
    """Rate limiter and circuit breaker for broker API calls."""
    
    def __init__(self):
        self._states: Dict[str, BrokerRateLimitState] = {}
        self._configs: Dict[str, BrokerRateLimitConfig] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
    
    def get_config(self, broker_id: str) -> BrokerRateLimitConfig:
        """Get config for a broker, using defaults if not customized."""
        if broker_id in self._configs:
            return self._configs[broker_id]
        
        # Check for broker type in ID (e.g., "alpaca_xxx" -> "alpaca")
        broker_type = broker_id.split("_")[0].lower()
        return DEFAULT_BROKER_CONFIGS.get(broker_type, DEFAULT_BROKER_CONFIGS["default"])
    
    def set_config(self, broker_id: str, config: BrokerRateLimitConfig):
        """Set custom config for a broker."""
        self._configs[broker_id] = config
    
    def _get_state(self, broker_id: str) -> BrokerRateLimitState:
        """Get or create state for a broker."""
        if broker_id not in self._states:
            self._states[broker_id] = BrokerRateLimitState()
        return self._states[broker_id]
    
    def _get_lock(self, broker_id: str) -> asyncio.Lock:
        """Get or create lock for a broker."""
        if broker_id not in self._locks:
            self._locks[broker_id] = asyncio.Lock()
        return self._locks[broker_id]
    
    def _clean_old_timestamps(self, state: BrokerRateLimitState, window_seconds: int = 60):
        """Remove timestamps older than the window."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=window_seconds)
        while state.request_timestamps and state.request_timestamps[0] < cutoff:
            state.request_timestamps.popleft()
    
    async def check_rate_limit(self, broker_id: str) -> tuple[bool, Optional[str]]:
        """
        Check if a request is allowed under rate limits.
        
        Returns (allowed, error_message).
        """
        config = self.get_config(broker_id)
        state = self._get_state(broker_id)
        now = datetime.now(timezone.utc)
        
        async with self._get_lock(broker_id):
            # Check circuit breaker first
            if state.circuit_state == CircuitState.OPEN:
                # Check if recovery timeout has passed
                if state.circuit_opened_at:
                    elapsed = (now - state.circuit_opened_at).total_seconds()
                    if elapsed >= config.recovery_timeout_seconds:
                        state.circuit_state = CircuitState.HALF_OPEN
                        state.success_count = 0
                        deps.logger.info(f"Circuit breaker for {broker_id} entering HALF_OPEN state")
                    else:
                        return False, f"Circuit breaker OPEN. Retry in {int(config.recovery_timeout_seconds - elapsed)}s"
            
            # Clean old timestamps
            self._clean_old_timestamps(state, 60)
            
            # Check per-minute limit
            if len(state.request_timestamps) >= config.requests_per_minute:
                from audit_service import audit_service, AuditEventType
                await audit_service.log_rate_limit(
                    broker_id,
                    len(state.request_timestamps),
                    config.requests_per_minute,
                    60,
                )
                return False, f"Rate limit: {len(state.request_timestamps)}/{config.requests_per_minute} requests/min"
            
            # Check per-second limit
            one_second_ago = now - timedelta(seconds=1)
            recent_count = sum(1 for ts in state.request_timestamps if ts >= one_second_ago)
            if recent_count >= config.requests_per_second:
                return False, f"Rate limit: {recent_count}/{config.requests_per_second} requests/sec"
            
            # Check burst limit
            if state.concurrent_requests >= config.burst_limit:
                return False, f"Burst limit: {state.concurrent_requests}/{config.burst_limit} concurrent"
            
            # All checks passed - record the request
            state.request_timestamps.append(now)
            state.concurrent_requests += 1
            
            return True, None
    
    async def record_success(self, broker_id: str):
        """Record a successful API call."""
        config = self.get_config(broker_id)
        state = self._get_state(broker_id)
        
        async with self._get_lock(broker_id):
            state.concurrent_requests = max(0, state.concurrent_requests - 1)
            state.failure_count = 0
            
            if state.circuit_state == CircuitState.HALF_OPEN:
                state.success_count += 1
                if state.success_count >= config.success_threshold:
                    state.circuit_state = CircuitState.CLOSED
                    state.circuit_opened_at = None
                    deps.logger.info(f"Circuit breaker for {broker_id} CLOSED after recovery")
                    from audit_service import audit_service
                    await audit_service.log_circuit_breaker(
                        broker_id, "closed", 0, config.failure_threshold
                    )
    
    async def record_failure(self, broker_id: str, error: str):
        """Record a failed API call."""
        config = self.get_config(broker_id)
        state = self._get_state(broker_id)
        now = datetime.now(timezone.utc)
        
        async with self._get_lock(broker_id):
            state.concurrent_requests = max(0, state.concurrent_requests - 1)
            state.failure_count += 1
            state.last_failure_time = now
            
            if state.circuit_state == CircuitState.HALF_OPEN:
                # Failed during recovery - reopen circuit
                state.circuit_state = CircuitState.OPEN
                state.circuit_opened_at = now
                deps.logger.warning(f"Circuit breaker for {broker_id} re-OPENED after recovery failure")
            elif state.circuit_state == CircuitState.CLOSED:
                if state.failure_count >= config.failure_threshold:
                    state.circuit_state = CircuitState.OPEN
                    state.circuit_opened_at = now
                    deps.logger.warning(f"Circuit breaker for {broker_id} OPENED after {state.failure_count} failures")
                    from audit_service import audit_service
                    await audit_service.log_circuit_breaker(
                        broker_id, "open", state.failure_count, config.failure_threshold
                    )
    
    def get_status(self, broker_id: str) -> Dict[str, Any]:
        """Get current rate limit and circuit breaker status for a broker."""
        config = self.get_config(broker_id)
        state = self._get_state(broker_id)
        
        self._clean_old_timestamps(state, 60)
        
        now = datetime.now(timezone.utc)
        one_second_ago = now - timedelta(seconds=1)
        recent_per_second = sum(1 for ts in state.request_timestamps if ts >= one_second_ago)
        
        recovery_remaining = None
        if state.circuit_state == CircuitState.OPEN and state.circuit_opened_at:
            elapsed = (now - state.circuit_opened_at).total_seconds()
            recovery_remaining = max(0, config.recovery_timeout_seconds - elapsed)
        
        return {
            "broker_id": broker_id,
            "circuit_state": state.circuit_state.value,
            "failure_count": state.failure_count,
            "requests_last_minute": len(state.request_timestamps),
            "requests_last_second": recent_per_second,
            "concurrent_requests": state.concurrent_requests,
            "limits": {
                "requests_per_minute": config.requests_per_minute,
                "requests_per_second": config.requests_per_second,
                "burst_limit": config.burst_limit,
                "failure_threshold": config.failure_threshold,
                "recovery_timeout_seconds": config.recovery_timeout_seconds,
            },
            "recovery_remaining_seconds": recovery_remaining,
        }
    
    def get_all_statuses(self) -> list:
        """Get status for all tracked brokers."""
        return [self.get_status(bid) for bid in self._states.keys()]


# Singleton instance
rate_limiter = RateLimiter()
