import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]


class BotControlsStaticTest(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_stop_clears_pending_sells_and_disables_tickers(self):
        text = self.read("backend/routes/bot.py")

        self.assertIn("class BotControlRequest", text)
        self.assertIn("deps.engine._pending_sells.clear()", text)
        self.assertIn('{"$set": {"enabled": False}}', text)
        self.assertIn('"tickers": tickers', text)

    def test_start_all_enables_tickers(self):
        text = self.read("backend/routes/bot.py")

        self.assertIn('"$set": {"enabled": True, "auto_stopped": False, "auto_stop_reason": ""}', text)
        self.assertIn("enable_all=%s", text)

    def test_stopped_engine_does_not_process_pending_sells(self):
        text = self.read("backend/server.py")

        self.assertIn("if deps.engine.running and deps.engine._pending_sells:", text)
        self.assertIn("a full stop must stop all bot activity", text)

    def test_bot_snapshot_endpoint_exposes_live_watchlist_state(self):
        text = self.read("backend/routes/bot.py")

        self.assertIn('@router.get("/bot/snapshot")', text)
        self.assertIn("async def get_bot_snapshot", text)
        self.assertIn('"prices": snapshot["prices"]', text)
        self.assertIn('"price_sources": snapshot["price_sources"]', text)
        self.assertIn('"tickers": snapshot["tickers"]', text)
        self.assertIn('"simulate_24_7": deps.engine.simulate_24_7', text)
        self.assertIn('"replay": snapshot["replay"]', text)

    def test_price_broadcast_keeps_working_when_one_symbol_fails(self):
        snapshot = self.read("backend/bot_snapshot.py")
        server = self.read("backend/server.py")

        self.assertIn("async def build_bot_snapshot", snapshot)
        self.assertIn("price_errors", snapshot)
        self.assertIn("Price lookup failed for", snapshot)
        self.assertIn("from bot_snapshot import build_bot_snapshot", server)
        self.assertIn('update["type"] = "PRICE_UPDATE"', server)


if __name__ == "__main__":
    unittest.main()
