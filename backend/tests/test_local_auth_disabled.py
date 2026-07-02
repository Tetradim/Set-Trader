from datetime import datetime
from pathlib import Path
import asyncio
import sys


BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


class _Client:
    host = "127.0.0.1"


class _Request:
    client = _Client()


def test_auth_disabled_returns_local_admin_identity(monkeypatch):
    import auth

    monkeypatch.setenv("SENTINEL_PULSE_AUTH_DISABLED", "1")

    token = asyncio.run(auth.get_current_user(credentials=None, request=_Request()))

    assert token.sub == "local-desktop-admin"
    assert token.username == "local-admin"
    assert token.roles == ["admin", "risk_officer", "trader"]
    assert token.broker_access == ["*"]
    assert token.exp > datetime.utcnow()
