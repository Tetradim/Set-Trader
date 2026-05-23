"""Static checks for beta preflight readiness features."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class PreflightStaticTest(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_backend_exposes_release_preflight_endpoint(self):
        text = self.read("backend/routes/system.py")

        self.assertIn('@router.get("/preflight")', text)
        self.assertIn("account_balance", text)
        self.assertIn("edge_api_key", text)
        self.assertIn("ALERT_WEBHOOK_SECRET", text)
        self.assertIn("global_daily_drawdown", text)
        self.assertIn("ready_to_trade", text)

    def test_global_daily_drawdown_is_persisted(self):
        schemas = self.read("backend/schemas.py")
        bot = self.read("backend/routes/bot.py")
        engine = self.read("backend/trading_engine.py")

        self.assertIn("class GlobalDailyDrawdownConfig", schemas)
        self.assertIn("global_daily_drawdown: Optional[GlobalDailyDrawdownConfig]", schemas)
        self.assertIn('{"key": "global_daily_drawdown"}', bot)
        self.assertIn("_check_global_daily_drawdown", engine)
        self.assertIn("GLOBAL_DAILY_DRAWDOWN", engine)

    def test_edge_retry_attempt_setting_is_persisted(self):
        schemas = self.read("backend/schemas.py")
        bot = self.read("backend/routes/bot.py")
        settings = self.read("frontend/src/components/tabs/SettingsTab.tsx")

        self.assertIn("edge_retry_max_attempts", schemas)
        self.assertIn('{"key": "edge_retry_max_attempts"}', bot)
        self.assertIn("set_max_retry_attempts", bot)
        self.assertIn("edgeRetryAttemptsText", settings)
        self.assertIn("edge_retry_max_attempts", settings)

    def test_frontend_has_preflight_tab(self):
        tab_content = self.read("frontend/src/components/DashboardTabContent.tsx")
        tabs = self.read("frontend/src/lib/dashboard-tabs.ts")
        preflight = self.read("frontend/src/components/tabs/PreflightTab.tsx")

        self.assertIn("PreflightTab", tab_content)
        self.assertIn("case 'preflight'", tab_content)
        self.assertIn("'preflight'", tabs)
        self.assertIn("/api/preflight", preflight)
        self.assertIn("ready_to_trade", preflight)


if __name__ == "__main__":
    unittest.main()
