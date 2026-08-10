# Per-User Windows Beta Installer Design

## Goal

Make the Windows beta installer suitable for non-technical international beta testers: one setup executable, no admin prompt, Desktop and Start Menu launch shortcuts, automatic first-run dependency download, and clear support logs if anything fails.

## Scope

The supported beta path is a single Windows installer produced by the existing PyInstaller plus Inno Setup build. The installer should install Sentinel Pulse per user under `%LOCALAPPDATA%\Programs\Sentinel Pulse` and avoid UAC unless a tester explicitly runs the installer elevated.

The installer remains Windows-first. The existing macOS source installer can stay as a separate path and is not part of this change.

The first-run launcher remains the runtime bootstrap owner. It should continue downloading missing dependencies, including Microsoft Visual C++ Runtime and MongoDB, into `%LOCALAPPDATA%\Sentinel Pulse\dependencies`. Testers should not need Python, Node.js, npm, Git, MongoDB setup steps, or developer tools.

## Tester Flow

1. Tester double-clicks `SentinelPulse-Beta-Setup-<version>.exe`.
2. Installer defaults to a per-user install path and does not request admin privileges.
3. Installer creates a Desktop shortcut named `Sentinel Pulse`.
4. Installer creates Start Menu entries for launch and uninstall.
5. Installer runs `Setup-And-Launch.bat` after install when the launch task is checked.
6. `Setup-And-Launch.bat` delegates to `Launch-Sentinel-Pulse.bat`.
7. `Launch-Sentinel-Pulse.bat` runs `Launch-Sentinel-Pulse.ps1`.
8. The PowerShell launcher checks/downloads dependencies, starts MongoDB if needed, starts the packaged Sentinel Pulse server, and opens the dashboard.

## Installer Behavior

`setup.iss` should use per-user install defaults:

- `DefaultDirName={localappdata}\Programs\Sentinel Pulse`
- `PrivilegesRequired=lowest`
- user-scope Start Menu and Desktop entries

The Desktop shortcut must point to `Launch-Sentinel-Pulse.bat`, not `SentinelPulse.exe`. This keeps dependency repair, logging, browser lifecycle management, and process cleanup on the tested launcher path.

The post-install launch task should continue to run `Setup-And-Launch.bat`, and that wrapper should continue delegating to `Launch-Sentinel-Pulse.bat`.

The installer output should be named for beta distribution, for example `SentinelPulse-Beta-Setup-<version>.exe`, while preserving CI artifact upload behavior.

## Error Handling

Dependency and startup failures should stay launcher-centered. The launcher writes `Sentinel-Pulse.log` and `Sentinel-Pulse-Transcript.log` to the tester's Desktop and prints plain-language guidance telling the tester to send those files to support.

If dependency downloads fail because the tester is offline or behind a blocked network, the launcher should stop before starting the bot and preserve any already downloaded cache contents for the next run.

If the app package is incomplete, the launcher should tell the tester to reinstall from the official beta setup executable instead of surfacing raw PowerShell or missing-file errors.

## Packaging Alignment

The following paths should agree on the same tester-facing shape:

- `setup.iss`
- `build-windows.ps1`
- `.github/workflows/build.yml`
- `WINDOWS_BUILD.md`
- `README.md`
- installer static tests under `backend/tests`

The packaged install directory should contain `SentinelPulse.exe`, built frontend static assets, `.env`, `Launch-Sentinel-Pulse.bat`, `Launch-Sentinel-Pulse.ps1`, and `Setup-And-Launch.bat`.

## Tests

Add or update static tests to verify:

- Inno Setup uses a per-user install path.
- Inno Setup does not require admin privileges.
- Desktop and Start Menu launch shortcuts target `Launch-Sentinel-Pulse.bat`.
- The post-install launch task targets `Setup-And-Launch.bat`.
- The installer script still includes launcher files.
- The docs describe a no-admin, double-click beta setup flow.
- Existing first-run dependency download tests still pass.

Run the focused backend static installer tests after implementation. If local Inno Setup is unavailable, rely on static verification locally and leave the full installer artifact build to GitHub Actions.
