"""Static backend checks for demo/dev leftovers.

These tests intentionally avoid importing the FastAPI app so they can run
without MongoDB or external service dependencies.
"""
from pathlib import Path
import re
import unittest


BACKEND = Path(__file__).resolve().parents[1]


class NoDemoArtifactsTest(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (BACKEND / relative_path).read_text(encoding="utf-8")

    def test_server_does_not_mount_developer_or_duplicate_auth_router(self):
        text = self.read("server.py")

        self.assertNotIn("routes.developer", text)
        self.assertNotIn("developer_router", text)
        self.assertEqual(len(re.findall(r"api\.include_router\(auth_router\)", text)), 1)
        self.assertNotIn("os.getenv('ENVIRONMENT', 'development')", text)

    def test_auth_route_is_single_database_backed_implementation(self):
        text = self.read("routes/auth.py")

        self.assertNotRegex(text, r"\b_users\b")
        self.assertNotIn("For demo purposes", text)
        self.assertNotIn("@router.post(\"/auth/login\"", text)
        self.assertEqual(len(re.findall(r"class LoginRequest", text)), 1)
        self.assertEqual(len(re.findall(r"async def login", text)), 1)

    def test_api_router_prefixes_are_not_double_prefixed(self):
        for relative_path in [
            "routes/audit.py",
            "routes/analytics.py",
            "routes/auth.py",
            "routes/ops.py",
            "routes/orders.py",
            "routes/reconciliation.py",
            "routes/risk.py",
            "routes/slo.py",
        ]:
            text = self.read(relative_path)
            self.assertNotRegex(text, r"APIRouter\(prefix=[\"']/api/")

    def test_no_sample_or_simulated_market_data_fallbacks(self):
        forbidden = {
            "routes/audit.py": ["init_sample_audit_events", "sample events for demo"],
            "routes/analytics.py": ["In production", "Momentum", "2024-01-30"],
            "routes/ops.py": ["_services_db or", "_incidents_db or", "_runbooks_db or"],
            "price_service.py": ["DEMO_TICKERS", "Last resort: random price", "\"simulated\""],
        }

        for relative_path, needles in forbidden.items():
            text = self.read(relative_path)
            for needle in needles:
                self.assertNotIn(needle, text)


if __name__ == "__main__":
    unittest.main()
