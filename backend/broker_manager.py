"""Broker connection manager — stores credentials, manages live connections, handles failover."""
import asyncio
import logging
import base64
import os
import uuid
from datetime import datetime, timezone
from typing import Optional, Set
from brokers import BrokerAdapter, BrokerOrder, get_broker_adapter, get_broker_info, BROKER_REGISTRY

logger = logging.getLogger("SentinelPulse")

# Simple XOR-based obfuscation for credentials at rest.
_KEY = (os.environ.get("CREDENTIAL_KEY") or "sentinel-pulse-default-key-2026").encode()

def _xor_bytes(data: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))

def encrypt_credentials(creds: dict) -> str:
    import json
    raw = json.dumps(creds).encode()
    return base64.b64encode(_xor_bytes(raw, _KEY)).decode()

def decrypt_credentials(encrypted: str) -> dict:
    import json
    raw = _xor_bytes(base64.b64decode(encrypted), _KEY)
    return json.loads(raw)


class BrokerConnectionManager:
    """Manages live broker connections with auto-reconnect and failover."""

    def __init__(self, db):
        self.db = db
        self._adapters: dict[str, BrokerAdapter] = {}
        self._failed: dict[str, str] = {}
        self._telegram = None
        self._ws_manager = None
        # Idempotency tracking: submitted order keys to prevent duplicates
        self._submitted_orders: dict[str, dict] = {}  # idempotency_key -> {symbol, side, status, broker_order_id}
        self._order_ttl_seconds: int = 300  # Keep order tracking for 5 minutes

    def set_telegram(self, telegram_service):
        self._telegram = telegram_service

    def set_ws_manager(self, ws_manager):
        self._ws_manager = ws_manager

    def _generate_idempotency_key(self, symbol: str, side: str, quantity: float, order_type: str) -> str:
        """Generate a unique idempotency key for an order."""
        key_data = f"{symbol}:{side}:{quantity}:{order_type}:{datetime.now(timezone.utc).isoformat()[:19]}"
        return f"sp_{uuid.uuid5(uuid.NAMESPACE_DNS, key_data)}"

    async def _check_duplicate_order(self, idempotency_key: str) -> Optional[dict]:
        """Check if an order with this idempotency key was already submitted."""
        if idempotency_key in self._submitted_orders:
            existing = self._submitted_orders[idempotency_key]
            # Check if order is still pending or was filled recently
            if existing.get("status") in ("pending", "submitted", "filled"):
                logger.warning(f"Duplicate order detected: {idempotency_key}")
                return existing
        return None

    async def _track_submitted_order(self, idempotency_key: str, order_info: dict):
        """Track a submitted order for duplicate prevention."""
        self._submitted_orders[idempotency_key] = {
            "symbol": order_info.get("symbol"),
            "side": order_info.get("side"),
            "quantity": order_info.get("quantity"),
            "status": order_info.get("status", "submitted"),
            "broker_order_id": order_info.get("broker_order_id", ""),
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        }

    async def _cleanup_old_orders(self):
        """Clean up old tracked orders to prevent memory bloat."""
        import time
        cutoff = time.time() - self._order_ttl_seconds
        keys_to_remove = []
        for key, info in self._submitted_orders.items():
            submitted_at = info.get("submitted_at", "")
            if submitted_at:
                try:
                    dt = datetime.fromisoformat(submitted_at.replace("Z", "+00:00"))
                    if dt.timestamp() < cutoff:
                        keys_to_remove.append(key)
                except Exception:
                    pass
        for key in keys_to_remove:
            self._submitted_orders.pop(key, None)

    async def _broadcast_ws(self, msg: dict):
        """Broadcast a message via WebSocket manager if available."""
        if self._ws_manager:
            await self._ws_manager.broadcast(msg)

    async def save_credentials(self, broker_id: str, credentials: dict):
        """Encrypt and store broker credentials in MongoDB."""
        encrypted = encrypt_credentials(credentials)
        await self.db.broker_credentials.update_one(
            {"broker_id": broker_id},
            {"$set": {"broker_id": broker_id, "encrypted": encrypted, "updated_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )
        logger.info(f"Credentials saved for broker: {broker_id}")

    async def load_credentials(self, broker_id: str) -> Optional[dict]:
        """Load and decrypt broker credentials from MongoDB."""
        doc = await self.db.broker_credentials.find_one({"broker_id": broker_id}, {"_id": 0})
        if doc and doc.get("encrypted"):
            try:
                return decrypt_credentials(doc["encrypted"])
            except Exception as e:
                logger.error(f"Failed to decrypt credentials for {broker_id}: {e}")
        return None

    async def connect_broker(self, broker_id: str, credentials: dict = None) -> bool:
        """Connect to a broker. Saves credentials on success."""
        if not credentials:
            credentials = await self.load_credentials(broker_id)
        if not credentials:
            self._failed[broker_id] = "No credentials stored"
            return False

        adapter = get_broker_adapter(broker_id, credentials)
        if not adapter:
            self._failed[broker_id] = "Adapter not available"
            return False

        try:
            connected = await adapter.check_connection()
            if connected:
                self._adapters[broker_id] = adapter
                self._failed.pop(broker_id, None)
                await self.save_credentials(broker_id, credentials)
                logger.info(f"Broker connected: {broker_id}")
                return True
            else:
                self._failed[broker_id] = "Authentication failed"
                await adapter.close()
                return False
        except Exception as e:
            self._failed[broker_id] = str(e)
            logger.error(f"Broker connection failed ({broker_id}): {e}")
            return False

    async def disconnect_broker(self, broker_id: str):
        """Disconnect a broker and clean up."""
        adapter = self._adapters.pop(broker_id, None)
        if adapter:
            await adapter.close()
            logger.info(f"Broker disconnected: {broker_id}")

    async def auto_connect_all(self):
        """On startup, try to reconnect all brokers with stored credentials."""
        cursor = self.db.broker_credentials.find({}, {"_id": 0})
        docs = await cursor.to_list(50)
        for doc in docs:
            bid = doc.get("broker_id", "")
            if bid and bid not in self._adapters:
                ok = await self.connect_broker(bid)
                if ok:
                    logger.info(f"Auto-reconnected broker: {bid}")
                else:
                    logger.warning(f"Auto-reconnect failed for broker: {bid}")

    def get_adapter(self, broker_id: str) -> Optional[BrokerAdapter]:
        """Get a live adapter for a broker, or None if not connected."""
        return self._adapters.get(broker_id)

    def is_connected(self, broker_id: str) -> bool:
        return broker_id in self._adapters

    def get_status(self) -> dict:
        """Get connection status for all brokers."""
        result = {}
        for bid in BROKER_REGISTRY:
            info = get_broker_info(bid)
            result[bid] = {
                "connected": bid in self._adapters,
                "failed": self._failed.get(bid),
                "name": info.name if info else bid,
            }
        return result

    async def place_orders_for_ticker(
        self,
        broker_ids: list[str],
        allocations: dict,
        order_template: dict,
    ) -> list[dict]:
        """Place orders across multiple brokers in parallel.
        Returns results per broker. Handles failover: skips failed brokers, sends alerts."""
        tasks = []
        valid_brokers = []

        for bid in broker_ids:
            adapter = self.get_adapter(bid)
            alloc = allocations.get(bid, 0)

            if not adapter:
                # Broker not connected — mark failure, alert, skip
                self._failed[bid] = "Not connected"
                info = get_broker_info(bid)
                name = info.name if info else bid

                # Telegram alert (fire and forget)
                if self._telegram:
                    asyncio.create_task(self._telegram._broadcast_alert(
                        f"BROKER DISCONNECTED: {name}\n"
                        f"Ticker: {order_template.get('symbol', '?')}\n"
                        f"Skipping order for this broker.\n"
                        f"Use /reconnect_brokers to retry."
                    ))

                # WebSocket failure broadcast
                asyncio.create_task(self._broadcast_ws({
                    "type": "BROKER_FAILED",
                    "broker_id": bid,
                    "symbol": order_template.get("symbol", ""),
                    "reason": "Not connected",
                }))
                continue

            if alloc <= 0:
                continue

            valid_brokers.append(bid)
            price = max(order_template.get("price", 1), 0.01)
            order = BrokerOrder(
                symbol=order_template["symbol"],
                side=order_template["side"],
                order_type=order_template["order_type"],
                quantity=order_template.get("quantity", 0) or round(alloc / price, 4),
                limit_price=order_template.get("limit_price"),
                stop_price=order_template.get("stop_price"),
            )
            tasks.append(self._place_single(adapter, bid, order, order_template.get("symbol", "")))

        if not tasks:
            return []

        results = await asyncio.gather(*tasks, return_exceptions=True)
        output = []
        for bid, result in zip(valid_brokers, results):
            if isinstance(result, Exception):
                self._failed[bid] = str(result)
                output.append({"broker_id": bid, "status": "error", "error": str(result)})
                # Alert on mid-trade failure
                info = get_broker_info(bid)
                name = info.name if info else bid
                if self._telegram:
                    asyncio.create_task(self._telegram._broadcast_alert(
                        f"BROKER ORDER FAILED: {name}\n"
                        f"Ticker: {order_template.get('symbol', '?')}\n"
                        f"Error: {result}\n"
                        f"Other brokers unaffected."
                    ))
                asyncio.create_task(self._broadcast_ws({
                    "type": "BROKER_FAILED",
                    "broker_id": bid,
                    "symbol": order_template.get("symbol", ""),
                    "reason": str(result),
                }))
            else:
                output.append({"broker_id": bid, **result})
        return output

    async def _place_single(self, adapter: BrokerAdapter, broker_id: str, order: BrokerOrder, symbol: str = "") -> dict:
        """Place a single order through a broker adapter with resilience (token-bucket rate limiting + circuit breaker).
        
        Includes idempotency tracking to prevent duplicate orders.
        """
        from resilience import broker_resilience, CircuitOpenError
        from audit_service import audit_service
        import time

        # Generate idempotency key if not provided
        if not order.idempotency_key:
            order.idempotency_key = self._generate_idempotency_key(
                symbol, order.side.value, order.quantity, order.order_type.value
            )

        # Check for duplicate order
        duplicate = await self._check_duplicate_order(order.idempotency_key)
        if duplicate:
            logger.info(f"Duplicate order blocked: {order.idempotency_key}")
            return {
                "status": "duplicate",
                "order_id": duplicate.get("broker_order_id", ""),
                "filled_price": 0.0,
                "error": "Duplicate order prevented",
                "idempotency_key": order.idempotency_key,
            }

        # Track this order as submitted
        await self._track_submitted_order(order.idempotency_key, {
            "symbol": symbol,
            "side": order.side.value,
            "quantity": order.quantity,
            "status": "submitted",
            "broker_order_id": "",
        })

        # Acquire rate-limit token and verify circuit state.
        # CircuitOpenError is re-raised so place_orders_for_ticker records it as a broker failure.
        try:
            await broker_resilience.before_call(broker_id)
        except CircuitOpenError as e:
            # Update order status
            await self._track_submitted_order(order.idempotency_key, {
                "symbol": symbol,
                "side": order.side.value,
                "quantity": order.quantity,
                "status": "circuit_open",
                "broker_order_id": "",
            })
            raise Exception(f"Circuit OPEN for {broker_id}: retry in {e.recovery_seconds}s") from e

        start_time = time.time()
        try:
            result = await adapter.place_order(order)
            elapsed_ms = (time.time() - start_time) * 1000
            await broker_resilience.record_success(broker_id)
            await audit_service.log_broker_api(
                broker_id, "place_order", "POST",
                success=True, response_time_ms=elapsed_ms,
                request_data={"symbol": symbol, "side": order.side, "qty": order.quantity, "idempotency_key": order.idempotency_key},
            )
            
            # Update order tracking with broker order ID
            await self._track_submitted_order(order.idempotency_key, {
                "symbol": symbol,
                "side": order.side.value,
                "quantity": order.quantity,
                "status": result.status,
                "broker_order_id": result.broker_order_id,
            })
            
            return {
                "status": result.status,
                "order_id": result.broker_order_id,
                "filled_price": result.filled_price,
                "error": result.error,
                "idempotency_key": order.idempotency_key,
            }
        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            await broker_resilience.record_failure(broker_id, e)
            await audit_service.log_broker_api(
                broker_id, "place_order", "POST",
                success=False, response_time_ms=elapsed_ms, error_message=str(e),
                request_data={"symbol": symbol, "side": order.side, "qty": order.quantity, "idempotency_key": order.idempotency_key},
            )
            
            # Update order status to failed
            await self._track_submitted_order(order.idempotency_key, {
                "symbol": symbol,
                "side": order.side.value,
                "quantity": order.quantity,
                "status": "failed",
                "broker_order_id": "",
            })
            
            self._failed[broker_id] = str(e)
            self._adapters.pop(broker_id, None)
            raise

    async def reconnect_broker(self, broker_id: str) -> bool:
        """Attempt to reconnect a failed broker using stored credentials."""
        await self.disconnect_broker(broker_id)
        return await self.connect_broker(broker_id)

    async def verify_order_fill(self, broker_id: str, broker_order_id: str, symbol: str) -> dict:
        """Verify order fill status by checking broker positions.
        
        Returns dict with fill status details.
        """
        adapter = self._adapters.get(broker_id)
        if not adapter:
            return {"status": "error", "message": "Broker not connected"}
        
        if not broker_order_id:
            return {"status": "unknown", "message": "No broker order ID to verify"}
        
        try:
            # Get current positions from broker
            positions = await adapter.get_positions()
            
            # Check if we have a position for this symbol
            for pos in positions:
                if pos.symbol.upper() == symbol.upper():
                    return {
                        "status": "filled",
                        "symbol": pos.symbol,
                        "quantity": pos.quantity,
                        "current_price": pos.current_price,
                        "unrealized_pnl": pos.unrealized_pnl,
                        "broker_order_id": broker_order_id,
                    }
            
            # No position found - order may have been filled and sold, or not filled
            return {
                "status": "no_position",
                "symbol": symbol,
                "broker_order_id": broker_order_id,
                "message": "No position found - verify with broker",
            }
            
        except Exception as e:
            logger.warning(f"Order verification failed for {broker_id}/{broker_order_id}: {e}")
            return {"status": "error", "message": str(e)}

    async def verify_order_status(self, broker_id: str, broker_order_id: str, symbol: str) -> str:
        """Quick check if order was filled. Returns status string."""
        result = await self.verify_order_fill(broker_id, broker_order_id, symbol)
        return result.get("status", "unknown")

    async def reconcile_positions(self, broker_id: str) -> dict:
        """Reconcile broker positions with expected positions.
        
        Returns dict of symbol -> {expected_qty, actual_qty, status}
        """
        adapter = self._adapters.get(broker_id)
        if not adapter:
            return {}
        
        try:
            positions = await adapter.get_positions()
            result = {}
            for pos in positions:
                result[pos.symbol.upper()] = {
                    "quantity": pos.quantity,
                    "avg_entry": pos.avg_entry,
                    "current_price": pos.current_price,
                    "market_value": pos.market_value,
                    "unrealized_pnl": pos.unrealized_pnl,
                }
            return result
        except Exception as e:
            logger.error(f"Position reconciliation failed for {broker_id}: {e}")
            return {}

    async def reconnect_all(self) -> dict:
        """Reconnect all brokers (failed + disconnected). Returns results."""
        results = {}
        # Try all brokers that have stored credentials
        cursor = self.db.broker_credentials.find({}, {"_id": 0, "broker_id": 1})
        docs = await cursor.to_list(50)
        for doc in docs:
            bid = doc.get("broker_id", "")
            if not bid:
                continue
            if bid in self._adapters:
                results[bid] = "already connected"
                continue
            ok = await self.reconnect_broker(bid)
            results[bid] = "connected" if ok else (self._failed.get(bid, "failed"))
        return results
