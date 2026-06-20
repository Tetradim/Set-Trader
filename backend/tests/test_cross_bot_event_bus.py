import sys
import os
import unittest
from pathlib import Path
from unittest.mock import patch


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


class _Engine:
    def __init__(self):
        self._positions = {}
        self.paused = False


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
        publish_event("edge.action", {"action": "observe"}, target="darkpool-mon", store=store)

        events = store.list_events(limit=10, target="sentinel-pulse")

        self.assertEqual(1, len(events))
        self.assertEqual("bot-event.v1", events[0]["schema_version"])
        self.assertEqual("sentinel-pulse", events[0]["target"])

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
