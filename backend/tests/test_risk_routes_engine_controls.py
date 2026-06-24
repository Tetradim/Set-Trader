import asyncio
import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

password_security = types.ModuleType("password_security")
password_security.hash_password = lambda password: password
password_security.verify_password = lambda password, hashed: password == hashed
sys.modules.setdefault("password_security", password_security)

import deps  # noqa: E402
from risk_controls import RiskControls  # noqa: E402
from routes import risk as risk_routes  # noqa: E402


class _User:
    username = "test-admin"


class _Engine:
    def __init__(self):
        self.risk_controls = RiskControls()


def _admin_user():
    return _User()


def test_kill_switch_routes_target_running_engine_controls(monkeypatch):
    engine = _Engine()
    monkeypatch.setattr(deps, "engine", engine)

    create_request = risk_routes.KillSwitchRequest(
        level="global",
        target_id="global",
        reason="panic stop",
    )
    create_result = asyncio.run(
        risk_routes.create_kill_switch(create_request, current_user=_admin_user())
    )

    assert create_result["switch_id"] == "global:global"
    assert engine.risk_controls.get_kill_switch("global", "global") is not None

    toggle_result = asyncio.run(
        risk_routes.toggle_kill_switch(
            "global:global",
            create_request,
            current_user=_admin_user(),
        )
    )

    kill_switch = engine.risk_controls.get_kill_switch("global", "global")
    assert toggle_result["is_active"] is True
    assert kill_switch.is_active is True
    assert kill_switch.reason == "panic stop"

    status_result = asyncio.run(
        risk_routes.get_risk_status(current_user=_admin_user())
    )

    assert status_result["trading_allowed"] is False
    assert status_result["restriction"] == "hard_block"
    assert "Global kill switch active" in status_result["message"]


def test_toggle_kill_switch_rejects_unknown_switch(monkeypatch):
    engine = _Engine()
    monkeypatch.setattr(deps, "engine", engine)

    request = risk_routes.KillSwitchRequest(
        level="global",
        target_id="global",
        reason="panic stop",
    )

    with pytest.raises(risk_routes.HTTPException) as exc:
        asyncio.run(
            risk_routes.toggle_kill_switch(
                "global:global",
                request,
                current_user=_admin_user(),
            )
        )

    assert exc.value.status_code == 404
    assert "not found" in exc.value.detail.lower()
    assert engine.risk_controls.get_kill_switch("global", "global") is None


def test_deactivate_kill_switch_rejects_unknown_switch(monkeypatch):
    engine = _Engine()
    monkeypatch.setattr(deps, "engine", engine)

    with pytest.raises(risk_routes.HTTPException) as exc:
        asyncio.run(
            risk_routes.deactivate_kill_switch(
                "global:global",
                current_user=_admin_user(),
            )
        )

    assert exc.value.status_code == 404
    assert "not found" in exc.value.detail.lower()
    assert engine.risk_controls.get_kill_switch("global", "global") is None
