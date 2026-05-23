import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class UninstallCleanupStaticTests(unittest.TestCase):
    def test_inno_uninstall_removes_desktop_logs_and_installers(self):
        text = (ROOT / "setup.iss").read_text(encoding="utf-8")

        for desktop in ("{userdesktop}", "{commondesktop}"):
            for artifact in (
                "Sentinel-Pulse.log",
                "Sentinel-Pulse-Transcript.log",
                "Sentinel-Pulse-MongoDB.log",
                "sentinel_pulse.log",
                "SentinelPulse-Setup*.exe",
                "Sentinel Pulse-Setup*.exe",
                "Sentinel Pulse Setup*.exe",
            ):
                self.assertIn(f'Name: "{desktop}\\{artifact}"', text)

    def test_legacy_batch_uninstaller_removes_desktop_logs_and_installers(self):
        text = (ROOT / "build-installer.ps1").read_text(encoding="utf-8")

        for desktop in ("%USERPROFILE%\\Desktop", "$env:PUBLIC\\Desktop"):
            for artifact in (
                "Sentinel-Pulse.log",
                "Sentinel-Pulse-Transcript.log",
                "Sentinel-Pulse-MongoDB.log",
                "sentinel_pulse.log",
                "SentinelPulse-Setup*.exe",
                "Sentinel Pulse-Setup*.exe",
                "Sentinel Pulse Setup*.exe",
            ):
                self.assertIn(f'del /q "{desktop}\\{artifact}"', text)


if __name__ == "__main__":
    unittest.main()
