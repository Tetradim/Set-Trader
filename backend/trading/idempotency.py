from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Tuple
from zoneinfo import ZoneInfo

import deps
from schemas import TradeRecord
from resilience import CircuitOpenError


class OrderIdempotencyMixin:
    def _generate_order_id(self, symbol: str, side: str, price: float, qty: float) -> str:
        """Generate a unique order ID for idempotency."""
        import hashlib
        import time
        # Include timestamp at minute granularity to avoid collisions
        ts = int(time.time() / 60) * 60
        data = f"{symbol}:{side}:{price}:{qty}:{ts}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def is_order_duplicate(self, order_id: str) -> bool:
        """Check if this order ID was recently submitted."""
        self._cleanup_expired_order_ids()
        return order_id in self._order_id_timestamps

    def mark_order_submitted(self, order_id: str):
        """Mark an order as submitted."""
        self._order_id_timestamps[order_id] = datetime.now(timezone.utc)

    def _cleanup_expired_order_ids(self):
        """Remove expired order IDs from tracking."""
        now = datetime.now(timezone.utc)
        expired = [
            oid for oid, ts in self._order_id_timestamps.items()
            if (now - ts).total_seconds() > self.IDEMPOTENCY_TTL_SECONDS
        ]
        for oid in expired:
            del self._order_id_timestamps[oid]

    def clear_order_id(self, order_id: str):
        """Clear a specific order ID (e.g., after execution confirmed)."""
        self._order_id_timestamps.pop(order_id, None)
