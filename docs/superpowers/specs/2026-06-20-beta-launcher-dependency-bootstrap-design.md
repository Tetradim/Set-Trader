# Beta Launcher Dependency Bootstrap Design

## Goal

Make the Windows beta installer and launcher recover missing runtime dependencies automatically so non-technical beta testers can install Sentinel Pulse, double-click the app shortcut, and reach the dashboard without manually installing MongoDB, Python, Node.js, npm, Git, or common Windows runtimes.

## Scope

The supported beta path is a single Windows installer, `SentinelPulse-Setup-<version>.exe`, produced by the existing PyInstaller plus Inno Setup build. The installer places the packaged backend/frontend app and the Windows launch scripts under the install directory, then creates Desktop and Start Menu shortcuts that run `Launch-Sentinel-Pulse.bat`.

The launcher handles the packaged Windows beta path. It will not install developer toolchains for testers. Python, Node.js, npm, yarn, and Git remain build/source-development requirements, not beta-user requirements.

Source checkout launchers remain available for development and branch testing. They should fail with clear setup guidance when the source package is incomplete, rather than surfacing raw PowerShell `-File` errors.

## Behavior

`Launch-Sentinel-Pulse.bat` resolves Windows PowerShell from the system directory first so a broken `PATH` does not produce exit code `9009`.

`Launch-Sentinel-Pulse.ps1` runs a dependency bootstrap before starting MongoDB or Sentinel Pulse:

- Check for Microsoft Visual C++ Redistributable and install the current x64 redistributable from Microsoft's supported permalink if absent.
- Check for MongoDB on the requested port, in the app-local dependency cache, bundled with the app, installed under Program Files, or available on `PATH`.
- If MongoDB is missing, download the official MongoDB Community Windows x64 zip into `%LOCALAPPDATA%\Sentinel Pulse\dependencies`, extract it there, locate `mongod.exe`, and use that copy.
- If the zip path cannot produce `mongod.exe`, fall back to the official MSI only when the launcher is running elevated.
- Log all checks, downloads, and failures to the same desktop log/transcript files the launcher already creates.

Installed shortcuts must launch `Launch-Sentinel-Pulse.bat`, not `SentinelPulse.exe` directly. This keeps dependency repair, logging, browser lifecycle management, and process cleanup on the same path for first run and later runs.

The packaged executable remains responsible for running the FastAPI app and serving the built React assets. Browser auto-open is suppressed when launched by the outer PowerShell launcher so testers get one dedicated browser window owned by the launcher lifecycle.

The local source batch wrapper checks that `Launch-Sentinel-Pulse-Local.ps1` exists before invoking PowerShell. If it is missing, it explains that the tester should extract the full zip or use the installer. This directly addresses the observed failure where a temporary extracted source path passed a non-existent `.ps1` file to PowerShell.

## Error Handling

Download failures will be reported with plain-language messages that tell testers to send the desktop logs. Silent installs treat success and reboot-required exit codes as recoverable. Admin-required recovery is attempted only when already elevated.

If a beta tester is offline or behind a blocked network during first launch, the launcher stops before starting the bot and points them to `Sentinel-Pulse.log` and `Sentinel-Pulse-Transcript.log` on the Desktop. Future launches reuse dependencies already present under `%LOCALAPPDATA%\Sentinel Pulse\dependencies`.

If the installed package is incomplete, the launcher reports the missing file and tells the tester to reinstall from the official `SentinelPulse-Setup-<version>.exe`.

## Packaging Alignment

`build-windows.ps1`, `build-installer.ps1`, `setup.iss`, and `.github/workflows/build.yml` should produce the same tester-facing shape:

- app files in the install directory include `SentinelPulse.exe`, the built static frontend, `.env`, `Launch-Sentinel-Pulse.bat`, `Launch-Sentinel-Pulse.ps1`, and `Setup-And-Launch.bat`;
- the Desktop shortcut, Start Menu shortcut, and post-install launch action all run `Launch-Sentinel-Pulse.bat` or `Setup-And-Launch.bat`;
- no shortcut asks testers to edit `.env`, install MongoDB, or run `mongod` manually;
- release documentation describes `SentinelPulse-Setup-<version>.exe` as the primary beta download.

## Tests

Static launcher and packaging tests will verify the batch wrapper avoids `PATH`-only PowerShell resolution, the PowerShell launcher contains VC++ and MongoDB bootstrap functions, official download URLs, local dependency-cache extraction, and a bootstrap call before the existing MongoDB startup failure path.

Additional checks will verify:

- `setup.iss` installs and shortcuts the launcher scripts instead of `SentinelPulse.exe` directly;
- `build-windows.ps1` and CI copy launcher scripts into the packaged output;
- `build-installer.ps1` uses the packaged launcher path and does not reference the obsolete spaced executable name;
- `Launch-Sentinel-Pulse-Local.bat` gives a clear missing-script message before invoking PowerShell;
- `WINDOWS_BUILD.md` and the README beta quick start no longer tell testers that MongoDB is a manual prerequisite for the installer path.
