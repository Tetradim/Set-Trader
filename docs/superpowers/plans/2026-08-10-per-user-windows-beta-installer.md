# Per-User Windows Beta Installer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the Windows beta installer to a no-admin per-user installer with a Desktop shortcut that launches the first-run bootstrap path.

**Architecture:** Keep the existing PyInstaller package and first-run PowerShell launcher as the runtime boundary. Change the Inno Setup installer to install under the user's local app data folder, create user-scope shortcuts, and emit a beta-named setup executable. Guard the behavior with static tests and update release docs so beta testers get one double-click install path.

**Tech Stack:** Inno Setup 6, PowerShell, GitHub Actions, Python unittest static tests, Markdown docs.

---

## File Structure

- `backend/tests/test_windows_installer_bootstrap_static.py`: extend static installer coverage for per-user install defaults, no admin prompt, Desktop shortcut wiring, and beta output naming.
- `setup.iss`: change installer scope from machine-wide admin install to per-user install and rename the output setup executable for beta distribution.
- `.github/workflows/build.yml`: update artifact naming to match the beta setup filename while keeping the existing upload path.
- `WINDOWS_BUILD.md`: document the no-admin double-click Windows beta setup flow.
- `README.md`: align Quick Start installer wording with the beta per-user path.

## Task 1: Add Failing Static Tests

**Files:**
- Modify: `backend/tests/test_windows_installer_bootstrap_static.py`

- [ ] **Step 1: Add per-user installer assertions**

Insert this test method after `test_inno_installer_launches_wrapper_and_leaves_dependencies_to_first_run`:

```python
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
```

- [ ] **Step 2: Add documentation assertions**

Extend `test_docs_present_first_run_dependency_download_as_beta_path` with these assertions:

```python
        self.assertIn("SentinelPulse-Beta-Setup-", readme)
        self.assertIn("SentinelPulse-Beta-Setup-", windows)
        self.assertIn("does not require admin", windows)
        self.assertIn("Desktop shortcut named Sentinel Pulse", windows)
```

- [ ] **Step 3: Run the focused test and verify it fails**

Run:

```powershell
python -m unittest backend.tests.test_windows_installer_bootstrap_static -v
```

Expected: FAIL on the new per-user installer assertions because `setup.iss` still uses `{autopf}`, `PrivilegesRequired=admin`, `SentinelPulse-Setup`, and common Desktop shortcuts.

- [ ] **Step 4: Commit the failing tests**

Run:

```powershell
git add backend/tests/test_windows_installer_bootstrap_static.py
git commit -m "test: cover per-user beta installer expectations"
```

## Task 2: Update Inno Setup Installer

**Files:**
- Modify: `setup.iss`

- [ ] **Step 1: Change app URL and installer scope**

Replace the current setup constants and setup scope lines with:

```ini
#define MyAppURL "https://github.com/Tetradim/Sentinel-Pulse"
DefaultDirName={localappdata}\Programs\{#MyAppName}
OutputBaseFilename=SentinelPulse-Beta-Setup-{#MyAppVersion}
PrivilegesRequired=lowest
```

Keep the existing `AppSupportURL={#MyAppURL}/issues` and `AppUpdatesURL={#MyAppURL}/releases` lines.

- [ ] **Step 2: Move Desktop shortcuts to user scope**

Replace the current common Desktop icon entries with:

```ini
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\Launch-Sentinel-Pulse.bat"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{userdesktop}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
```

Keep the Start Menu launch shortcut pointing to `Launch-Sentinel-Pulse.bat`.

- [ ] **Step 3: Move uninstall cleanup from common Desktop to user Desktop**

Remove the common Desktop setup-file cleanup entries:

```ini
Type: files; Name: "{commondesktop}\Sentinel-Pulse.log"
Type: files; Name: "{commondesktop}\Sentinel-Pulse-Transcript.log"
Type: files; Name: "{commondesktop}\Sentinel-Pulse-MongoDB.log"
Type: files; Name: "{commondesktop}\sentinel_pulse.log"
Type: files; Name: "{commondesktop}\SentinelPulse-Setup*.exe"
Type: files; Name: "{commondesktop}\Sentinel Pulse-Setup*.exe"
Type: files; Name: "{commondesktop}\Sentinel Pulse Setup*.exe"
```

Add this beta setup cleanup entry beside the existing user Desktop setup cleanup entries:

```ini
Type: files; Name: "{userdesktop}\SentinelPulse-Beta-Setup*.exe"
```

- [ ] **Step 4: Run the focused static test and verify installer assertions pass or docs still fail**

Run:

```powershell
python -m unittest backend.tests.test_windows_installer_bootstrap_static -v
```

Expected: remaining FAIL only on docs assertions added in Task 1 Step 2.

- [ ] **Step 5: Commit installer changes**

Run:

```powershell
git add setup.iss
git commit -m "build: make Windows beta installer per-user"
```

## Task 3: Align CI Artifact Naming

**Files:**
- Modify: `.github/workflows/build.yml`

- [ ] **Step 1: Update artifact display name**

Change the upload artifact name from:

```yaml
name: SentinelPulse-Setup-${{ env.VERSION }}
```

to:

```yaml
name: SentinelPulse-Beta-Setup-${{ env.VERSION }}
```

Keep the uploaded file path as `dist/SentinelPulse-Setup*.exe` only if Inno's generated beta filename is still matched by the wildcard. Prefer this broader pattern to cover both legacy and beta filenames:

```yaml
path: dist/SentinelPulse*Setup*.exe
```

- [ ] **Step 2: Verify the workflow still references setup.iss**

Run:

```powershell
rg -n "setup\\.iss|SentinelPulse-Beta-Setup|SentinelPulse\\*Setup" .github\workflows\build.yml
```

Expected: output includes the Inno Setup action path and the beta artifact name.

- [ ] **Step 3: Commit CI naming**

Run:

```powershell
git add .github/workflows/build.yml
git commit -m "ci: name Windows installer artifact for beta testers"
```

## Task 4: Update Tester-Facing Docs

**Files:**
- Modify: `WINDOWS_BUILD.md`
- Modify: `README.md`

- [ ] **Step 1: Update Windows distribution filename**

In `WINDOWS_BUILD.md`, replace references to:

```text
SentinelPulse-Setup-<version>.exe
```

with:

```text
SentinelPulse-Beta-Setup-<version>.exe
```

- [ ] **Step 2: Add no-admin and Desktop shortcut wording**

In `WINDOWS_BUILD.md`, update the recipient setup section so it includes these exact points:

```markdown
The beta installer is per-user and does not require admin privileges. It installs under the tester's local app data folder, creates a Desktop shortcut named Sentinel Pulse, and creates Start Menu entries.
```

```markdown
1. Run `SentinelPulse-Beta-Setup-<version>.exe`
2. Leave the default install location selected
3. Leave "Launch Sentinel Pulse after install" checked
4. Use the Desktop shortcut named Sentinel Pulse for future launches
```

- [ ] **Step 3: Update README quick start wording**

In `README.md`, update the Windows installer quick-start wording so it says:

```markdown
The Windows beta installer is distributed as `SentinelPulse-Beta-Setup-<version>.exe`. It installs per user, does not require admin privileges, creates a Desktop shortcut named `Sentinel Pulse`, and launches through the first-run dependency bootstrap.
```

- [ ] **Step 4: Run docs assertions**

Run:

```powershell
python -m unittest backend.tests.test_windows_installer_bootstrap_static -v
```

Expected: PASS.

- [ ] **Step 5: Commit docs updates**

Run:

```powershell
git add WINDOWS_BUILD.md README.md
git commit -m "docs: describe double-click Windows beta setup"
```

## Task 5: Final Verification

**Files:**
- Test: `backend/tests/test_windows_installer_bootstrap_static.py`
- Test: `Launch-Sentinel-Pulse.ps1`

- [ ] **Step 1: Run focused installer static tests**

Run:

```powershell
python -m unittest backend.tests.test_windows_installer_bootstrap_static -v
```

Expected: PASS.

- [ ] **Step 2: Run launcher smoke test**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Launch-Sentinel-Pulse.ps1 -SmokeTest
```

Expected: output includes `Launcher smoke test passed`.

- [ ] **Step 3: Inspect final diff**

Run:

```powershell
git diff --stat HEAD~4..HEAD
git status --short
```

Expected: installer, workflow, docs, and static tests changed through commits. Working tree is clean except ignored `docs/superpowers` files if the plan was not force-added.

- [ ] **Step 4: Commit this plan if desired by the implementing agent**

Run:

```powershell
git add -f docs/superpowers/plans/2026-08-10-per-user-windows-beta-installer.md
git commit -m "plan: implement per-user Windows beta installer"
```

Expected: the plan is preserved in git.
