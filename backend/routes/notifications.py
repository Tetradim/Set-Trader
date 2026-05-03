"""Notification management routes."""
from typing import Optional, List
from fastapi import APIRouter, Query, Body
from pydantic import BaseModel

import deps
from notification_service import notification_service, NotificationConfig
from audit_service import audit_service

router = APIRouter(tags=["Notifications"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class NotificationSettings(BaseModel):
    slack_webhook_url: Optional[str] = None
    slack_enabled: Optional[bool] = None
    discord_webhook_url: Optional[str] = None
    discord_enabled: Optional[bool] = None
    webhook_urls: Optional[List[str]] = None
    webhook_enabled: Optional[bool] = None
    email_enabled: Optional[bool] = None


class TestNotificationRequest(BaseModel):
    channel: str = "slack"  # slack, discord, webhook


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/notifications")
async def get_notification_settings():
    """Get current notification settings."""
    return {
        "slack_webhook_url": notification_service.config.slack_webhook_url,
        "slack_enabled": notification_service.config.slack_enabled,
        "discord_webhook_url": notification_service.config.discord_webhook_url,
        "discord_enabled": notification_service.config.discord_enabled,
        "webhook_urls": notification_service.config.webhook_urls,
        "webhook_enabled": notification_service.config.webhook_enabled,
        "email_enabled": notification_service.config.email_enabled,
    }


@router.post("/notifications")
async def update_notification_settings(settings: NotificationSettings):
    """Update notification settings."""
    # Update config
    if settings.slack_webhook_url is not None:
        notification_service.config.slack_webhook_url = settings.slack_webhook_url
    if settings.slack_enabled is not None:
        notification_service.config.slack_enabled = settings.slack_enabled
    if settings.discord_webhook_url is not None:
        notification_service.config.discord_webhook_url = settings.discord_webhook_url
    if settings.discord_enabled is not None:
        notification_service.config.discord_enabled = settings.discord_enabled
    if settings.webhook_urls is not None:
        notification_service.config.webhook_urls = settings.webhook_urls
    if settings.webhook_enabled is not None:
        notification_service.config.webhook_enabled = settings.webhook_enabled
    if settings.email_enabled is not None:
        notification_service.config.email_enabled = settings.email_enabled

    # Save to database
    await notification_service.save_config()

    # Log change
    await audit_service.log_setting_change(
        "notifications",
        {},
        {
            "slack_enabled": notification_service.config.slack_enabled,
            "discord_enabled": notification_service.config.discord_enabled,
            "webhook_enabled": notification_service.config.webhook_enabled,
            "email_enabled": notification_service.config.email_enabled,
        },
    )

    return {"ok": True, "message": "Notification settings updated"}


@router.post("/notifications/test")
async def test_notification_channel(req: TestNotificationRequest):
    """Send a test notification to the specified channel."""
    test_message = "🔔 Test notification from Sentinel Pulse"

    channel = req.channel.lower()
    success = False
    error = None

    try:
        if channel == "slack":
            if not notification_service.config.slack_webhook_url:
                error = "Slack webhook not configured"
            else:
                await notification_service._send_slack(test_message)
                success = True
        elif channel == "discord":
            if not notification_service.config.discord_webhook_url:
                error = "Discord webhook not configured"
            else:
                await notification_service._send_discord(test_message)
                success = True
        elif channel == "webhook":
            if not notification_service.config.webhook_urls:
                error = "Webhook URLs not configured"
            else:
                await notification_service._send_webhooks(test_message, {"test": True})
                success = True
        elif channel == "email":
            if not notification_service.config.email_enabled:
                error = "Email notifications not enabled"
            else:
                # Import email service
                from email_service import send_email
                result = send_email("Sentinel Pulse Test", "<p>Test email from Sentinel Pulse</p>")
                success = result
                if not result:
                    error = "Email sending failed"
        else:
            error = f"Unknown channel: {channel}"
    except Exception as e:
        error = str(e)
        logger = logging.getLogger("SentinelPulse")
        logger.error(f"Test notification error: {e}")

    if success:
        await audit_service.log_event("TEST_NOTIFICATION_SENT", success=True, channel=channel)
        return {"ok": True, "message": f"Test notification sent to {channel}"}
    else:
        await audit_service.log_event("TEST_NOTIFICATION_FAILED", success=False, channel=channel, error=error)
        return {"ok": False, "error": error}


@router.post("/notifications/webhooks/add")
async def add_webhook_url(url: str = Query(...)):
    """Add a custom webhook URL."""
    if url in notification_service.config.webhook_urls:
        return {"ok": False, "error": "URL already exists"}

    notification_service.config.webhook_urls.append(url)
    if not notification_service.config.webhook_enabled:
        notification_service.config.webhook_enabled = True

    await notification_service.save_config()
    await audit_service.log_setting_change(
        "notification_webhook_added",
        {},
        {"url": url},
    )

    return {"ok": True, "message": "Webhook URL added", "urls": notification_service.config.webhook_urls}


@router.post("/notifications/webhooks/remove")
async def remove_webhook_url(url: str = Query(...)):
    """Remove a custom webhook URL."""
    if url not in notification_service.config.webhook_urls:
        return {"ok": False, "error": "URL not found"}

    notification_service.config.webhook_urls.remove(url)
    await notification_service.save_config()
    await audit_service.log_setting_change(
        "notification_webhook_removed",
        {},
        {"url": url},
    )

    return {"ok": True, "message": "Webhook URL removed", "urls": notification_service.config.webhook_urls}