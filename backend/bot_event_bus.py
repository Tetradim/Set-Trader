"""Append-only Cross Bot Event Bus helpers for Sentinel Pulse."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EVENT_SCHEMA_VERSION = "bot-event.v1"
DEFAULT_SOURCE = "sentinel-pulse"


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_event_dir() -> Path:
    configured = os.getenv("BOT_EVENT_BUS_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parent / "data" / "event-bus"


@dataclass(frozen=True)
class BotEvent:
    event_type: str
    payload: dict[str, Any]
    source: str = DEFAULT_SOURCE
    target: str | None = None
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    schema_version: str = EVENT_SCHEMA_VERSION
    created_at: str = field(default_factory=_now_utc)

    def to_record(self) -> dict[str, Any]:
        return asdict(self)


class EventBusStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or default_event_dir()

    def _path_for(self, created_at: str | None = None) -> Path:
        day = (created_at or _now_utc())[:10]
        return self.root / f"{day}.jsonl"

    def publish(self, event: BotEvent) -> dict[str, Any]:
        self.root.mkdir(parents=True, exist_ok=True)
        record = event.to_record()
        path = self._path_for(record["created_at"])
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        return {**record, "path": str(path)}

    def list_events(self, limit: int = 100, target: str | None = None) -> list[dict[str, Any]]:
        if limit <= 0 or not self.root.exists():
            return []
        records: list[dict[str, Any]] = []
        for path in sorted(self.root.glob("*.jsonl"), reverse=True):
            for line in reversed(path.read_text(encoding="utf-8").splitlines()):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if target and record.get("target") not in {target, None}:
                    continue
                records.append(record)
                if len(records) >= limit:
                    return records
        return records


def publish_event(
    event_type: str,
    payload: dict[str, Any],
    *,
    source: str = DEFAULT_SOURCE,
    target: str | None = None,
    store: EventBusStore | None = None,
) -> dict[str, Any]:
    return (store or EventBusStore()).publish(
        BotEvent(event_type=event_type, payload=payload, source=source, target=target)
    )
