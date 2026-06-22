"""Static checks for advanced risk route wiring."""
from pathlib import Path
import unittest


BACKEND = Path(__file__).resolve().parents[1]


class AdvancedRiskRouteStaticTest(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (BACKEND / relative_path).read_text(encoding="utf-8")

    def test_risk_router_exposes_advanced_risk_endpoints(self):
        text = self.read("routes/risk.py")

        for route in [
            '@router.post("/advanced/score")',
            '@router.post("/advanced/liquidity-size")',
            '@router.post("/advanced/var-cvar")',
            '@router.post("/advanced/circuit-breakers/{broker_id}/adjust")',
            '@router.post("/advanced/check")',
        ]:
            self.assertIn(route, text)

    def test_routes_call_advanced_risk_manager(self):
        text = self.read("routes/risk.py")

        for call in [
            "advanced_risk_manager.score_trade",
            "advanced_risk_manager.recommend_position_size",
            "advanced_risk_manager.evaluate_var_cvar",
            "advanced_risk_manager.recommend_circuit_breaker",
            "advanced_risk_manager.assess_trade",
        ]:
            self.assertIn(call, text)


if __name__ == "__main__":
    unittest.main()
