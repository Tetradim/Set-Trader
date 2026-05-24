"""Static checks for launcher smoke testing and backend test commands."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class LauncherAndTestEnvStaticTest(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_launcher_has_non_destructive_smoke_test_mode(self):
        launcher = self.read("Launch-Sentinel-Pulse.ps1")

        self.assertIn("[switch]$SmokeTest", launcher)
        self.assertIn("Launcher smoke test passed", launcher)
        self.assertIn("Join-ProcessArguments", launcher)
        self.assertIn("$env:SENTINEL_OPEN_BROWSER = \"0\"", launcher)
        self.assertIn("Stop-OwnedProcesses", launcher)

    def test_backend_test_runner_splits_static_and_live_suites(self):
        runner = self.read("backend/run-tests.ps1")
        makefile = self.read("Makefile")

        self.assertIn("-m unittest", runner)
        self.assertIn("-m pytest", runner)
        self.assertIn("REACT_APP_BACKEND_URL", runner)
        self.assertIn("test-backend-static", makefile)
        self.assertIn("test-backend-live", makefile)


if __name__ == "__main__":
    unittest.main()
