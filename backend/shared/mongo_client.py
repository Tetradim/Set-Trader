"""MongoDB client for sending commands to Edge.

This module provides a client for Pulse to communicate with Edge via MongoDB.
Pulse inserts command documents into the commands collection that Edge
consumes via change streams.
"""
import os
import logging
import time
from typing import Optional, Dict, Any, List

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import PyMongoError

from shared.commands import (
    CommandType,
    OrderFilled,
    PositionUpdate,
    AccountUpdate,
    PulseStatus,
    BrokerStatus,
    AutoStopTriggered,
)

logger = logging.getLogger("SentinelPulse.EdgeClient")


class EdgeMongoClient:
    """MongoDB client for Edge communication.
    
    Provides methods to send commands to Edge's MongoDB instance.
    Pulse uses this to notify Edge about trades, positions, and status.
    """
    
    def __init__(
        self,
        mongo_url: Optional[str] = None,
        db_name: str = "edge",
        commands_collection: str = "commands",
        base_retry_delay: int = 5,
        max_retry_delay: int = 300,
        connect_timeout_ms: int = 2000,
        max_retry_attempts: int = 10,
    ):
        """Initialize the Edge MongoDB client.
        
        Args:
            mongo_url: MongoDB connection URL. Defaults to MONGO_URL from env.
            db_name: Database name for commands. Defaults to "edge".
            commands_collection: Collection name for commands. Defaults to "commands".
        """
        # Do not fall back to Pulse's own MongoDB URL here. A local Pulse MongoDB
        # ping only proves Pulse storage exists; it does not prove Sentinel Edge is
        # running or consuming the command channel.
        self.mongo_url = mongo_url if mongo_url is not None else os.environ.get("EDGE_MONGO_URL", "")
        self.db_name = db_name
        self.commands_collection = commands_collection
        self.base_retry_delay = base_retry_delay
        self.max_retry_delay = max_retry_delay
        self.connect_timeout_ms = connect_timeout_ms
        self.max_retry_attempts = max(0, int(max_retry_attempts))
        
        self._client: Optional[AsyncIOMotorClient] = None
        self._db: Optional[AsyncIOMotorDatabase] = None
        self._enabled = False
        self._has_ever_connected = False
        self._last_error = ""
        self._last_success_at: Optional[float] = None
        self._last_send_at: Optional[float] = None
        self._consecutive_failures = 0
        self._retry_delay_seconds = 0
        self._next_retry_at: Optional[float] = None
        self._command_counts: Dict[str, int] = {}
        
        # Check if configuration is present
        if self.mongo_url:
            self._enabled = True
            logger.info(f"Edge MongoDB client configured: {self.db_name}.{self.commands_collection}")
        else:
            logger.warning("Edge MongoDB URL not configured - Edge integration disabled")
    
    async def connect(self) -> None:
        """Connect to MongoDB."""
        if not self._enabled:
            logger.debug("Edge client disabled - skipping connect")
            return
        if self.retry_exhausted:
            logger.debug("Edge retry attempt limit reached - skipping connect")
            return
        if self._is_backoff_active():
            logger.debug("Edge retry backoff active - skipping connect")
            return
            
        try:
            self._client = AsyncIOMotorClient(
                self.mongo_url,
                serverSelectionTimeoutMS=self.connect_timeout_ms,
                connectTimeoutMS=self.connect_timeout_ms,
            )
            self._db = self._client[self.db_name]
            
            # Verify connection
            await self._client.admin.command("ping")
            
            # Ensure indexes
            await self._db[self.commands_collection].create_index("command_type")
            await self._db[self.commands_collection].create_index("timestamp")
            await self._db[self.commands_collection].create_index("symbol")
            
            was_previously_connected = self._has_ever_connected
            self._has_ever_connected = True
            if not was_previously_connected:
                self._mark_success()
            logger.info(f"Connected to Edge MongoDB: {self.db_name}")
        except PyMongoError as e:
            logger.error(f"Failed to connect to Edge MongoDB: {e}")
            self._db = None
            if self._client:
                self._client.close()
                self._client = None
            self._mark_failure(str(e))
    
    async def close(self) -> None:
        """Close the MongoDB connection."""
        if self._client:
            self._client.close()
            self._client = None
            self._db = None
            logger.info("Edge MongoDB client closed")
    
    @property
    def is_enabled(self) -> bool:
        """Check if Edge integration is enabled."""
        return self._enabled
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to MongoDB."""
        # More robust check: verify _db is not None AND is a valid database object
        if self._db is None:
            return False
        try:
            return self._client is not None
        except Exception:
            return False

    @property
    def has_ever_connected(self) -> bool:
        """Whether Pulse has successfully connected to Edge in this process."""
        return self._has_ever_connected

    @property
    def last_error(self) -> str:
        """Most recent Edge connection or send error."""
        return self._last_error

    @property
    def retry_delay_seconds(self) -> int:
        """Current exponential retry delay in seconds."""
        return self._retry_delay_seconds

    @property
    def next_retry_at(self) -> Optional[float]:
        """Monotonic timestamp when the next retry is allowed."""
        return self._next_retry_at

    @property
    def consecutive_failures(self) -> int:
        """Number of consecutive failures after a successful Edge connection."""
        return self._consecutive_failures

    @property
    def retry_exhausted(self) -> bool:
        """Whether the post-connection retry attempt limit has been reached."""
        return self._has_ever_connected and self._consecutive_failures >= self.max_retry_attempts

    def set_max_retry_attempts(self, attempts: int) -> None:
        """Update the retry attempt limit from persisted settings."""
        self.max_retry_attempts = max(0, int(attempts))

    def clear_retry_backoff_for_test(self) -> None:
        """Clear retry gate for deterministic unit tests."""
        self._next_retry_at = None

    def status_snapshot(self) -> Dict[str, Any]:
        """Return Edge communication health without exposing credentials."""
        return {
            "configured": bool(self.mongo_url),
            "identity": "explicit_edge_mongo_url" if self.mongo_url else "not_configured",
            "enabled": self.is_enabled,
            "connected": self.is_connected,
            "has_ever_connected": self.has_ever_connected,
            "last_error": self.last_error,
            "last_success_at": self._last_success_at,
            "last_send_at": self._last_send_at,
            "consecutive_failures": self._consecutive_failures,
            "retry_delay_seconds": self.retry_delay_seconds,
            "max_retry_attempts": self.max_retry_attempts,
            "retry_exhausted": self.retry_exhausted,
            "next_retry_at": self.next_retry_at,
            "commands_collection": f"{self.db_name}.{self.commands_collection}",
            "command_counts": dict(self._command_counts),
        }
    
    async def insert_command(self, command: Dict[str, Any]) -> bool:
        """Insert a command document into the commands collection.
        
        Args:
            command: Command document to insert.
            
        Returns:
            True if successful, False otherwise.
        """
        if not self._enabled:
            return False
        if self.retry_exhausted:
            return False
        if self._db is None:
            await self.connect()
        if self._db is None:
            return False
        if self._is_backoff_active():
            return False
        
        try:
            result = await self._db[self.commands_collection].insert_one(command)
            command_type = self._command_count_key(command.get("command_type", "UNKNOWN"))
            self._command_counts[command_type] = self._command_counts.get(command_type, 0) + 1
            self._last_send_at = time.time()
            self._mark_success()
            logger.debug(f"Inserted command: {command.get('command_type')} (id: {result.inserted_id})")
            return True
        except PyMongoError as e:
            logger.error(f"Failed to insert command: {e}")
            self._db = None
            if self._client:
                self._client.close()
                self._client = None
            self._mark_failure(str(e))
            return False
    
    # --- Convenience methods for each command type ---
    
    async def send_order_filled(self, order: OrderFilled) -> bool:
        """Send an ORDER_FILLED command after a trade executes."""
        return await self.insert_command(order.model_dump())
    
    async def send_position_update(self, update: PositionUpdate) -> bool:
        """Send a POSITION_UPDATE command."""
        return await self.insert_command(update.model_dump())
    
    async def send_account_update(self, update: AccountUpdate) -> bool:
        """Send an ACCOUNT_UPDATE command."""
        return await self.insert_command(update.model_dump())
    
    async def send_pulse_status(self, status: PulseStatus) -> bool:
        """Send a PULSE_STATUS heartbeat."""
        return await self.insert_command(status.model_dump())
    
    async def send_broker_status(self, status: BrokerStatus) -> bool:
        """Send a BROKER_STATUS update."""
        return await self.insert_command(status.model_dump())
    
    async def send_auto_stop_triggered(self, stop: AutoStopTriggered) -> bool:
        """Send an AUTO_STOP_TRIGGERED event."""
        return await self.insert_command(stop.model_dump())
    
    # --- Batch operations ---
    
    async def send_position_batch(self, positions: List[Dict[str, Any]]) -> int:
        """Send multiple position updates in a batch.
        
        Args:
            positions: List of position update dictionaries.
            
        Returns:
            Number of successfully inserted documents.
        """
        if not self._enabled or not positions:
            return 0
        if self.retry_exhausted:
            return 0
        if self._db is None:
            await self.connect()
        if self._db is None or self._is_backoff_active():
            return 0
        
        try:
            # Add command_type to each position
            commands = [
                {**pos, "command_type": CommandType.POSITION_UPDATE}
                for pos in positions
            ]
            result = await self._db[self.commands_collection].insert_many(commands)
            inserted_count = len(result.inserted_ids)
            command_type = self._command_count_key(CommandType.POSITION_UPDATE)
            self._command_counts[command_type] = self._command_counts.get(command_type, 0) + inserted_count
            self._last_send_at = time.time()
            self._mark_success()
            logger.debug(f"Batch inserted {len(result.inserted_ids)} position updates")
            return inserted_count
        except PyMongoError as e:
            logger.error(f"Failed to batch insert positions: {e}")
            self._db = None
            if self._client:
                self._client.close()
                self._client = None
            self._mark_failure(str(e))
            return 0

    def _mark_success(self) -> None:
        self._last_error = ""
        self._last_success_at = time.time()
        self._consecutive_failures = 0
        self._retry_delay_seconds = 0
        self._next_retry_at = None

    def _mark_failure(self, error: str) -> None:
        self._last_error = error
        if not self._has_ever_connected:
            self._consecutive_failures = 0
            self._retry_delay_seconds = 0
            self._next_retry_at = None
            return
        self._consecutive_failures += 1
        delay = self.base_retry_delay * (2 ** (self._consecutive_failures - 1))
        self._retry_delay_seconds = min(delay, self.max_retry_delay)
        self._next_retry_at = time.monotonic() + self._retry_delay_seconds

    def _is_backoff_active(self) -> bool:
        return self._next_retry_at is not None and time.monotonic() < self._next_retry_at

    @staticmethod
    def _command_count_key(command_type: Any) -> str:
        return getattr(command_type, "value", str(command_type))


# --- Singleton instance ---
# Initialize with defaults from environment
edge_client = EdgeMongoClient()


async def init_edge_client() -> EdgeMongoClient:
    """Initialize and connect the Edge client.
    
    Call this during application startup.
    
    Returns:
        Initialized EdgeMongoClient instance.
    """
    await edge_client.connect()
    return edge_client
