import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class WindowsInstallerBootstrapStaticTests(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_local_batch_reports_missing_powershell_script_before_invoking_powershell(self):
        text = self.read("Launch-Sentinel-Pulse-Local.bat")

        self.assertIn('set "LAUNCHER=%~dp0Launch-Sentinel-Pulse-Local.ps1"', text)
        self.assertIn('if not exist "%LAUNCHER%" (', text)
        self.assertIn("Sentinel Pulse local launcher file is missing", text)
        self.assertIn("Extract the full Sentinel Pulse folder first", text)
        self.assertIn("SentinelPulse-Setup", text)
        self.assertLess(
            text.index('if not exist "%LAUNCHER%" ('),
            text.index('"%POWERSHELL%" -NoProfile -ExecutionPolicy Bypass -File "%LAUNCHER%"'),
        )

    def test_build_windows_packages_first_run_launcher_scripts(self):
        text = self.read("build-windows.ps1")

        self.assertIn('$PACKAGE = Join-Path $DIST "SentinelPulse"', text)
        self.assertIn('"Launch-Sentinel-Pulse.bat"', text)
        self.assertIn('"Launch-Sentinel-Pulse.ps1"', text)
        self.assertIn('"Setup-And-Launch.bat"', text)
        self.assertIn("Copy-Item -Path (Join-Path $ROOT $file)", text)
        self.assertIn("-Destination (Join-Path $PACKAGE $file)", text)
        self.assertIn('call "%~dp0Launch-Sentinel-Pulse.bat"', text)
        self.assertIn('Copy-Item (Join-Path $BACKEND ".env") (Join-Path $PACKAGE ".env") -Force', text)
        self.assertNotIn("Sentinel Pulse.exe", text)
        self.assertNotIn("Recipients need MongoDB installed", text)
        self.assertNotIn("Prerequisites:", text)

    def test_legacy_installer_shortcuts_to_first_run_launcher(self):
        text = self.read("build-installer.ps1")

        self.assertIn('$PACKAGE = Join-Path $DIST "SentinelPulse"', text)
        self.assertIn('Test-Path (Join-Path $PACKAGE "SentinelPulse.exe")', text)
        self.assertIn('URL=file:///$InstallDir/Launch-Sentinel-Pulse.bat', text)
        self.assertIn('start "" "$InstallDir\\Launch-Sentinel-Pulse.bat"', text)
        self.assertNotIn("Sentinel Pulse.exe", text)

    def test_inno_installer_launches_wrapper_and_leaves_dependencies_to_first_run(self):
        text = self.read("setup.iss")

        self.assertIn('Filename: "{app}\\Setup-And-Launch.bat"', text)
        self.assertIn('Filename: "{app}\\Launch-Sentinel-Pulse.bat"', text)
        self.assertIn('Source: "Launch-Sentinel-Pulse.bat"', text)
        self.assertIn('Source: "Launch-Sentinel-Pulse.ps1"', text)
        self.assertNotIn('{tmp}\\vc_redist.x64.exe', text)

    def test_inno_installer_is_per_user_beta_installer_with_desktop_launcher(self):
        text = self.read("setup.iss")

        self.assertIn("DefaultDirName={localappdata}\\Programs\\{#MyAppName}", text)
        self.assertIn("PrivilegesRequired=lowest", text)
        self.assertIn("OutputBaseFilename=SentinelPulse-Beta-Setup-{#MyAppVersion}", text)
        self.assertIn('Name: "{userdesktop}\\{#MyAppName}"; Filename: "{app}\\Launch-Sentinel-Pulse.bat"', text)
        self.assertIn('Name: "{group}\\{#MyAppName}"; Filename: "{app}\\Launch-Sentinel-Pulse.bat"', text)
        self.assertIn('Filename: "{app}\\Setup-And-Launch.bat"', text)
        self.assertNotIn("DefaultDirName={autopf}", text)
        self.assertNotIn("PrivilegesRequired=admin", text)
        self.assertNotIn('Name: "{commondesktop}\\{#MyAppName}"', text)

    def test_ci_build_copies_real_launcher_instead_of_generating_direct_exe_batch(self):
        text = self.read(".github/workflows/build.yml")

        self.assertIn("Copy launchers into package", text)
        self.assertIn('Copy-Item "Launch-Sentinel-Pulse.bat"', text)
        self.assertIn('Copy-Item "Launch-Sentinel-Pulse.ps1"', text)
        self.assertIn('call "%~dp0Launch-Sentinel-Pulse.bat"', text)
        self.assertNotIn("MongoDB not bundled - ensure MongoDB is running externally", text)
        self.assertNotIn("Download VC++ Redist", text)

    def test_docs_present_first_run_dependency_download_as_beta_path(self):
        readme = self.read("README.md")
        windows = self.read("WINDOWS_BUILD.md")

        self.assertIn("downloads missing runtime dependencies on first launch", readme)
        self.assertIn("first run downloads missing runtime dependencies", windows)
        self.assertIn("SentinelPulse-Setup-", windows)
        self.assertIn("SentinelPulse-Beta-Setup-", readme)
        self.assertIn("SentinelPulse-Beta-Setup-", windows)
        self.assertIn("does not require admin", windows)
        self.assertIn("Desktop shortcut named Sentinel Pulse", windows)
        self.assertNotIn("Recipients only need **MongoDB**", windows)
        self.assertNotIn("Recipients need MongoDB installed", windows)


if __name__ == "__main__":
    unittest.main()
