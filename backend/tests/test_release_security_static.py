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
            "settings_router",
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
        self.assertIn("authenticate_websocket", text)
        self.assertIn("extract_websocket_token", text)
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
        self.assertIn("Backend is not reachable. Start Sentinel Pulse and try again.", api)
        self.assertIn("getAuthToken", ws)
        self.assertIn("searchParams.set('token'", ws)

    def test_server_allows_local_frontend_origins_by_default(self):
        server = self.read("backend/server.py")

        self.assertIn("DEFAULT_CORS_ORIGINS", server)
        for origin in [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:8002",
            "http://127.0.0.1:8002",
        ]:
            self.assertIn(origin, server)
        self.assertIn("allow_origins=_cors_origins.split(\",\") if _cors_origins else DEFAULT_CORS_ORIGINS", server)

    def test_log_routes_are_mounted_with_auth_dependency(self):
        server = self.read("backend/server.py")
        logs = self.read("backend/routes/logs.py")

        self.assertRegex(
            server,
            r"api\.include_router\(logs_router,\s*dependencies=\[Depends\(get_current_user\)\]\)",
            "logs_router must be mounted with the same auth dependency as other private API routes",
        )
        self.assertNotIn('@app.get("/api/logs', server)
        self.assertNotIn('@app.post("/api/logs', server)
        self.assertIn('router = APIRouter(prefix="/logs"', logs)

    def test_password_hashing_uses_bcrypt_for_new_passwords(self):
        auth_routes = self.read("backend/routes/auth.py")
        password_security = self.read("backend/password_security.py")

        self.assertNotIn("hashlib.sha256((password + salt)", auth_routes)
        self.assertNotIn("hashlib.sha256(password.encode", auth_routes)
        self.assertIn("hash_password", auth_routes)
        self.assertIn("bcrypt.hashpw", password_security)
        self.assertIn("verify_password", password_security)

    def test_frontend_has_no_unguarded_console_logging(self):
        frontend_root = ROOT / "frontend" / "src"
        allowed_files = {
            "lib/clientLogger.ts",
        }
        offenders = []
        for path in frontend_root.rglob("*"):
            if path.suffix not in {".ts", ".tsx", ".js", ".jsx"}:
                continue
            rel = path.relative_to(frontend_root).as_posix()
            if rel in allowed_files:
                continue
            text = path.read_text(encoding="utf-8")
            if "console." in text:
                offenders.append(rel)
        self.assertEqual([], offenders, f"Route frontend logs through clientLogger instead of console: {offenders}")

    def test_foreign_markets_are_backend_driven_and_global(self):
        markets = self.read("backend/markets.py")
        foreign_tab = self.read("frontend/src/components/tabs/ForeignTab.tsx")
        add_ticker = self.read("frontend/src/components/AddTickerDialog.tsx")

        for code in ["JP", "DE", "FR", "IN_NSE", "SG", "KR", "TW", "BR", "ZA"]:
            self.assertIn(f'code="{code}"', markets)
        self.assertNotIn("FOREIGN_CODES", foreign_tab)
        self.assertIn("markets.filter((market) => market.code !== 'US')", foreign_tab)
        self.assertIn("apiFetch('/api/markets')", add_ticker)
        self.assertNotIn("const MARKET_OPTIONS = [", add_ticker)

    def test_broker_credentials_do_not_use_runtime_legacy_fallback(self):
        broker_manager = self.read("backend/broker_manager.py")

        self.assertNotIn("_LEGACY_KEY", broker_manager)
        self.assertNotIn("_xor_bytes", broker_manager)
        self.assertNotIn("base64.b64decode(encrypted)", broker_manager)
        self.assertNotIn("migrate_credential_format", broker_manager)


if __name__ == "__main__":
    unittest.main()
