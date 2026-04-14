"""MongoDB client for sending commands to Edge.

This module provides a client for Pulse to communicate with Edge via MongoDB.
Pulse inserts command documents into the commands collection that Edge
consumes via change streams.
"""
import os
import logging
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
    ):
        """Initialize the Edge MongoDB client.
        
        Args:
            mongo_url: MongoDB connection URL. Defaults to MONGO_URL from env.
            db_name: Database name for commands. Defaults to "edge".
            commands_collection: Collection name for commands. Defaults to "commands".
        """
        self.mongo_url = mongo_url or os.environ.get("EDGE_MONGO_URL", os.environ.get("MONGO_URL", ""))
        self.db_name = db_name
        self.commands_collection = commands_collection
        
        self._client: Optional[AsyncIOMotorClient] = None
        self._db: Optional[AsyncIOMotorDatabase] = None
        self._enabled = False
        
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
            
        try:
            self._client = AsyncIOMotorClient(self.mongo_url)
            self._db = self._client[self.db_name]
            
            # Verify connection
            await self._client.admin.command("ping")
            
            # Ensure indexes
            await self._db[self.commands_collection].create_index("command_type")
            await self._db[self.commands_collection].create_index("timestamp")
            await self._db[self.commands_collection].create_index("symbol")
            
            logger.info(f"Connected to Edge MongoDB: {self.db_name}")
        except PyMongoError as e:
            logger.error(f"Failed to connect to Edge MongoDB: {e}")
            self._enabled = False
    
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
        return self._db is not None
    
    async def insert_command(self, command: Dict[str, Any]) -> bool:
        """Insert a command document into the commands collection.
        
        Args:
            command: Command document to insert.
            
        Returns:
            True if successful, False otherwise.
        """
        if not self._enabled or not self._db:
            return False
        
        try:
            result = await self._db[self.commands_collection].insert_one(command)
            logger.debug(f"Inserted command: {command.get('command_type')} (id: {result.inserted_id})")
            return True
        except PyMongoError as e:
            logger.error(f"Failed to insert command: {e}")
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
        if not self._enabled or not self._db or not positions:
            return 0
        
        try:
            # Add command_type to each position
            commands = [
                {**pos, "command_type": CommandType.POSITION_UPDATE}
                for pos in positions
            ]
            result = await self._db[self.commands_collection].insert_many(commands)
            logger.debug(f"Batch inserted {len(result.inserted_ids)} position updates")
            return len(result.inserted_ids)
        except PyMongoError as e:
            logger.error(f"Failed to batch insert positions: {e}")
            return 0


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