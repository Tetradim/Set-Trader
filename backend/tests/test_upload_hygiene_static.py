"""Static checks for first-push repository hygiene."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class UploadHygieneStaticTest(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_gitignore_keeps_templates_and_excludes_local_artifacts(self):
        text = self.read(".gitignore")

        self.assertIn("!backend/.env.example", text)
        for pattern in [
            "backend/data/",
            "logs/",
            "test_reports/",
            "screenshots/",
            "frontend/screenshots/",
            "frontend/*.log",
            "backend/trade_logs/",
            "memory/",
            ".superpowers/",
            "docs/superpowers/",
        ]:
            self.assertIn(pattern, text)
        self.assertNotIn("\n-e", text)

    def test_launchers_do_not_override_runtime_secrets(self):
        text = self.read("start-sentinel.ps1")

        self.assertNotIn("Get-Random", text)
        self.assertNotIn("$env:CREDENTIAL_KEY", text)

    def test_docs_do_not_reference_removed_demo_or_xor_credentials(self):
        for relative_path in ["MONGO_SETUP.md", "README.md"]:
            text = self.read(relative_path)
            self.assertNotIn("DEMO_MODE=true", text)
            self.assertNotIn("XOR", text)
            self.assertNotIn("built-in key", text)


if __name__ == "__main__":
    unittest.main()
