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


if __name__ == "__main__":
    unittest.main()
