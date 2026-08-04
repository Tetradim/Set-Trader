import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from routes import settings as settings_routes  # noqa: E402
from schemas import SettingsUpdate  # noqa: E402


class _InsertResult:
    inserted_id = "audit-id"


class _AuditCollection:
    def __init__(self):
        self.docs = []

    async def insert_one(self, doc):
        self.docs.append(doc)
        return _InsertResult()


class _Db:
    def __init__(self):
        self.audit_logs = _AuditCollection()

    def __getitem__(self, name):
        if name == "audit_logs":
            return self.audit_logs
        raise KeyError(name)


class _Engine:
    def __init__(self):
        self.simulate_24_7 = False
        self.market_hours_only = True
        self.live_during_market_hours = True
        self.paper_after_hours = False
        self._dry_run_mode = False
        self.saved = 0

    def is_dry_run(self):
        return self._dry_run_mode

    def is_paper_trading(self):
        return False

    def get_trading_mode(self):
        return "live"

    async def save_state(self):
        self.saved += 1


class _TelegramService:
    running = False


class _Logger:
    def info(self, *_args, **_kwargs):
        pass


def _patch_deps(monkeypatch, engine):
    db = _Db()
    monkeypatch.setattr(settings_routes.deps, "engine", engine)
    monkeypatch.setattr(settings_routes.deps, "db", db)
    monkeypatch.setattr(settings_routes.deps, "logger", _Logger())
    monkeypatch.setattr(settings_routes.deps, "telegram_service", _TelegramService())
    return db


def test_settings_rejects_simulate_24_7_enable(monkeypatch):
    engine = _Engine()
    db = _patch_deps(monkeypatch, engine)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            settings_routes.update_settings(
                SettingsUpdate(simulate_24_7=True)
            )
        )

    assert exc.value.status_code == 400
    assert exc.value.detail["error"] == "local_paper_execution_removed"
    assert engine.simulate_24_7 is False
    assert engine.live_during_market_hours is True
    assert engine.saved == 0
    assert db.audit_logs.docs == []


def test_settings_rejects_paper_after_hours_enable(monkeypatch):
    engine = _Engine()
    db = _patch_deps(monkeypatch, engine)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(settings_routes.update_settings(SettingsUpdate(paper_after_hours=True)))

    assert exc.value.status_code == 400
    assert exc.value.detail["error"] == "local_paper_execution_removed"
    assert engine.paper_after_hours is False
    assert engine.saved == 0
    assert db.audit_logs.docs == []


def test_settings_rejects_disabling_live_broker_execution(monkeypatch):
    engine = _Engine()
    db = _patch_deps(monkeypatch, engine)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(settings_routes.update_settings(SettingsUpdate(live_during_market_hours=False)))

    assert exc.value.status_code == 400
    assert exc.value.detail["error"] == "local_paper_execution_removed"
    assert engine.live_during_market_hours is True
    assert engine.saved == 0
    assert db.audit_logs.docs == []


def test_settings_normalizes_allowed_mode_update_to_live_broker_execution(monkeypatch):
    engine = _Engine()
    engine.simulate_24_7 = True
    engine.live_during_market_hours = False
    engine.paper_after_hours = True
    db = _patch_deps(monkeypatch, engine)

    result = asyncio.run(
        settings_routes.update_settings(
            SettingsUpdate(
                simulate_24_7=False,
                live_during_market_hours=True,
                paper_after_hours=False,
            )
        )
    )

    assert result["ok"] is True
    assert engine.simulate_24_7 is False
    assert engine.live_during_market_hours is True
    assert engine.paper_after_hours is False
    assert engine.get_trading_mode() == "live"
    assert engine.saved == 1
    assert len(db.audit_logs.docs) == 1
    audit = db.audit_logs.docs[0]
    assert audit["event_type"] == "SETTING_CHANGED"
    assert audit["success"] is True
    assert audit["error_message"] is None
    assert audit["details"]["setting"] == "trading_mode"
    assert audit["details"]["old_value"] == "live"
    assert audit["details"]["new_value"] == "live"


def test_settings_live_mode_update_no_longer_requires_operator_secret(monkeypatch):
    engine = _Engine()
    monkeypatch.delenv("SENTINEL_PULSE_LIVE_TRADING_OPERATOR_SECRET", raising=False)
    db = _patch_deps(monkeypatch, engine)

    result = asyncio.run(
        settings_routes.update_settings(
            SettingsUpdate(simulate_24_7=False, live_during_market_hours=True)
        )
    )

    assert result["ok"] is True
    assert engine.simulate_24_7 is False
    assert engine.live_during_market_hours is True
    assert engine.saved == 1
    assert len(db.audit_logs.docs) == 1


def test_settings_paper_mode_update_is_removed(monkeypatch):
    engine = _Engine()
    db = _patch_deps(monkeypatch, engine)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(settings_routes.update_settings(SettingsUpdate(simulate_24_7=True)))

    assert exc.value.status_code == 400
    assert exc.value.detail["error"] == "local_paper_execution_removed"
    assert engine.saved == 0
    assert db.audit_logs.docs == []
