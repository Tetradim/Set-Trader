import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class LauncherConsolidationStaticTests(unittest.TestCase):
    def test_only_current_windows_launchers_are_shipped(self):
        launchers = sorted(path.name for path in ROOT.glob("Launch-Sentinel-Pulse*"))
        self.assertEqual(
            launchers,
            [
                "Launch-Sentinel-Pulse-Local.bat",
                "Launch-Sentinel-Pulse-Local.ps1",
                "Launch-Sentinel-Pulse.bat",
                "Launch-Sentinel-Pulse.ps1",
            ],
        )
        self.assertFalse(any("-v2" in launcher or "-v3" in launcher for launcher in launchers))

    def test_batch_wrapper_invokes_unversioned_powershell_launcher(self):
        text = (ROOT / "Launch-Sentinel-Pulse.bat").read_text(encoding="utf-8")
        self.assertIn("Launch-Sentinel-Pulse.ps1", text)
        self.assertNotIn("-v2", text)
        self.assertNotIn("-v3", text)

    def test_batch_wrapper_uses_system_powershell_before_path_lookup(self):
        text = (ROOT / "Launch-Sentinel-Pulse.bat").read_text(encoding="utf-8")

        self.assertIn("%SystemRoot%\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", text)
        self.assertIn('"%POWERSHELL%" -NoProfile -ExecutionPolicy Bypass -File', text)
        self.assertIn("PowerShell was not found", text)

    def test_launcher_settings_are_local_only(self):
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("launcher-settings.ini", gitignore)

    def test_root_launcher_does_not_duplicate_packaged_browser_open(self):
        text = (ROOT / "Launch-Sentinel-Pulse.ps1").read_text(encoding="utf-8")
        self.assertIn("$serverWillOpenBrowser = $false", text)
        self.assertIn('$env:SENTINEL_OPEN_BROWSER = "0"', text)
        self.assertIn("$BrowserProcess = Start-BrowserWindow -Url $url", text)

    def test_root_launcher_bootstraps_beta_runtime_dependencies(self):
        text = (ROOT / "Launch-Sentinel-Pulse.ps1").read_text(encoding="utf-8")

        self.assertIn("function Ensure-LauncherDependencies", text)
        self.assertIn("function Test-VisualCRuntimeInstalled", text)
        self.assertIn("https://aka.ms/vc14/vc_redist.x64.exe", text)
        self.assertIn("function Install-MongoDbPortableDependency", text)
        self.assertIn("https://fastdl.mongodb.org/windows/mongodb-windows-x86_64-8.0.26.zip", text)
        self.assertIn("https://fastdl.mongodb.org/windows/mongodb-windows-x86_64-8.0.26-signed.msi", text)
        self.assertIn('Join-Path $env:LOCALAPPDATA "Sentinel Pulse\\dependencies"', text)
        self.assertIn("Expand-Archive", text)
        self.assertIn("Ensure-LauncherDependencies -MongoPort $MongoPort", text)

    def test_root_launcher_bootstrap_runs_before_mongodb_startup_failure_path(self):
        text = (ROOT / "Launch-Sentinel-Pulse.ps1").read_text(encoding="utf-8")

        bootstrap_index = text.index("Ensure-LauncherDependencies -MongoPort $MongoPort")
        mongo_start_index = text.index('throw "MongoDB was not found. Install MongoDB Community Server or pass -MongoPath."')

        self.assertLess(bootstrap_index, mongo_start_index)

    def test_root_launcher_opens_source_frontend_instead_of_backend_root(self):
        text = (ROOT / "Launch-Sentinel-Pulse.ps1").read_text(encoding="utf-8")
        self.assertIn("[int]$FrontendPort = 3001", text)
        self.assertIn("function Find-Npm", text)
        self.assertIn('Join-Path $ProjectRoot "frontend\\package.json"', text)
        self.assertIn('$env:VITE_BACKEND_URL = ""', text)
        self.assertIn('$env:REACT_APP_BACKEND_URL = ""', text)
        self.assertIn('Write-Status "Starting frontend UI on port $FrontendPort"', text)
        self.assertIn('"run", "dev", "--", "--host", "127.0.0.1", "--port", "$FrontendPort"', text)
        self.assertIn('$url = "http://127.0.0.1:$FrontendPort"', text)
        self.assertNotIn('$url = "http://localhost:$AppPort"', text)
        self.assertNotIn('$url = "http://localhost:$FrontendPort"', text)

    def test_windows_launchers_use_relative_dev_api_and_set_local_cors(self):
        for launcher in ["Launch-Sentinel-Pulse.ps1", "Launch-Sentinel-Pulse-Local.ps1"]:
            with self.subTest(launcher=launcher):
                text = (ROOT / launcher).read_text(encoding="utf-8")
                self.assertIn('$env:CORS_ORIGINS =', text)
                self.assertIn('"http://localhost:$FrontendPort"', text)
                self.assertIn('"http://127.0.0.1:$FrontendPort"', text)
                self.assertIn('$env:VITE_BACKEND_URL = ""', text)
                self.assertIn('$env:REACT_APP_BACKEND_URL = ""', text)
                self.assertNotIn('$env:VITE_BACKEND_URL = $backendUrl', text)

    def test_windows_launchers_verify_existing_ports_are_sentinel_pulse(self):
        for launcher in ["Launch-Sentinel-Pulse.ps1", "Launch-Sentinel-Pulse-Local.ps1"]:
            with self.subTest(launcher=launcher):
                text = (ROOT / launcher).read_text(encoding="utf-8")
                self.assertIn("function Test-SentinelPulseBackend", text)
                self.assertIn("http://127.0.0.1:$Port/api/health", text)
                self.assertIn('$health.status -eq "online"', text)
                self.assertIn('"market_open"', text)
                self.assertIn("function Test-SentinelPulseFrontend", text)
                self.assertIn('$response.Content -match "Sentinel Pulse"', text)
                self.assertIn("is already in use by another service", text)

    def test_windows_launchers_replace_stale_existing_pulse_processes(self):
        for launcher in ["Launch-Sentinel-Pulse.ps1", "Launch-Sentinel-Pulse-Local.ps1"]:
            with self.subTest(launcher=launcher):
                text = (ROOT / launcher).read_text(encoding="utf-8")
                self.assertIn("function Stop-PortOwnerProcess", text)
                self.assertIn("Replacing existing $Label on port $Port", text)
                self.assertIn('-Label "Sentinel Pulse backend"', text)
                self.assertIn('-Label "Sentinel Pulse frontend"', text)
                self.assertIn("Stop-PortOwnerProcess -Port $", text)
                self.assertNotIn("already running on port $AppPort", text)
                self.assertNotIn("already running on port $BackendPort", text)
                self.assertNotIn("already running on port $FrontendPort", text)

    def test_windows_launchers_auto_resolve_frontend_port_conflicts(self):
        for launcher in ["Launch-Sentinel-Pulse.ps1", "Launch-Sentinel-Pulse-Local.ps1"]:
            with self.subTest(launcher=launcher):
                text = (ROOT / launcher).read_text(encoding="utf-8")
                self.assertIn("function Resolve-SentinelPulseFrontendPort", text)
                self.assertIn("Found existing Sentinel Pulse frontend on port $port", text)
                self.assertIn("Frontend port $RequestedPort is used by another app; using port $port", text)
                self.assertIn("$FrontendPort = Resolve-SentinelPulseFrontendPort -RequestedPort $FrontendPort", text)
                self.assertIn("no free frontend port was found", text)

    def test_vite_dev_server_proxies_api_to_backend(self):
        text = (ROOT / "frontend" / "vite.config.ts").read_text(encoding="utf-8")
        self.assertIn("VITE_BACKEND_URL", text)
        self.assertIn("'http://127.0.0.1:8001'", text)
        self.assertIn("proxy:", text)
        self.assertIn("'/api':", text)
        self.assertIn("target: backendUrl", text)
        self.assertIn("ws: true", text)

    def test_root_launcher_stops_started_child_process_trees(self):
        text = (ROOT / "Launch-Sentinel-Pulse.ps1").read_text(encoding="utf-8")
        self.assertIn("function Stop-ProcessTree", text)
        self.assertIn("ParentProcessId = $ProcessId", text)
        self.assertIn("Stop-ProcessTree -ProcessId $process.Id", text)

    def test_root_launcher_tracks_browser_window(self):
        text = (ROOT / "Launch-Sentinel-Pulse.ps1").read_text(encoding="utf-8")
        self.assertIn("$BrowserProcess = $null", text)
        self.assertIn("$BrowserProfileDir = $null", text)
        self.assertIn("$BrowserProcessIds = @()", text)
        self.assertIn("$BrowserWindowProcessIds = @()", text)
        self.assertIn("$BrowserStartedAt = $null", text)
        self.assertIn("function Start-BrowserWindow", text)
        self.assertIn("function Get-BrowserProfileProcesses", text)
        self.assertIn("function Get-BrowserWindowProcesses", text)
        self.assertIn("function Wait-BrowserProfileProcesses", text)
        self.assertIn("function Wait-BrowserWindowProcesses", text)
        self.assertIn("function Test-BrowserWindowClosed", text)
        self.assertIn("function Stop-BrowserWindow", text)
        self.assertIn("--user-data-dir=$script:BrowserProfileDir", text)
        self.assertIn("--disable-background-mode", text)
        self.assertNotIn("Browser process handed off; close monitoring disabled", text)
        self.assertNotIn("$script:BrowserMonitorDisabled = $true", text)
        self.assertIn("Browser window closed; shutting down Sentinel Pulse", text)
        self.assertNotIn('throw "Browser window closed."', text)
        self.assertIn("SENTINEL_OPEN_BROWSER", text)

    def test_windows_launchers_detect_visible_browser_window_close(self):
        for launcher in ["Launch-Sentinel-Pulse.ps1", "Launch-Sentinel-Pulse-Local.ps1"]:
            with self.subTest(launcher=launcher):
                text = (ROOT / launcher).read_text(encoding="utf-8")
                self.assertIn("$BrowserWindowProcessIds = @()", text)
                self.assertIn("function Get-BrowserWindowProcesses", text)
                self.assertIn("MainWindowHandle", text)
                self.assertIn("function Wait-BrowserWindowProcesses", text)
                self.assertIn("$script:BrowserWindowProcessIds", text)
                self.assertIn("if ($BrowserWindowProcessIds.Count -gt 0) { return $true }", text)
                self.assertIn("Wait-BrowserWindowProcesses -Seconds 10", text)
                self.assertNotIn("if ($profileProcesses.Count -gt 0) { return $false }\n\n    $knownProcesses", text)

    def test_windows_launchers_register_console_shutdown_cleanup(self):
        for launcher in ["Launch-Sentinel-Pulse.ps1", "Launch-Sentinel-Pulse-Local.ps1"]:
            with self.subTest(launcher=launcher):
                text = (ROOT / launcher).read_text(encoding="utf-8")
                self.assertIn("$ShutdownStarted = $false", text)
                self.assertIn("function Invoke-LauncherCleanup", text)
                self.assertIn("function Register-LauncherShutdownHandlers", text)
                self.assertIn("Register-EngineEvent -SourceIdentifier PowerShell.Exiting", text)
                self.assertIn("[Console]::CancelKeyPress", text)
                self.assertIn("Invoke-LauncherCleanup", text)

    def test_windows_launchers_start_external_shutdown_watchdog(self):
        for launcher in ["Launch-Sentinel-Pulse.ps1", "Launch-Sentinel-Pulse-Local.ps1"]:
            with self.subTest(launcher=launcher):
                text = (ROOT / launcher).read_text(encoding="utf-8")
                self.assertIn("function Start-LauncherShutdownWatchdog", text)
                self.assertIn("function Stop-LauncherShutdownWatchdog", text)
                self.assertIn("$LauncherWatchdogStopFile", text)
                self.assertIn("$ParentProcessId", text)
                self.assertIn("Start-Process -FilePath \"powershell.exe\"", text)
                self.assertIn("-WindowStyle Hidden", text)
                self.assertIn("Get-ProfileProcesses", text)
                self.assertIn("Stop-ProcessTreeById", text)
                self.assertIn("Start-LauncherShutdownWatchdog", text)
                self.assertIn("Stop-LauncherShutdownWatchdog", text)

    def test_windows_launchers_quote_empty_process_arguments(self):
        for launcher in ["Launch-Sentinel-Pulse.ps1", "Launch-Sentinel-Pulse-Local.ps1"]:
            with self.subTest(launcher=launcher):
                text = (ROOT / launcher).read_text(encoding="utf-8")
                self.assertIn("[string]::IsNullOrEmpty($arg)", text)

    def test_local_batch_wrapper_only_pauses_on_error(self):
        text = (ROOT / "Launch-Sentinel-Pulse-Local.bat").read_text(encoding="utf-8")
        self.assertIn('if not "%EXITCODE%"=="0" (', text)
        self.assertIn("pause", text)
        self.assertNotIn("Sentinel Pulse local launcher exited with code %EXITCODE%.\npause", text)

    def test_root_launcher_quotes_browser_arguments_with_user_profile_spaces(self):
        text = (ROOT / "Launch-Sentinel-Pulse.ps1").read_text(encoding="utf-8")
        self.assertIn("$browserArgs = Join-ProcessArguments -Arguments @(", text)
        self.assertIn('Start-Process -FilePath $browserExe -ArgumentList $browserArgs -PassThru', text)

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
        self.assertIn("$startParams.ArgumentList = Join-ProcessArguments -Arguments $ArgumentList", text)

    def test_root_launcher_omits_empty_process_argument_list(self):
        text = (ROOT / "Launch-Sentinel-Pulse.ps1").read_text(encoding="utf-8")
        self.assertIn("if ($ArgumentList -and $ArgumentList.Count -gt 0)", text)
        self.assertIn("$process = Start-Process @startParams", text)

    def test_packaged_windows_launcher_allows_browser_open_suppression(self):
        text = (ROOT / "backend" / "win_launcher.py").read_text(encoding="utf-8")
        self.assertIn('SENTINEL_OPEN_BROWSER', text)
        self.assertIn('webbrowser.open', text)
        self.assertIn('webbrowser.open(f"http://127.0.0.1:{port}")', text)
        self.assertIn("s.connect(('127.0.0.1', port))", text)
        self.assertNotIn('webbrowser.open(f"http://localhost:{port}")', text)

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
