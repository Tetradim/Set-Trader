import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class LauncherConsolidationStaticTests(unittest.TestCase):
    def test_only_unversioned_windows_launchers_are_shipped(self):
        launchers = sorted(path.name for path in ROOT.glob("Launch-Sentinel-Pulse*"))
        self.assertEqual(
            launchers,
            ["Launch-Sentinel-Pulse.bat", "Launch-Sentinel-Pulse.ps1"],
        )

    def test_batch_wrapper_invokes_unversioned_powershell_launcher(self):
        text = (ROOT / "Launch-Sentinel-Pulse.bat").read_text(encoding="utf-8")
        self.assertIn("Launch-Sentinel-Pulse.ps1", text)
        self.assertNotIn("-v2", text)
        self.assertNotIn("-v3", text)

    def test_launcher_settings_are_local_only(self):
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("launcher-settings.ini", gitignore)


if __name__ == "__main__":
    unittest.main()
