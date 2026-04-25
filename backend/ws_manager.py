"""WebSocket connection manager with backpressure handling."""
import asyncio
import logging
from collections import deque
from fastapi import WebSocket
from datetime import datetime, timezone

logger = logging.getLogger("SentinelPulse")


class ConnectionManager:
    """WebSocket connection manager with queue-based broadcasting."""
    
    def __init__(self, max_queue_size: int = 100, broadcast_interval: float = 0.1):
        self.active: list[WebSocket] = []
        # Queue-based broadcasting to handle backpressure
        self._message_queue: deque = deque(maxlen=max_queue_size)
        self._broadcast_task: asyncio.Task = None
        self._broadcast_interval = broadcast_interval  # 100ms default
        self._running = False
        
        # Metrics
        self._messages_sent = 0
        self._messages_dropped = 0
        self._last_broadcast_error: datetime = None
    
    async def start_broadcast_loop(self):
        """Start the background broadcast task."""
        if self._running:
            return
        self._running = True
        self._broadcast_task = asyncio.create_task(self._broadcast_loop())
        logger.info("WebSocket broadcast loop started")
    
    async def stop_broadcast_loop(self):
        """Stop the background broadcast task gracefully."""
        self._running = False
        if self._broadcast_task:
            self._broadcast_task.cancel()
            try:
                await self._broadcast_task
            except asyncio.CancelledError:
                pass
        logger.info("WebSocket broadcast loop stopped")
    
    async def _broadcast_loop(self):
        """Background task that batches and sends messages."""
        while self._running:
            try:
                # Batch messages
                if self._message_queue:
                    batch = []
                    while self._message_queue and len(batch) < 50:
                        batch.append(self._message_queue.popleft())
                    
                    await self._send_batch(batch)
                
                await asyncio.sleep(self._broadcast_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Broadcast loop error: {e}", exc_info=True)
                await asyncio.sleep(1)  # Brief pause on error
    
    async def _send_batch(self, messages: list):
        """Send a batch of messages to all connections."""
        dead = []
        
        for ws in self.active:
            try:
                await ws.send_json(messages)
                self._messages_sent += len(messages)
            except Exception as e:
                logger.debug(f"WS send error: {e}")
                dead.append(ws)
        
        # Remove dead connections
        for ws in dead:
            self.disconnect(ws)
            logger.info(f"Removed dead WebSocket connection, {len(self.active)} remaining")
    
    async def connect(self, ws: WebSocket):
        """Accept and track a new WebSocket connection."""
        await ws.accept()
        self.active.append(ws)
        logger.debug(f"WebSocket connected, total: {len(self.active)}")

    def disconnect(self, ws: WebSocket):
        """Remove a WebSocket connection."""
        if ws in self.active:
            self.active.remove(ws)
            logger.debug(f"WebSocket disconnected, remaining: {len(self.active)}")

    async def broadcast(self, msg: dict):
        """
        Queue a message for broadcast (non-blocking).
        Uses queue to handle backpressure when clients are slow.
        """
        if not self._running:
            await self.start_broadcast_loop()
        
        try:
            self._message_queue.append(msg)
        except IndexError:
            # Queue full - drop oldest message
            self._message_queue.popleft()
            self._message_queue.append(msg)
            self._messages_dropped += 1
            logger.warning(f"WS message queue full, dropped oldest. Total dropped: {self._messages_dropped}")
    
    async def broadcast_immediate(self, msg: dict):
        """Send a message immediately (bypasses queue, for critical alerts)."""
        await self._send_batch([msg])
    
    def get_stats(self) -> dict:
        """Get connection statistics."""
        return {
            "active_connections": len(self.active),
            "queue_size": len(self._message_queue),
            "queue_capacity": self._message_queue.maxlen,
            "messages_sent": self._messages_sent,
            "messages_dropped": self._messages_dropped,
            "running": self._running,
        }
