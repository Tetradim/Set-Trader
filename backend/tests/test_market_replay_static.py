import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]


class MarketReplayStaticTest(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_replay_service_owns_session_and_bar_collections(self):
        text = self.read("backend/replay_service.py")

        self.assertIn('REPLAY_SESSIONS_COLLECTION = "replay_sessions"', text)
        self.assertIn('REPLAY_BARS_COLLECTION = "replay_bars"', text)
        self.assertIn('ACTIVE_REPLAY_SETTING = "active_replay"', text)
        self.assertIn('"session_id"', text)
        self.assertIn('"symbol"', text)
        self.assertIn('"timestamp"', text)
        self.assertIn('"close"', text)
        self.assertIn('"source"', text)

    def test_yfinance_and_alpaca_imports_are_available(self):
        text = self.read("backend/routes/replay.py")

        self.assertIn('@router.post("/replay/import/yfinance")', text)
        self.assertIn('@router.post("/replay/import/alpaca")', text)
        self.assertIn('@router.post("/replay/sessions/{session_id}/start")', text)
        self.assertIn('@router.post("/replay/stop")', text)
        self.assertIn('@router.get("/replay/status")', text)
        self.assertIn("import_yfinance_session", text)
        self.assertIn("import_alpaca_session", text)

    def test_price_service_checks_active_replay_before_live_feeds(self):
        text = self.read("backend/price_service.py")

        self.assertIn("get_active_replay_price", text)
        self.assertIn('self._price_source[symbol] = f"replay:{replay_price', text)
        self.assertIn("math.isfinite(replay_value)", text)
        self.assertIn("Invalid replay price", text)

    def test_replay_import_and_playback_reject_non_finite_prices(self):
        text = self.read("backend/replay_service.py")

        self.assertIn("import math", text)
        self.assertIn("def _is_finite_positive", text)
        self.assertIn("if not _is_finite_positive(close):", text)
        self.assertIn("async def _find_valid_replay_bar", text)
        self.assertIn("if not _is_finite_positive(bar.get(\"close\")):", text)
        self.assertIn("return None", text)

    def test_snapshot_never_emits_non_finite_prices(self):
        text = self.read("backend/bot_snapshot.py")

        self.assertIn("import math", text)
        self.assertIn("math.isfinite(price)", text)
        self.assertIn("Non-finite price skipped", text)

    def test_replay_router_is_mounted_with_authenticated_api(self):
        text = self.read("backend/server.py")

        self.assertIn("from routes.replay import router as replay_router", text)
        self.assertIn("api.include_router(replay_router, dependencies=[Depends(get_current_user)])", text)

    def test_empty_replay_imports_are_not_selectable(self):
        service = self.read("backend/replay_service.py")
        router = self.read("backend/routes/replay.py")

        self.assertIn("raise ValueError(", service)
        self.assertIn("Replay import produced no bars", service)
        self.assertIn('"bar_count": {"$gt": 0}', router)
        self.assertIn("include_empty", router)


if __name__ == "__main__":
    unittest.main()
