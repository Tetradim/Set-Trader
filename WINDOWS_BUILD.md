# BracketBot Windows Build & Distribution Guide

## Overview

BracketBot can be packaged into a standalone Windows executable that bundles:
- The Python/FastAPI backend
- The React frontend (pre-built static files)
- All dependencies

Recipients only need **MongoDB** (local install or Atlas cloud URI) — no Python, Node.js, or developer tools.

---

## Option 1: Automated Build via GitHub Actions (Recommended)

The easiest way to build the executable is through the GitHub Actions workflow.

### Trigger a Build

1. Push your code to GitHub
2. Go to **Actions** > **Build Windows Executable**
3. Click **Run workflow**
4. Optionally set a custom MongoDB URI (defaults to `mongodb://localhost:27017`)
5. Wait ~10 minutes for the build to complete
6. Download **BracketBot-Windows.zip** from the workflow artifacts

### Auto-Release on Tag

Push a version tag to automatically create a GitHub Release with the `.zip`:

```bash
git tag v1.0.0
git push origin v1.0.0
```

The release will include `BracketBot-Windows.zip` as a downloadable asset.

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
git clone <your-repo-url> BracketBot
cd BracketBot

# Run the build script
.\build-windows.ps1

# With a custom MongoDB URI:
.\build-windows.ps1 -MongoUri "mongodb+srv://user:pass@cluster.mongodb.net/bracketbot"

# Clean build (removes old artifacts first):
.\build-windows.ps1 -Clean
```

### Build Output

```
backend/dist/
  Start BracketBot.bat     <-- Double-click to launch
  BracketBot/
    BracketBot.exe         <-- The executable
    static/                <-- Frontend files
    .env                   <-- Configuration
    ...                    <-- Bundled dependencies
```

---

## Distribution

### What to Send

Zip the entire `backend/dist/` folder and share the `.zip` file.

### What Recipients Need

1. **MongoDB** — Either:
   - Install [MongoDB Community Edition](https://www.mongodb.com/try/download/community) and run `mongod`
   - OR use a [MongoDB Atlas](https://cloud.mongodb.com) cloud cluster (free tier available)

2. **That's it.** No Python, Node.js, or any other developer tools needed.

### Setup for Recipients

1. Unzip `BracketBot-Windows.zip`
2. **If using Atlas:** Edit `BracketBot\.env` and set:
   ```
   MONGO_URL=mongodb+srv://username:password@cluster.mongodb.net/bracketbot
   ```
3. Double-click `Start BracketBot.bat`
4. Browser opens to `http://localhost:8001`

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
  |     BracketBot.exe         |
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
| `DB_NAME` | `bracketbot` | Database name |
| `CORS_ORIGINS` | `http://localhost:8001` | Allowed CORS origins |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| App won't start | Make sure MongoDB is running (`mongod`) |
| Port 8001 in use | Close whatever's using port 8001, or edit server.py's port |
| "Module not found" errors | Re-build with `.\build-windows.ps1 -Clean` |
| Frontend shows blank page | Make sure `static/` folder exists inside `BracketBot/` |
| Can't connect to Atlas | Check your Atlas URI, whitelist your IP in Atlas |
| Windows Defender blocks exe | Click "More info" > "Run anyway" (or add an exception) |

---

## Development Mode

For development without building an executable:

```bash
# Windows
start-bracketbot.bat

# Or manually:
# Terminal 1: Backend
cd backend
python -m uvicorn server:app --host 0.0.0.0 --port 8001 --reload

# Terminal 2: Frontend
cd frontend
set REACT_APP_BACKEND_URL=http://localhost:8001
yarn dev --port 3000
```
