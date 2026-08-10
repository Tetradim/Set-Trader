# Sentinel Pulse Windows Build & Distribution Guide

## Overview

Sentinel Pulse can be packaged into a Windows installer that bundles the app and installs a first-run launcher. Beta testers install one `SentinelPulse-Beta-Setup-<version>.exe`, then launch Sentinel Pulse from the Desktop or Start Menu.

The installed launcher:
- Starts the packaged Python/FastAPI backend
- Serves the pre-built React frontend
- First run downloads missing runtime dependencies
- Caches downloaded dependencies under `%LOCALAPPDATA%\Sentinel Pulse\dependencies`
- Starts MongoDB automatically when it is not already running

Recipients do not need Python, Node.js, Git, MongoDB setup steps, or developer tools.

---

## Option 1: Automated Build via GitHub Actions (Recommended)

The easiest way to build the executable is through the GitHub Actions workflow.

### Trigger a Build

1. Push your code to GitHub
2. Go to **Actions** > **Build Windows Executable**
3. Click **Run workflow**
4. Optionally set a custom MongoDB URI (defaults to `mongodb://localhost:27017`)
5. Wait ~10 minutes for the build to complete
6. Download **Sentinel Pulse-Windows.zip** from the workflow artifacts

### Auto-Release on Tag

Push a version tag to automatically create a GitHub Release with the `.zip`:

```bash
git tag v1.0.0
git push origin v1.0.0
```

The release will include `Sentinel Pulse-Windows.zip` as a downloadable asset.

---

## Option 2: Local Build (PowerShell)

### Prerequisites

- Windows 10/11
- Python 3.11+ (`python --version`)
- Node.js 18+ (`node --version`)
- Yarn (`yarn --version`)

### Build Steps

```powershell
# Clone and enter the repo
git clone <your-repo-url> Sentinel Pulse
cd Sentinel Pulse

# Run the build script
.\build-windows.ps1

# With a custom MongoDB URI:
.\build-windows.ps1 -MongoUri "mongodb+srv://user:pass@cluster.mongodb.net/sentinel_pulse"

# Clean build (removes old artifacts first):
.\build-windows.ps1 -Clean
```

### Build Output

```
backend/dist/
  SentinelPulse/
    Launch-Sentinel-Pulse.bat  <-- First-run launcher; downloads missing runtime dependencies
    Launch-Sentinel-Pulse.ps1  <-- PowerShell launcher used by the batch file
    Start Sentinel Pulse.bat   <-- Compatibility launcher
    SentinelPulse.exe          <-- Packaged backend/frontend app
    static/                    <-- Frontend files
    .env                       <-- Configuration
    ...                        <-- Packaged app files; runtime dependencies download on first launch
```

---

## Distribution

### What to Send

Share the generated installer:

```text
dist/SentinelPulse-Beta-Setup-<version>.exe
```

### What Recipients Need

- Windows 10/11
- Internet access on first launch if MongoDB or the Microsoft Visual C++ Runtime is missing

### Setup for Recipients

The beta installer is per-user and does not require admin privileges. It installs under the tester's local app data folder, creates a Desktop shortcut named Sentinel Pulse, and creates Start Menu entries.

1. Run `SentinelPulse-Beta-Setup-<version>.exe`
2. Leave the default install location selected
3. Leave "Launch Sentinel Pulse after install" checked
4. Wait while the first-run bootstrap completes and the dashboard opens
5. Use the Desktop shortcut named Sentinel Pulse for future launches

The first run downloads missing runtime dependencies and reuses them on future launches.

---

## Architecture in Desktop Mode

When running as a standalone executable:

```
  User's Browser
       |
       v
  http://localhost:8001
       |
       v
  +----------------------------+
  |     SentinelPulse.exe          |
  |                            |
  |  FastAPI (port 8001)       |
  |    ├── /api/*  REST + WS   |
  |    ├── /       index.html  |
  |    └── /*      SPA routes  |
  |                            |
  |  static/                   |
  |    └── React frontend      |
  +----------------------------+
       |
       v
  MongoDB (local or Atlas)
```

- The FastAPI server serves both the API and the static frontend files from the same port
- No separate frontend server needed
- WebSocket connects to `ws://localhost:8001/api/ws`
- All API calls go to `http://localhost:8001/api/*`

---

## Configuration (.env)

| Variable | Default | Description |
|----------|---------|-------------|
| `MONGO_URL` | `mongodb://localhost:27017` | MongoDB connection string |
| `DB_NAME` | `sentinel_pulse` | Database name |
| `CORS_ORIGINS` | `http://localhost:8001` | Allowed CORS origins |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| First launch says a dependency download failed | Check internet access, then send `Sentinel-Pulse.log` and `Sentinel-Pulse-Transcript.log` from the Desktop to support |
| MongoDB does not start | Re-run the Sentinel Pulse shortcut; the launcher reuses or repairs the cached MongoDB runtime |
| Port 8001 in use | Close whatever's using port 8001, or edit server.py's port |
| "Module not found" errors | Re-build with `.\build-windows.ps1 -Clean` |
| Frontend shows blank page | Make sure `static/` folder exists inside `SentinelPulse/` |
| Can't connect to Atlas | Check your Atlas URI, whitelist your IP in Atlas |
| Windows Defender blocks exe | Click "More info" > "Run anyway" (or add an exception) |

---

## Development Mode

For development without building an executable:

```bash
# Windows
start-sentinel_pulse.bat

# Or manually:
# Terminal 1: Backend
cd backend
python -m uvicorn server:app --host 0.0.0.0 --port 8001 --reload

# Terminal 2: Frontend
cd frontend
set REACT_APP_BACKEND_URL=http://localhost:8001
yarn dev --port 3000
```
