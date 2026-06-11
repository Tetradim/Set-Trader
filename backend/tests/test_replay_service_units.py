import unittest

from backend.replay_service import build_replay_bar, build_session_id, normalize_alpaca_bars


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


if __name__ == "__main__":
    unittest.main()
