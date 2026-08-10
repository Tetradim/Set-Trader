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
        self.assertIn("SENTINEL_PULSE_LIVE_TRADING_OPERATOR_SECRET", text)
        self.assertIn("global_daily_drawdown", text)
        self.assertIn("ready_to_trade", text)

    def test_edge_api_key_is_optional_until_edge_is_configured(self):
        text = self.read("backend/routes/system.py")

        self.assertIn("Edge REST integrations disabled", text)
        self.assertIn("Set edge_api_key only when connecting Sentinel Edge.", text)
        self.assertNotIn('"pass" if edge_api_key else "warn"', text)

    def test_global_daily_drawdown_is_persisted(self):
        schemas = self.read("backend/schemas.py")
        settings = self.read("backend/routes/settings.py")
        trade_accounting = self.read("backend/trading/trade_accounting.py")

        self.assertIn("class GlobalDailyDrawdownConfig", schemas)
        self.assertIn("global_daily_drawdown: Optional[GlobalDailyDrawdownConfig]", schemas)
        self.assertIn('{"key": "global_daily_drawdown"}', settings)
        self.assertIn("_check_global_daily_drawdown", trade_accounting)
        self.assertIn("GLOBAL_DAILY_DRAWDOWN", trade_accounting)

    def test_edge_retry_attempt_setting_is_persisted(self):
        schemas = self.read("backend/schemas.py")
        settings_route = self.read("backend/routes/settings.py")
        settings_tab = self.read("frontend/src/components/tabs/SettingsTab.tsx")

        self.assertIn("edge_retry_max_attempts", schemas)
        self.assertIn('{"key": "edge_retry_max_attempts"}', settings_route)
        self.assertIn("set_max_retry_attempts", settings_route)
        self.assertIn("edgeRetryAttemptsText", settings_tab)
        self.assertIn("edge_retry_max_attempts", settings_tab)

    def test_frontend_has_preflight_tab(self):
        tab_content = self.read("frontend/src/components/DashboardTabContent.tsx")
        tabs = self.read("frontend/src/lib/dashboard-tabs.ts")
        preflight = self.read("frontend/src/components/tabs/PreflightTab.tsx")

        self.assertIn("PreflightTab", tab_content)
        self.assertIn("case 'preflight'", tab_content)
        self.assertIn("'preflight'", tabs)
        self.assertIn("/api/preflight", preflight)
        self.assertIn("ready_to_trade", preflight)

    def test_live_trading_readiness_runbook_exists(self):
        runbook = self.read("docs/runbooks/live-trading-readiness.md")

        required_terms = [
            "ENABLE LIVE TRADING",
            "dry-run",
            "Simulate 24/7",
            "/api/preflight",
            "/api/audit-logs",
            "panic stop",
            "kill switch",
            "broker reconciliation",
            "SENTINEL_PULSE_LIVE_TRADING_OPERATOR_SECRET",
            "rollback",
            "Do not place live orders",
        ]
        for term in required_terms:
            self.assertIn(term, runbook)

    def test_ci_builds_installer_without_live_readiness_gate(self):
        workflow = self.read(".github/workflows/build.yml")

        required_terms = [
            "pull_request:",
            "runs-on: windows-latest",
            "Build Windows Installer",
            "cache-dependency-path: frontend/package-lock.json",
            "pip install -r backend/requirements.txt",
            "npm ci",
            "npm run build",
            "Minionguyjpro/Inno-Setup-Action",
            "Upload Installer",
        ]
        for term in required_terms:
            self.assertIn(term, workflow)

        self.assertRegex(workflow, r"(?m)^permissions:\n\s+contents:\s+read")
        self.assertNotIn("docs/runbooks/**", workflow)
        self.assertNotIn("readiness-checks", workflow)
        self.assertNotIn("Live Trading Readiness Checks", workflow)
        self.assertNotIn("Run backend readiness tests", workflow)
        self.assertNotIn("npm audit --audit-level=high", workflow)
        self.assertNotIn("npm run test:unit", workflow)
        self.assertNotRegex(workflow, r"(?s)\n  build:\n.*needs:\s+.*readiness")


if __name__ == "__main__":
    unittest.main()
