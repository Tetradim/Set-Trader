"""Resilience module — Rate Limiting & Circuit Breakers for Broker APIs.

Provides production-grade resilience patterns:
- Token bucket rate limiting (via aiolimiter)
- Circuit breaker state machine (CLOSED → OPEN → HALF_OPEN → CLOSED)
- Per-broker configuration stored in MongoDB
- Prometheus metrics integration
- Telegram alerts for circuit state changes
"""
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import deque
import time

from aiolimiter import AsyncLimiter

import deps


class CircuitState(str, Enum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Blocking all calls
    HALF_OPEN = "half_open" # Testing with one call


@dataclass
class BrokerResilienceConfig:
    """Per-broker resilience configuration."""
    # Rate limiting (token bucket)
    max_rps: float = 10.0           # Max requests per second
    burst: int = 20                 # Burst capacity
    cooldown_ms: int = 100          # Min ms between requests
    
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


@dataclass
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


class BrokerResilience:
    """
    Manages rate limiting and circuit breakers for all brokers.
    
    Usage:
        resilience = BrokerResilience()
        await resilience.load_config()
        
        async with resilience.acquire(broker_id):
            result = await broker.place_order(...)
        
        # Or manually:
        await resilience.before_call(broker_id)
        try:
            result = await broker.place_order(...)
            await resilience.record_success(broker_id)
        except Exception as e:
            await resilience.record_failure(broker_id, e)
            raise
    """
    
    def __init__(self):
        self._configs: Dict[str, BrokerResilienceConfig] = {}
        self._limiters: Dict[str, AsyncLimiter] = {}
        self._circuits: Dict[str, CircuitBreakerState] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._telegram = None
        self._ws_manager = None
        self._loaded = False
    
    def set_telegram(self, telegram_service):
        """Set telegram service for alerts."""
        self._telegram = telegram_service
    
    def set_ws_manager(self, ws_manager):
        """Set WebSocket manager for real-time updates."""
        self._ws_manager = ws_manager
    
    async def load_config(self):
        """Load resilience config from MongoDB."""
        doc = await deps.db.settings.find_one({"key": "brokers_resilience"}, {"_id": 0})
        if doc and doc.get("value"):
            for broker_id, cfg in doc["value"].items():
                self._configs[broker_id] = BrokerResilienceConfig(**cfg)
                self._create_limiter(broker_id)
        self._loaded = True
        deps.logger.info(f"Loaded resilience config for {len(self._configs)} brokers")
    
    async def save_config(self):
        """Save current config to MongoDB."""
        value = {
            broker_id: {
                "max_rps": cfg.max_rps,
                "burst": cfg.burst,
                "cooldown_ms": cfg.cooldown_ms,
                "failure_threshold": cfg.failure_threshold,
                "failure_window_seconds": cfg.failure_window_seconds,
                "recovery_timeout_seconds": cfg.recovery_timeout_seconds,
                "half_open_max_calls": cfg.half_open_max_calls,
                "skip_during_opening": cfg.skip_during_opening,
            }
            for broker_id, cfg in self._configs.items()
        }
        await deps.db.settings.update_one(
            {"key": "brokers_resilience"},
            {"$set": {"value": value}},
            upsert=True,
        )
    
    def get_config(self, broker_id: str) -> BrokerResilienceConfig:
        """Get or create config for a broker."""
        if broker_id not in self._configs:
            broker_type = broker_id.split("_")[0]
            self._configs[broker_id] = BrokerResilienceConfig.for_broker(broker_type)
            self._create_limiter(broker_id)
        return self._configs[broker_id]
    
    def set_config(self, broker_id: str, config: BrokerResilienceConfig):
        """Update config for a broker."""
        self._configs[broker_id] = config
        self._create_limiter(broker_id)
    
    def _create_limiter(self, broker_id: str):
        """Create or recreate the rate limiter for a broker."""
        cfg = self._configs.get(broker_id, BrokerResilienceConfig())
        # AsyncLimiter(max_rate, time_period) - e.g., 10 requests per 1 second
        self._limiters[broker_id] = AsyncLimiter(cfg.max_rps, 1.0)
    
    def _get_circuit(self, broker_id: str) -> CircuitBreakerState:
        """Get or create circuit breaker state."""
        if broker_id not in self._circuits:
            self._circuits[broker_id] = CircuitBreakerState()
        return self._circuits[broker_id]
    
    def _get_lock(self, broker_id: str) -> asyncio.Lock:
        """Get or create lock for thread-safe operations."""
        if broker_id not in self._locks:
            self._locks[broker_id] = asyncio.Lock()
        return self._locks[broker_id]
    
    def _clean_old_failures(self, circuit: CircuitBreakerState, window_seconds: int):
        """Remove failures outside the sliding window."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=window_seconds)
        while circuit.failure_timestamps and circuit.failure_timestamps[0] < cutoff:
            circuit.failure_timestamps.popleft()
    
    async def before_call(self, broker_id: str) -> None:
        """
        Check rate limit and circuit breaker before making a call.
        Raises CircuitOpenError or waits for rate limit.
        """
        cfg = self.get_config(broker_id)
        circuit = self._get_circuit(broker_id)
        now = datetime.now(timezone.utc)
        
        async with self._get_lock(broker_id):
            # Check circuit breaker
            if circuit.state == CircuitState.OPEN:
                if circuit.opened_at:
                    elapsed = (now - circuit.opened_at).total_seconds()
                    if elapsed >= cfg.recovery_timeout_seconds:
                        # Transition to half-open
                        circuit.state = CircuitState.HALF_OPEN
                        circuit.half_open_successes = 0
                        deps.logger.info(f"Circuit {broker_id} → HALF_OPEN (testing recovery)")
                        await self._notify_circuit_change(broker_id, "half_open")
                    else:
                        remaining = int(cfg.recovery_timeout_seconds - elapsed)
                        raise CircuitOpenError(broker_id, remaining)
            
            # Clean old failures
            self._clean_old_failures(circuit, cfg.failure_window_seconds)
        
        # Acquire rate limiter (this will wait if needed)
        limiter = self._limiters.get(broker_id)
        if limiter:
            await limiter.acquire()
        
        # Additional cooldown if configured
        if cfg.cooldown_ms > 0:
            await asyncio.sleep(cfg.cooldown_ms / 1000.0)
    
    async def record_success(self, broker_id: str):
        """Record a successful API call."""
        circuit = self._get_circuit(broker_id)
        cfg = self.get_config(broker_id)
        
        async with self._get_lock(broker_id):
            circuit.total_successes += 1
            circuit.consecutive_failures = 0
            
            if circuit.state == CircuitState.HALF_OPEN:
                circuit.half_open_successes += 1
                if circuit.half_open_successes >= cfg.half_open_max_calls:
                    # Recovery successful - close circuit
                    circuit.state = CircuitState.CLOSED
                    circuit.opened_at = None
                    deps.logger.info(f"Circuit {broker_id} → CLOSED (recovered)")
                    await self._notify_circuit_change(broker_id, "closed")
        
        # Update Prometheus metric
        self._update_metrics(broker_id, success=True)
    
    async def record_failure(self, broker_id: str, error: Optional[Exception] = None):
        """Record a failed API call."""
        circuit = self._get_circuit(broker_id)
        cfg = self.get_config(broker_id)
        now = datetime.now(timezone.utc)
        
        async with self._get_lock(broker_id):
            circuit.failure_timestamps.append(now)
            circuit.last_failure_time = now
            circuit.total_failures += 1
            circuit.consecutive_failures += 1
            
            # Clean old failures and check threshold
            self._clean_old_failures(circuit, cfg.failure_window_seconds)
            recent_failures = len(circuit.failure_timestamps)
            
            if circuit.state == CircuitState.HALF_OPEN:
                # Failed during recovery - reopen
                circuit.state = CircuitState.OPEN
                circuit.opened_at = now
                deps.logger.warning(f"Circuit {broker_id} → OPEN (failed during recovery)")
                await self._notify_circuit_change(broker_id, "open", error)
            
            elif circuit.state == CircuitState.CLOSED:
                if recent_failures >= cfg.failure_threshold:
                    # Trip the circuit
                    circuit.state = CircuitState.OPEN
                    circuit.opened_at = now
                    deps.logger.warning(
                        f"Circuit {broker_id} → OPEN ({recent_failures} failures in {cfg.failure_window_seconds}s)"
                    )
                    await self._notify_circuit_change(broker_id, "open", error)
        
        # Update Prometheus metric
        self._update_metrics(broker_id, success=False)
        
        # Log to audit
        from audit_service import audit_service, AuditEventType
        await audit_service.log(
            AuditEventType.BROKER_API_ERROR,
            {"error": str(error) if error else "Unknown", "consecutive": circuit.consecutive_failures},
            broker_id=broker_id,
            success=False,
            error_message=str(error) if error else None,
        )
    
    async def _notify_circuit_change(
        self, 
        broker_id: str, 
        new_state: str, 
        error: Optional[Exception] = None
    ):
        """Send notifications about circuit state change."""
        cfg = self.get_config(broker_id)
        circuit = self._get_circuit(broker_id)
        
        # Telegram alert
        if self._telegram and self._telegram.running:
            if new_state == "open":
                msg = (
                    f"🔴 CIRCUIT BREAKER OPEN\n"
                    f"Broker: {broker_id}\n"
                    f"Failures: {circuit.consecutive_failures}\n"
                    f"Paused for: {cfg.recovery_timeout_seconds}s\n"
                    f"Error: {str(error)[:100] if error else 'Multiple failures'}"
                )
            elif new_state == "closed":
                msg = f"🟢 Circuit breaker CLOSED for {broker_id} (recovered)"
            else:
                msg = f"🟡 Circuit breaker HALF_OPEN for {broker_id} (testing)"
            
            try:
                await self._telegram.send_alert(msg)
            except Exception:
                pass
        
        # WebSocket broadcast
        if self._ws_manager:
            await self._ws_manager.broadcast({
                "type": "CIRCUIT_STATE_CHANGE",
                "broker_id": broker_id,
                "state": new_state,
                "recovery_seconds": cfg.recovery_timeout_seconds if new_state == "open" else None,
            })
        
        # Audit log
        from audit_service import audit_service, AuditEventType
        event = AuditEventType.BROKER_CIRCUIT_OPEN if new_state == "open" else AuditEventType.BROKER_CIRCUIT_CLOSED
        await audit_service.log(
            event,
            {"state": new_state, "failures": circuit.consecutive_failures},
            broker_id=broker_id,
            success=new_state == "closed",
        )
    
    def _update_metrics(self, broker_id: str, success: bool):
        """Update Prometheus metrics."""
        # These would integrate with your existing metrics
        # For now, just log
        pass
    
    def get_status(self, broker_id: str) -> Dict[str, Any]:
        """Get current status for a broker."""
        cfg = self.get_config(broker_id)
        circuit = self._get_circuit(broker_id)
        
        self._clean_old_failures(circuit, cfg.failure_window_seconds)
        
        recovery_remaining = None
        if circuit.state == CircuitState.OPEN and circuit.opened_at:
            elapsed = (datetime.now(timezone.utc) - circuit.opened_at).total_seconds()
            recovery_remaining = max(0, int(cfg.recovery_timeout_seconds - elapsed))
        
        return {
            "broker_id": broker_id,
            "circuit_state": circuit.state.value,
            "recent_failures": len(circuit.failure_timestamps),
            "consecutive_failures": circuit.consecutive_failures,
            "total_failures": circuit.total_failures,
            "total_successes": circuit.total_successes,
            "recovery_remaining_seconds": recovery_remaining,
            "config": {
                "max_rps": cfg.max_rps,
                "burst": cfg.burst,
                "cooldown_ms": cfg.cooldown_ms,
                "failure_threshold": cfg.failure_threshold,
                "failure_window_seconds": cfg.failure_window_seconds,
                "recovery_timeout_seconds": cfg.recovery_timeout_seconds,
                "skip_during_opening": cfg.skip_during_opening,
            },
        }
    
    def get_all_statuses(self) -> list:
        """Get status for all tracked brokers."""
        return [self.get_status(bid) for bid in set(list(self._configs.keys()) + list(self._circuits.keys()))]
    
    def is_opening_window(self) -> bool:
        """Check if we're in the market opening window (first 15 minutes)."""
        now = datetime.now(timezone(timedelta(hours=-5)))
        if now.weekday() >= 5:
            return False
        market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
        elapsed = (now - market_open).total_seconds()
        return 0 <= elapsed <= 15 * 60
    
    def should_skip_broker(self, broker_id: str) -> bool:
        """Check if this broker should be skipped (e.g., during opening for high-risk brokers)."""
        cfg = self.get_config(broker_id)
        circuit = self._get_circuit(broker_id)
        
        # Skip if circuit is open
        if circuit.state == CircuitState.OPEN:
            return True
        
        # Skip high-risk brokers during opening window if configured
        if cfg.skip_during_opening and self.is_opening_window():
            return True
        
        return False
    
    async def reset_circuit(self, broker_id: str):
        """Manually reset a circuit breaker (admin action)."""
        circuit = self._get_circuit(broker_id)
        async with self._get_lock(broker_id):
            circuit.state = CircuitState.CLOSED
            circuit.opened_at = None
            circuit.consecutive_failures = 0
            circuit.failure_timestamps.clear()
            circuit.half_open_successes = 0
        
        deps.logger.info(f"Circuit {broker_id} manually reset to CLOSED")
        await self._notify_circuit_change(broker_id, "closed")


# Singleton instance
broker_resilience = BrokerResilience()
