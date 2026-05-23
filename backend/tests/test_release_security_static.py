"""Static checks for public-beta release safety.

These checks avoid importing the full app so they can run without MongoDB or
broker SDK dependencies. They verify that high-risk routes are not exposed
without authentication and that demo/debug release flags stay out of packaged
configuration.
"""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"


class ReleaseSecurityStaticTest(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_server_mounts_high_risk_routers_with_auth_dependencies(self):
        text = self.read("backend/server.py")

        protected_mounts = [
            "brokers_router",
            "tickers_router",
            "trades_router",
            "bot_router",
            "system_router",
            "markets_router",
            "strategies_router",
            "risk_router",
            "orders_router",
            "reconciliation_router",
            "audit_router",
            "ops_router",
            "analytics_router",
            "slo_router",
            "notifications_router",
            "portfolio_router",
        ]
        for router_name in protected_mounts:
            self.assertRegex(
                text,
                rf"api\.include_router\({router_name},\s*dependencies=\[[^\]]+\]\)",
                f"{router_name} must be mounted with an auth dependency",
            )

    def test_websocket_requires_token(self):
        text = self.read("backend/routes/ws.py")

        self.assertIn("verify_token", text)
        self.assertIn("token: Optional[str]", text)
        self.assertIn("WS_1008_POLICY_VIOLATION", text)

    def test_edge_and_alert_webhooks_require_shared_secret(self):
        edge = self.read("backend/routes/edge.py")
        alerts = self.read("backend/alert_handler.py")

        self.assertIn("Depends(validate_api_key)", edge)
        self.assertRegex(edge, r"expected\s*=\s*await\s+deps\.db\.settings\.find_one")
        self.assertIn("ALERT_WEBHOOK_SECRET", alerts)
        self.assertIn("X-Webhook-Secret", alerts)

    def test_release_configs_do_not_enable_demo_or_debug_defaults(self):
        for relative_path in [
            "backend/.env.example",
            ".github/workflows/build.yml",
        ]:
            text = self.read(relative_path)
            self.assertNotIn("DEMO_MODE", text)
            self.assertNotRegex(text, r"LOG_LEVEL\s*=\s*DEBUG")

    def test_frontend_api_and_websocket_send_bearer_token(self):
        api = self.read("frontend/src/lib/api.ts")
        ws = self.read("frontend/src/hooks/useWebSocket.ts")

        self.assertIn("getAuthToken", api)
        self.assertIn("Authorization", api)
        self.assertIn("getAuthToken", ws)
        self.assertIn("searchParams.set('token'", ws)


if __name__ == "__main__":
    unittest.main()
