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

    def test_root_launcher_does_not_duplicate_packaged_browser_open(self):
        text = (ROOT / "Launch-Sentinel-Pulse.ps1").read_text(encoding="utf-8")
        self.assertIn("$serverWillOpenBrowser = $false", text)
        self.assertIn('$env:SENTINEL_OPEN_BROWSER = "0"', text)
        self.assertIn("$BrowserProcess = Start-BrowserWindow -Url $url", text)

    def test_root_launcher_tracks_browser_window(self):
        text = (ROOT / "Launch-Sentinel-Pulse.ps1").read_text(encoding="utf-8")
        self.assertIn("$BrowserProcess = $null", text)
        self.assertIn("function Start-BrowserWindow", text)
        self.assertIn("function Stop-BrowserWindow", text)
        self.assertIn("Browser window closed.", text)
        self.assertIn("SENTINEL_OPEN_BROWSER", text)

    def test_packaged_windows_launcher_allows_browser_open_suppression(self):
        text = (ROOT / "backend" / "win_launcher.py").read_text(encoding="utf-8")
        self.assertIn('SENTINEL_OPEN_BROWSER', text)
        self.assertIn('webbrowser.open', text)


if __name__ == "__main__":
    unittest.main()
