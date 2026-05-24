"""Authenticated runtime and browser log endpoints."""
import json
import os
import sys
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

import deps


router = APIRouter(prefix="/logs", tags=["Logs"])
logger = deps.logger


def get_runtime_log_path() -> Path:
    """Return the active runtime log path used by launcher/backend logging."""
    configured = os.getenv("LOG_FILE")
    if configured:
        return Path(configured)
    if getattr(sys, "frozen", False):
        return Path.home() / "Desktop" / "Sentinel-Pulse.log"
    return Path("logs") / "sentinel_pulse.log"


@router.get("/stream")
async def stream_logs():
    """Stream logs in real time via SSE."""
    import asyncio

    log_path = get_runtime_log_path()
    if not log_path.exists():
        return {"error": "Log file not found"}

    async def generate():
        with open(log_path, "r", encoding="utf-8") as f:
            f.seek(0, 2)
            while True:
                line = f.readline()
                if line:
                    yield f"data: {line}\n\n"
                else:
                    await asyncio.sleep(0.25)

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/recent")
async def recent_logs(lines: int = 200, level: str = "DEBUG"):
    """Get recent log entries."""
    log_path = get_runtime_log_path()
    if not log_path.exists():
        return {"logs": []}

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            all_lines = f.readlines()[-lines:]
        parsed = []
        for line in all_lines:
            try:
                entry = json.loads(line)
                if level == "DEBUG" or entry.get("level") == level:
                    parsed.append(entry)
            except json.JSONDecodeError:
                pass
        return {"logs": parsed}
    except FileNotFoundError:
        return {"logs": []}


SENSITIVE_CLIENT_LOG_KEYS = {
    "authorization",
    "api_key",
    "apikey",
    "bearer",
    "bot_token",
    "chat_id",
    "credential",
    "password",
    "secret",
    "token",
}


def sanitize_client_log_payload(value, depth: int = 0):
    """Remove secrets and cap payload size before writing browser logs."""
    if depth > 4:
        return "[max-depth]"
    if isinstance(value, dict):
        clean = {}
        for key, item in list(value.items())[:80]:
            key_text = str(key)
            lowered = key_text.lower()
            if any(sensitive in lowered for sensitive in SENSITIVE_CLIENT_LOG_KEYS):
                clean[key_text] = "[redacted]"
            else:
                clean[key_text] = sanitize_client_log_payload(item, depth + 1)
        return clean
    if isinstance(value, list):
        return [sanitize_client_log_payload(item, depth + 1) for item in value[:50]]
    if isinstance(value, str):
        return value[:1000]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:1000]


@router.post("/client-error")
async def log_client_error(request: Request):
    """Receive frontend errors."""
    body = await request.json()
    event = sanitize_client_log_payload(body)
    logger.error("Frontend event error: %s", event.get("message"), extra={"extra_fields": event})
    return {"ok": True}


@router.post("/client-events")
async def log_client_events(request: Request):
    """Receive batched browser UI, API, WebSocket, and error events."""
    try:
        body = await request.json()
    except Exception as exc:
        logger.warning("Frontend event parse failure: %s", exc)
        return {"ok": False, "error": "invalid_json"}

    raw_events = body.get("events", [body]) if isinstance(body, dict) else []
    if not isinstance(raw_events, list):
        raw_events = [raw_events]

    logged = 0
    for raw_event in raw_events[:50]:
        event = sanitize_client_log_payload(raw_event)
        event_type = event.get("type", "ui.event") if isinstance(event, dict) else "ui.event"
        level = event.get("level", "info") if isinstance(event, dict) else "info"
        message = event.get("message", event_type) if isinstance(event, dict) else event_type
        extra = {"extra_fields": {"client_event": event}}
        if level == "error":
            logger.error("Frontend event %s: %s", event_type, message, extra=extra)
        elif level == "warn":
            logger.warning("Frontend event %s: %s", event_type, message, extra=extra)
        else:
            logger.info("Frontend event %s: %s", event_type, message, extra=extra)
        logged += 1

    return {"ok": True, "logged": logged}
