import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import broker_manager as broker_manager_module  # noqa: E402
import brokers.registry as broker_registry  # noqa: E402
from broker_manager import BrokerConnectionManager  # noqa: E402
from brokers import BROKER_REGISTRY, get_broker_adapter  # noqa: E402
from brokers.base import BrokerInfo  # noqa: E402
from routes import brokers as broker_routes  # noqa: E402
from schemas import BrokerTestRequest  # noqa: E402


def _unsupported_info() -> BrokerInfo:
    return BrokerInfo(
        id="stale_broker",
        name="Stale Broker",
        description="Disabled until live trading certification is complete.",
        supported=False,
        readiness="unavailable",
        readiness_note="Disabled pending certification.",
        auth_fields=["token"],
    )


def test_broker_test_endpoint_rejects_unsupported_brokers(monkeypatch):
    monkeypatch.setattr(broker_routes, "get_broker_info", lambda _broker_id: _unsupported_info())

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            broker_routes.test_broker_connection(
                "stale_broker",
                BrokerTestRequest(credentials={"token": "long-enough-token"}),
            )
        )

    assert exc.value.status_code == 400
    assert exc.value.detail["error"] == "unsupported_broker"
    assert exc.value.detail["broker_id"] == "stale_broker"


def test_broker_connect_endpoint_rejects_unsupported_brokers_before_manager(monkeypatch):
    class _BrokerManager:
        called = False

        async def connect_broker(self, *_args, **_kwargs):
            self.called = True
            return True

    manager = _BrokerManager()
    monkeypatch.setattr(broker_routes, "get_broker_info", lambda _broker_id: _unsupported_info())
    monkeypatch.setattr(broker_routes.deps, "broker_mgr", manager)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            broker_routes.connect_broker(
                "stale_broker",
                BrokerTestRequest(credentials={"token": "long-enough-token"}),
            )
        )

    assert exc.value.status_code == 400
    assert exc.value.detail["error"] == "unsupported_broker"
    assert manager.called is False


def test_connection_manager_refuses_unsupported_registry_broker(monkeypatch):
    adapter_calls = []

    class _Db:
        pass

    class _Adapter:
        async def check_connection(self):
            return True

    def fake_adapter_factory(broker_id, credentials):
        adapter_calls.append((broker_id, credentials))
        return _Adapter()

    monkeypatch.setattr(broker_manager_module, "get_broker_info", lambda _broker_id: _unsupported_info())
    monkeypatch.setattr(broker_manager_module, "get_broker_adapter", fake_adapter_factory)

    manager = BrokerConnectionManager(_Db())
    result = asyncio.run(manager.connect_broker("stale_broker", {"token": "long-enough-token"}))

    assert result is False
    assert adapter_calls == []
    assert "certification is complete" in manager._failed["stale_broker"]


def test_legacy_schwab_aliases_are_unavailable_until_live_certified():
    for broker_id in ("td_ameritrade", "thinkorswim"):
        info = BROKER_REGISTRY[broker_id]

        assert info.supported is False
        assert info.readiness == "unavailable"
        assert "disabled" in info.readiness_note.lower()
        assert get_broker_adapter(broker_id, {}) is None


def test_experimental_brokers_are_disabled_without_operator_opt_in(monkeypatch):
    monkeypatch.delenv("SENTINEL_PULSE_ENABLE_EXPERIMENTAL_BROKERS", raising=False)
    broker_connection_enabled = getattr(broker_registry, "broker_connection_enabled", None)

    assert broker_connection_enabled is not None

    for broker_id in ("robinhood", "webull", "wealthsimple"):
        info = BROKER_REGISTRY[broker_id]

        assert info.supported is True
        assert info.readiness == "experimental"
        assert broker_connection_enabled(info) is False
        assert get_broker_adapter(broker_id, {}) is None


def test_experimental_brokers_require_explicit_truthy_operator_opt_in(monkeypatch):
    monkeypatch.setenv("SENTINEL_PULSE_ENABLE_EXPERIMENTAL_BROKERS", "true")
    broker_connection_enabled = getattr(broker_registry, "broker_connection_enabled", None)

    assert broker_connection_enabled is not None

    for broker_id in ("robinhood", "webull", "wealthsimple"):
        info = BROKER_REGISTRY[broker_id]

        assert broker_connection_enabled(info) is True
