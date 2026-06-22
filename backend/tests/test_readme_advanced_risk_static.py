"""Static README checks for completed advanced risk roadmap work."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class ReadmeAdvancedRiskStaticTest(unittest.TestCase):
    def test_obsolete_roadmap_section_is_removed(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertNotIn("Roadmap: Planned Upgrades & Enhancements", readme)
        self.assertNotIn("Items marked with", readme)

    def test_advanced_risk_is_documented_as_implemented(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        for phrase in [
            "Advanced Risk Management",
            "ML Risk Assessment",
            "Dynamic Circuit Breakers",
            "Predictive Liquidity",
            "VaR/CVaR Limits",
            "/api/risk/advanced/check",
        ]:
            self.assertIn(phrase, readme)


if __name__ == "__main__":
    unittest.main()
