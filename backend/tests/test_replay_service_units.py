import unittest
from datetime import datetime, timezone
import asyncio

from backend.replay_service import build_replay_bar, build_session_id, get_active_replay_price, normalize_alpaca_bars


class FakeSettingsCollection:
    def __init__(self, value):
        self.value = value
        self.update = None

    async def find_one(self, query, projection=None):
        return {"key": "active_replay", "value": self.value}

    async def update_one(self, query, update, upsert=False):
        self.update = update
        self.value = update["$set"]["value"]


class FakeReplayDb:
    def __init__(self, replay_state):
        self.settings = FakeSettingsCollection(replay_state)


class ReplayServiceUnitTest(unittest.TestCase):
    def test_build_session_id_is_stable_for_same_import(self):
        first = build_session_id("yfinance", ["TSLA", "SPY"], "2026-06-09", "1m")
        second = build_session_id("yfinance", ["spy", "tsla"], "2026-06-09", "1m")

        self.assertEqual(first, second)
        self.assertTrue(first.startswith("yfinance-2026-06-09-1m-"))

    def test_build_replay_bar_normalizes_provider_fields(self):
        bar = build_replay_bar(
            session_id="session-1",
            source="alpaca",
            symbol="tsla",
            timestamp="2026-06-09T13:30:00Z",
            open_price=100,
            high=101.25,
            low=99.5,
            close=100.75,
            volume=12345,
            vwap=100.4,
            trade_count=50,
        )

        self.assertEqual(bar["session_id"], "session-1")
        self.assertEqual(bar["source"], "alpaca")
        self.assertEqual(bar["symbol"], "TSLA")
        self.assertEqual(bar["timestamp"], "2026-06-09T13:30:00+00:00")
        self.assertEqual(bar["open"], 100.0)
        self.assertEqual(bar["close"], 100.75)
        self.assertEqual(bar["volume"], 12345.0)
        self.assertEqual(bar["vwap"], 100.4)
        self.assertEqual(bar["trade_count"], 50)

    def test_normalize_alpaca_bars_reads_symbol_grouped_response(self):
        payload = {
            "bars": {
                "SPY": [
                    {"t": "2026-06-09T13:30:00Z", "o": 535.0, "h": 536.0, "l": 534.5, "c": 535.5, "v": 1000, "vw": 535.4, "n": 12}
                ]
            }
        }

        bars = normalize_alpaca_bars("session-2", payload)

        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0]["symbol"], "SPY")
        self.assertEqual(bars[0]["close"], 535.5)
        self.assertEqual(bars[0]["source"], "alpaca")

    def test_non_looping_replay_expires_instead_of_reusing_final_price(self):
        replay_state = {
            "active": True,
            "session_id": "session-expired",
            "symbols": ["QQQ"],
            "speed": 5.0,
            "loop": False,
            "started_at": "2026-06-12T00:00:00+00:00",
            "first_timestamp": "2026-06-11T13:30:00+00:00",
            "last_timestamp": "2026-06-11T13:31:00+00:00",
            "duration_seconds": 60.0,
        }
        db = FakeReplayDb(replay_state)

        result = asyncio.run(get_active_replay_price(
            db,
            "QQQ",
            now=datetime(2026, 6, 12, 0, 1, 1, tzinfo=timezone.utc),
        ))

        self.assertIsNone(result)
        self.assertFalse(db.settings.value["active"])
        self.assertTrue(db.settings.value["completed"])
        self.assertEqual(db.settings.value["completed_reason"], "replay_finished")


if __name__ == "__main__":
    unittest.main()
