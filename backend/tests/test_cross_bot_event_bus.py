import sys
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from bot_event_bus import EventBusStore, publish_event  # noqa: E402
from routes import bot_bus  # noqa: E402


class _UpdateResult:
    matched_count = 1


class _TickerCollection:
    def __init__(self):
        self.docs = {"AAPL": {"symbol": "AAPL", "enabled": True}}
        self.updates = []

    async def find_one(self, query=None, projection=None, **kwargs):
        return self.docs.get((query or {}).get("symbol"))

    async def update_one(self, query, update):
        self.updates.append((query, update))
        self.docs.setdefault(query.get("symbol"), {"symbol": query.get("symbol")}).update(update.get("$set", {}))
        return _UpdateResult()

    async def update_many(self, query, update):
        self.updates.append((query, update))
        for doc in self.docs.values():
            doc.update(update.get("$set", {}))
        return _UpdateResult()


class _Db:
    def __init__(self):
        self.tickers = _TickerCollection()
        self.settings = _SettingsCollection()


class _SettingsCollection:
    def __init__(self, edge_api_key: str = "test-edge-key"):
        self.edge_api_key = edge_api_key

    async def find_one(self, query=None, projection=None, **kwargs):
        if (query or {}).get("key") == "edge_api_key":
            return {"key": "edge_api_key", "value": self.edge_api_key}
        return None


class _Engine:
    def __init__(self):
        self._positions = {}
        self.paused = False
        self.buy_calls = []
        self.sell_calls = []

    async def execute_buy(self, symbol, price):
        self.buy_calls.append((symbol, price))

    async def execute_sell(self, symbol, price):
        self.sell_calls.append((symbol, price))


class CrossBotEventBusTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        import tempfile

        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmpdir.name)
        self.previous_bus_dir = os.environ.get("BOT_EVENT_BUS_DIR")
        os.environ["BOT_EVENT_BUS_DIR"] = str(self.tmp_path)

    def tearDown(self):
        if self.previous_bus_dir is None:
            os.environ.pop("BOT_EVENT_BUS_DIR", None)
        else:
            os.environ["BOT_EVENT_BUS_DIR"] = self.previous_bus_dir
        self.tmpdir.cleanup()

    def test_event_store_publishes_and_filters_for_pulse(self):
        store = EventBusStore(self.tmp_path)
        publish_event("edge.action", {"action": "stop_buying"}, target="sentinel-pulse", store=store)
        publish_event("edge.action", {"action": "observe"}, target="sentinel-flare", store=store)

        events = store.list_events(limit=10, target="sentinel-pulse")

        self.assertEqual(1, len(events))
        self.assertEqual("bot-event.v1", events[0]["schema_version"])
        self.assertEqual("sentinel-pulse", events[0]["target"])

    def test_edge_action_http_endpoint_requires_edge_api_key(self):
        db = _Db()
        app = FastAPI()
        app.include_router(bot_bus.router, prefix="/api")

        with patch.object(bot_bus.post_handoff.__globals__["deps"], "db", db):
            response = TestClient(app).post(
                "/api/bus/edge-actions",
                json={"payload": {"symbol": "AAPL", "action": "stop_buying"}},
            )

        self.assertEqual(401, response.status_code)
        self.assertEqual("Invalid API key", response.json()["detail"])

    def test_event_list_http_endpoint_requires_edge_api_key(self):
        db = _Db()
        app = FastAPI()
        app.include_router(bot_bus.router, prefix="/api")

        with patch.object(bot_bus.post_handoff.__globals__["deps"], "db", db):
            response = TestClient(app).get("/api/bus/events")

        self.assertEqual(401, response.status_code)
        self.assertEqual("Invalid API key", response.json()["detail"])

    def test_event_publish_http_endpoint_requires_edge_api_key(self):
        db = _Db()
        app = FastAPI()
        app.include_router(bot_bus.router, prefix="/api")

        with patch.object(bot_bus.post_handoff.__globals__["deps"], "db", db):
            response = TestClient(app).post(
                "/api/bus/events",
                json={"event_type": "edge.action", "payload": {"symbol": "AAPL"}},
            )

        self.assertEqual(401, response.status_code)
        self.assertEqual("Invalid API key", response.json()["detail"])

    def test_event_bus_http_endpoints_accept_configured_edge_api_key(self):
        db = _Db()
        app = FastAPI()
        app.include_router(bot_bus.router, prefix="/api")
        client = TestClient(app)

        with patch.object(bot_bus.post_handoff.__globals__["deps"], "db", db):
            publish_response = client.post(
                "/api/bus/events",
                headers={"X-API-Key": "test-edge-key"},
                json={
                    "event_type": "edge.signal.observed",
                    "payload": {"symbol": "AAPL"},
                    "source": "sentinel-edge",
                    "target": "sentinel-pulse",
                },
            )
            list_response = client.get(
                "/api/bus/events",
                headers={"Authorization": "Bearer test-edge-key"},
            )

        self.assertEqual(200, publish_response.status_code)
        self.assertEqual("edge.signal.observed", publish_response.json()["event"]["event_type"])
        self.assertEqual(200, list_response.status_code)
        self.assertEqual(1, list_response.json()["count"])

    async def test_downtrend_warning_maps_to_stop_buying(self):
        db = _Db()
        engine = _Engine()

        with (
            patch.object(bot_bus.post_handoff.__globals__["deps"], "db", db),
            patch.object(bot_bus.post_handoff.__globals__["deps"], "engine", engine),
        ):
            response = await bot_bus.apply_edge_action(
                bot_bus.EdgeActionRequest(
                    payload={
                        "symbol": "AAPL",
                        "action": "downtrend_warning",
                        "reason": "Edge detected market weakness",
                    }
                )
            )

        self.assertTrue(response["response"]["accepted"])
        self.assertEqual("stop_buying", response["response"]["action"])
        self.assertFalse(db.tickers.docs["AAPL"]["enabled"])
        self.assertEqual("Edge detected market weakness", db.tickers.docs["AAPL"]["auto_stop_reason"])
        events = EventBusStore(self.tmp_path).list_events(limit=10)
        self.assertEqual(["edge.action.applied", "edge.action.received"], [event["event_type"] for event in events])

    async def test_edge_action_rejects_simulation_mode_before_execution(self):
        db = _Db()
        engine = _Engine()

        with (
            patch.object(bot_bus.post_handoff.__globals__["deps"], "db", db),
            patch.object(bot_bus.post_handoff.__globals__["deps"], "engine", engine),
        ):
            response = await bot_bus.apply_edge_action(
                bot_bus.EdgeActionRequest(
                    payload={
                        "symbol": "AAPL",
                        "action": "buy",
                        "mode": "simulation",
                        "metadata": {"price": 123.45},
                    }
                )
            )

        self.assertFalse(response["response"]["accepted"])
        self.assertEqual("rejected", response["response"]["status"])
        self.assertEqual("unsupported_mode", response["response"]["reason"])
        self.assertEqual([], engine.buy_calls)
        self.assertEqual([], engine.sell_calls)
        events = EventBusStore(self.tmp_path).list_events(limit=10)
        self.assertEqual(["edge.action.rejected", "edge.action.received"], [event["event_type"] for event in events])
