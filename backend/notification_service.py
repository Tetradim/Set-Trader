"""Notification service for trade alerts, system events, and webhooks."""
import asyncio
import logging
import os
import time
import json
from collections import deque
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

import deps

logger = logging.getLogger("SentinelPulse")

# Rate limiting
MAX_ALERTS_PER_MINUTE = 10
_alert_timestamps: deque[float] = deque()


def _check_rate_limit() -> bool:
    """Check if alert rate limit is exceeded."""
    global _alert_timestamps
    now = time.time()
    cutoff = now - 60
    while _alert_timestamps and _alert_timestamps[0] < cutoff:
        _alert_timestamps.popleft()
    if len(_alert_timestamps) >= MAX_ALERTS_PER_MINUTE:
        return False
    _alert_timestamps.append(now)
    return True


@dataclass
class NotificationConfig:
    """Notification channel configuration."""
    slack_webhook_url: str = ""
    slack_enabled: bool = False
    discord_webhook_url: str = ""
    discord_enabled: bool = False
    webhook_urls: List[str] = field(default_factory=list)
    webhook_enabled: bool = False
    email_enabled: bool = False
    # Rate limiting per channel
    max_per_minute: int = 10


class NotificationService:
    """Central notification service for all alert channels."""

    def __init__(self):
        self.config = NotificationConfig()
        self._session: Optional[Any] = None

    async def _get_session(self):
        """Get or create aiohttp session."""
        if self._session is None:
            import aiohttp
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        """Close the HTTP session."""
        if self._session:
            await self._session.close()
            self._session = None

    async def load_config(self):
        """Load notification config from database."""
        doc = await deps.db.settings.find_one({"key": "notifications"}, {"_id": 0})
        if doc and doc.get("value"):
            value = doc["value"]
            self.config.slack_webhook_url = value.get("slack_webhook_url", "")
            self.config.slack_enabled = value.get("slack_enabled", False)
            self.config.discord_webhook_url = value.get("discord_webhook_url", "")
            self.config.discord_enabled = value.get("discord_enabled", False)
            self.config.webhook_urls = value.get("webhook_urls", [])
            self.config.webhook_enabled = value.get("webhook_enabled", False)
            self.config.email_enabled = value.get("email_enabled", False)
            logger.info("Notification config loaded: slack=%s, discord=%s, webhook=%s",
                      self.config.slack_enabled, self.config.discord_enabled, self.config.webhook_enabled)

    async def save_config(self):
        """Save notification config to database."""
        value = {
            "slack_webhook_url": self.config.slack_webhook_url,
            "slack_enabled": self.config.slack_enabled,
            "discord_webhook_url": self.config.discord_webhook_url,
            "discord_enabled": self.config.discord_enabled,
            "webhook_urls": self.config.webhook_urls,
            "webhook_enabled": self.config.webhook_enabled,
            "email_enabled": self.config.email_enabled,
        }
        await deps.db.settings.update_one(
            {"key": "notifications"},
            {"$set": {"value": value}},
            upsert=True,
        )
        logger.info("Notification config saved")

    async def update_config(self, config: NotificationConfig):
        """Update notification config."""
        self.config = config
        await self.save_config()

    # ---------------------------------------------------------------------------
    # Send methods
    # ---------------------------------------------------------------------------

    async def send_trade_alert(self, trade: Dict[str, Any]):
        """Send trade alert to all enabled channels."""
        if not _check_rate_limit():
            logger.warning("Notification rate limit exceeded - trade alert skipped")
            return

        side = trade.get("side", "?")
        sym = trade.get("symbol", "?")
        price = trade.get("price", 0)
        qty = trade.get("quantity", 0)
        pnl = trade.get("pnl", 0)
        order_type = trade.get("order_type", "")
        reason = trade.get("reason", "")

        # Build message
        pnl_emoji = "🟢" if pnl >= 0 else "🔴"
        msg = (
            f"*{pnl_emoji} TRADE {order_type} {side} {sym}*\n"
            f"• Price: ${price:.2f}\n"
            f"• Qty: {qty:.4f}\n"
            f"• P&L: {f'+${pnl:.2f}' if pnl >= 0 else f'-${abs(pnl):.2f}'}\n"
            f"• Reason: {reason}"
        )

        # Send to each channel
        if self.config.slack_enabled:
            await self._send_slack(msg)
        if self.config.discord_enabled:
            await self._send_discord(msg)
        if self.config.webhook_enabled:
            await self._send_webhooks(msg, trade)

    async def send_system_alert(self, title: str, message: str, severity: str = "info"):
        """Send system alert."""
        if not _check_rate_limit():
            logger.warning("Notification rate limit exceeded - system alert skipped")
            return

        emoji = {
            "info": "ℹ️",
            "warning": "⚠️",
            "error": "❌",
            "success": "✅",
        }.get(severity, "ℹ️")

        msg = f"*{emoji} {title}*\n{message}"

        if self.config.slack_enabled:
            await self._send_slack(msg)
        if self.config.discord_enabled:
            await self._send_discord(msg)
        if self.config.webhook_enabled:
            await self._send_webhooks(msg, {"title": title, "message": message, "severity": severity})

    # ---------------------------------------------------------------------------
    # Channel implementations
    # ---------------------------------------------------------------------------

    async def _send_slack(self, text: str):
        """Send message to Slack webhook."""
        if not self.config.slack_webhook_url:
            return

        try:
            session = await self._get_session()
            payload = {"text": text}
            async with session.post(self.config.slack_webhook_url, json=payload) as resp:
                if resp.status == 200:
                    logger.info("Slack notification sent")
                else:
                    logger.warning(f"Slack notification failed: {resp.status}")
        except Exception as e:
            logger.error(f"Slack notification error: {e}")

    async def _send_discord(self, text: str):
        """Send message to Discord webhook."""
        if not self.config.discord_webhook_url:
            return

        try:
            session = await self._get_session()
            payload = {"content": text}
            async with session.post(self.config.discord_webhook_url, json=payload) as resp:
                if resp.status == 204:
                    logger.info("Discord notification sent")
                else:
                    logger.warning(f"Discord notification failed: {resp.status}")
        except Exception as e:
            logger.error(f"Discord notification error: {e}")

    async def _send_webhooks(self, text: str, data: Dict[str, Any]):
        """Send to custom webhook URLs."""
        if not self.config.webhook_urls:
            return

        payload = {
            "text": text,
            "data": data,
            "timestamp": time.time(),
            "source": "SentinelPulse",
        }

        for url in self.config.webhook_urls:
            try:
                session = await self._get_session()
                async with session.post(url, json=payload) as resp:
                    if resp.status < 400:
                        logger.info(f"Webhook notification sent to {url}")
                    else:
                        logger.warning(f"Webhook failed {url}: {resp.status}")
            except Exception as e:
                logger.error(f"Webhook notification error: {e}")


# Global instance
notification_service = NotificationService()