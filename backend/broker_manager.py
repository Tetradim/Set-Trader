"""Broker connection manager — stores credentials, manages live connections, handles failover."""
import asyncio
import logging
import base64
import os
from datetime import datetime, timezone
from typing import Optional
from brokers import BrokerAdapter, BrokerOrder, get_broker_adapter, get_broker_info, BROKER_REGISTRY

logger = logging.getLogger("SentinelPulse")

# Simple XOR-based obfuscation for credentials at rest.
# For production, replace with a proper encryption library (cryptography.fernet).
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
        self._adapters: dict[str, BrokerAdapter] = {}  # broker_id -> live adapter
        self._failed: dict[str, str] = {}  # broker_id -> failure reason
        self._telegram = None  # set externally

    def set_telegram(self, telegram_service):
        self._telegram = telegram_service

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

    async def place_orders_parallel(self, broker_ids: list[str], allocations: dict, order_template: dict) -> list[dict]:
        """Place orders across multiple brokers in parallel. Returns results per broker.
        Handles failover: skips failed brokers, sends Telegram alerts."""
        tasks = []
        valid_brokers = []

        for bid in broker_ids:
            adapter = self.get_adapter(bid)
            alloc = allocations.get(bid, 0)
            if not adapter:
                self._failed[bid] = "Not connected"
                # Alert via Telegram
                info = get_broker_info(bid)
                name = info.name if info else bid
                if self._telegram:
                    asyncio.create_task(self._telegram._broadcast_alert(
                        f"BROKER DISCONNECTED: {name}\n"
                        f"Skipping order for this broker.\n"
                        f"Use /reconnect {bid} to retry."
                    ))
                # Broadcast failure to WebSocket
                from server import ws_manager
                asyncio.create_task(ws_manager.broadcast({
                    "type": "BROKER_FAILED",
                    "broker_id": bid,
                    "reason": self._failed.get(bid, "Not connected"),
                }))
                continue
            if alloc <= 0:
                continue
            valid_brokers.append(bid)
            order = BrokerOrder(
                symbol=order_template["symbol"],
                side=order_template["side"],
                order_type=order_template["order_type"],
                quantity=order_template.get("quantity", 0) or round(alloc / max(order_template.get("price", 1), 0.01), 4),
                limit_price=order_template.get("limit_price"),
                stop_price=order_template.get("stop_price"),
            )
            tasks.append(self._place_single(adapter, bid, order))

        if not tasks:
            return []

        results = await asyncio.gather(*tasks, return_exceptions=True)
        output = []
        for bid, result in zip(valid_brokers, results):
            if isinstance(result, Exception):
                self._failed[bid] = str(result)
                output.append({"broker_id": bid, "status": "error", "error": str(result)})
            else:
                output.append({"broker_id": bid, **result})
        return output

    async def _place_single(self, adapter: BrokerAdapter, broker_id: str, order: BrokerOrder) -> dict:
        """Place a single order through a broker adapter."""
        try:
            result = await adapter.place_order(order)
            return {
                "status": result.status,
                "order_id": result.broker_order_id,
                "filled_price": result.filled_price,
                "error": result.error,
            }
        except Exception as e:
            # Connection failed mid-trade — mark broker as failed
            self._failed[broker_id] = str(e)
            self._adapters.pop(broker_id, None)
            raise

    async def reconnect_broker(self, broker_id: str) -> bool:
        """Attempt to reconnect a failed broker using stored credentials."""
        await self.disconnect_broker(broker_id)
        return await self.connect_broker(broker_id)

    async def reconnect_all_failed(self) -> dict:
        """Reconnect all failed brokers. Returns results."""
        results = {}
        for bid in list(self._failed.keys()):
            ok = await self.reconnect_broker(bid)
            results[bid] = "connected" if ok else self._failed.get(bid, "failed")
        return results
