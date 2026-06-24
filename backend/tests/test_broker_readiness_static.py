"""Static checks that broker cards expose beta-ready status accurately."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class BrokerReadinessStaticTest(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_broker_info_has_explicit_readiness_metadata(self):
        text = self.read("backend/brokers/base.py")

        self.assertIn("readiness: str", text)
        self.assertIn("readiness_note: str", text)

    def test_registry_classifies_production_experimental_and_unavailable_brokers(self):
        text = self.read("backend/brokers/registry.py")

        self.assertIn('readiness="production"', text)
        self.assertIn('readiness="experimental"', text)
        self.assertIn('readiness="unavailable"', text)
        self.assertIn("Official API", text)
        self.assertIn("Unofficial", text)

    def test_broker_api_serializes_readiness_metadata(self):
        text = self.read("backend/routes/brokers.py")

        self.assertIn('"readiness": info.readiness', text)
        self.assertIn('"readiness_note": info.readiness_note', text)

    def test_frontend_renders_readiness_badges_and_notes(self):
        text = self.read("frontend/src/components/tabs/BrokersTab.tsx")

        self.assertIn("READINESS_STYLES", text)
        self.assertIn("READINESS_LABELS", text)
        self.assertIn("readiness_note", text)
        self.assertIn("broker-readiness-note", text)


if __name__ == "__main__":
    unittest.main()
