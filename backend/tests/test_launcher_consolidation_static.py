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

    def test_root_launcher_writes_desktop_log_and_backend_uses_same_file(self):
        text = (ROOT / "Launch-Sentinel-Pulse.ps1").read_text(encoding="utf-8")
        self.assertIn('[Environment]::GetFolderPath("Desktop")', text)
        self.assertIn("Sentinel-Pulse.log", text)
        self.assertIn("Start-Transcript", text)
        self.assertIn('$env:LOG_FILE = $LogFile', text)

    def test_root_launcher_uses_separate_transcript_file(self):
        text = (ROOT / "Launch-Sentinel-Pulse.ps1").read_text(encoding="utf-8")
        self.assertIn('$TranscriptFile = Join-Path $LogPath "Sentinel-Pulse-Transcript.log"', text)
        self.assertIn("Start-Transcript -Path $TranscriptFile -Append", text)
        self.assertNotIn("Start-Transcript -Path $LogFile", text)

    def test_root_launcher_starts_mongodb_from_bin_with_system_data_path(self):
        text = (ROOT / "Launch-Sentinel-Pulse.ps1").read_text(encoding="utf-8")
        self.assertIn('Join-Path $env:SystemDrive "data\\db"', text)
        self.assertIn("$mongoBin = Split-Path -Parent $mongoExe", text)
        self.assertIn("Preparing MongoDB working directory", text)
        self.assertIn("Start-Sleep -Seconds 3", text)
        self.assertIn("Wait-PortAttempts -Port $MongoPort -Attempts 3 -IntervalSeconds 3", text)
        self.assertIn("-WorkingDirectory $mongoBin", text)
        self.assertIn('"--dbpath", $DataPath', text)

    def test_root_launcher_quotes_process_arguments_with_spaces(self):
        text = (ROOT / "Launch-Sentinel-Pulse.ps1").read_text(encoding="utf-8")
        self.assertIn("function Join-ProcessArguments", text)
        self.assertIn("$escaped = $arg.Replace('\"', '\\\"')", text)
        self.assertIn("-ArgumentList (Join-ProcessArguments -Arguments $ArgumentList)", text)

    def test_packaged_windows_launcher_allows_browser_open_suppression(self):
        text = (ROOT / "backend" / "win_launcher.py").read_text(encoding="utf-8")
        self.assertIn('SENTINEL_OPEN_BROWSER', text)
        self.assertIn('webbrowser.open', text)

    def test_packaged_windows_launcher_uses_desktop_log_and_system_mongo_data_path(self):
        text = (ROOT / "backend" / "win_launcher.py").read_text(encoding="utf-8")
        self.assertIn('Path.home() / "Desktop"', text)
        self.assertIn('"Sentinel-Pulse.log"', text)
        self.assertIn('os.environ.setdefault("LOG_FILE", str(get_log_path()))', text)
        self.assertIn('get_default_mongo_data_dir()', text)
        self.assertIn('time.sleep(3)', text)
        self.assertIn('for attempt in range(1, 4):', text)
        self.assertIn('cwd=str(mongo_exe.parent)', text)


if __name__ == "__main__":
    unittest.main()
