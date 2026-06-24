import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


class ChromeDiscordBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.old_event_dir = os.environ.get("BOT_EVENT_BUS_DIR")
        os.environ["BOT_EVENT_BUS_DIR"] = self.tmpdir.name

    def tearDown(self):
        if self.old_event_dir is None:
            os.environ.pop("BOT_EVENT_BUS_DIR", None)
        else:
            os.environ["BOT_EVENT_BUS_DIR"] = self.old_event_dir
        self.tmpdir.cleanup()

    def test_bridge_message_publishes_signal_observed(self):
        from routes.chrome_bridge import router
        from bot_event_bus import EventBusStore

        app = FastAPI()
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        response = client.post(
            "/api/discord/chrome-bridge/message",
            json={
                "event_id": "pulse-chrome-1",
                "channel_id": "123",
                "channel_name": "mike-alerts",
                "channel_url": "https://discord.com/channels/1/123",
                "bridge_target_id": "sentinel-pulse",
                "bridge_target_name": "Sentinel Pulse",
                "author_name": "MikeInvesting [MIKE]",
                "content": "$SPY\n$744 PUTS\nEXPIRATION 6/22/2026\n$.4 Entry\n@everyone alert",
                "observed_at": "2026-06-22T14:23:00+00:00",
            },
        )
        events = EventBusStore().list_events(limit=10)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "accepted")
        self.assertEqual(events[0]["event_type"], "signal.observed")
        self.assertEqual(events[0]["source"], "chrome-discord-bridge")
        self.assertEqual(events[0]["target"], "sentinel-pulse")
        self.assertEqual(events[0]["payload"]["contract_version"], "chrome.discord.message.v1")
        self.assertEqual(events[0]["payload"]["bridge_target_id"], "sentinel-pulse")
        self.assertIn("$SPY", events[0]["payload"]["raw_text"])

    def test_bridge_heartbeat_publishes_health(self):
        from routes.chrome_bridge import router, get_bridge_health
        from bot_event_bus import EventBusStore

        app = FastAPI()
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        response = client.post(
            "/api/discord/chrome-bridge/heartbeat",
            json={
                "status": "ok",
                "bridge_enabled": True,
                "channel_id": "123",
                "channel_name": "mike-alerts",
                "channel_url": "https://discord.com/channels/1/123",
                "bridge_target_id": "sentinel-pulse",
                "observed_at": "2026-06-22T14:23:30+00:00",
            },
        )
        health = get_bridge_health()
        events = EventBusStore().list_events(limit=10)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "healthy")
        self.assertTrue(health["healthy"])
        self.assertEqual(events[0]["event_type"], "bridge.health")
        self.assertEqual(events[0]["payload"]["bridge_target_id"], "sentinel-pulse")

    def test_remote_bridge_requires_configured_secret(self):
        from routes import chrome_bridge

        app = FastAPI()
        app.include_router(chrome_bridge.router, prefix="/api")
        client = TestClient(app)

        with (
            patch.dict(
                os.environ,
                {"CHROME_BRIDGE_ALLOW_REMOTE": "1", "CHROME_BRIDGE_REMOTE_SECRET": ""},
                clear=False,
            ),
            patch.object(chrome_bridge, "LOCAL_CLIENT_HOSTS", set()),
        ):
            response = client.post(
                "/api/discord/chrome-bridge/message",
                json={"event_id": "remote-1", "content": "$SPY alert"},
            )

        self.assertEqual(503, response.status_code)
        self.assertEqual("Chrome bridge remote secret is not configured", response.json()["detail"])

    def test_remote_bridge_rejects_missing_secret_header(self):
        from routes import chrome_bridge

        app = FastAPI()
        app.include_router(chrome_bridge.router, prefix="/api")
        client = TestClient(app)

        with (
            patch.dict(
                os.environ,
                {
                    "CHROME_BRIDGE_ALLOW_REMOTE": "1",
                    "CHROME_BRIDGE_REMOTE_SECRET": "remote-test-secret",
                },
                clear=False,
            ),
            patch.object(chrome_bridge, "LOCAL_CLIENT_HOSTS", set()),
        ):
            response = client.post(
                "/api/discord/chrome-bridge/message",
                json={"event_id": "remote-2", "content": "$SPY alert"},
            )

        self.assertEqual(401, response.status_code)
        self.assertEqual("Invalid chrome bridge secret", response.json()["detail"])

    def test_remote_bridge_accepts_matching_secret_header(self):
        from routes import chrome_bridge
        from bot_event_bus import EventBusStore

        app = FastAPI()
        app.include_router(chrome_bridge.router, prefix="/api")
        client = TestClient(app)

        with (
            patch.dict(
                os.environ,
                {
                    "CHROME_BRIDGE_ALLOW_REMOTE": "1",
                    "CHROME_BRIDGE_REMOTE_SECRET": "remote-test-secret",
                },
                clear=False,
            ),
            patch.object(chrome_bridge, "LOCAL_CLIENT_HOSTS", set()),
        ):
            response = client.post(
                "/api/discord/chrome-bridge/message",
                headers={"X-Chrome-Bridge-Secret": "remote-test-secret"},
                json={"event_id": "remote-3", "content": "$SPY alert"},
            )

        events = EventBusStore().list_events(limit=10)
        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual("accepted", response.json()["status"])
        self.assertEqual("signal.observed", events[0]["event_type"])


if __name__ == "__main__":
    unittest.main()
