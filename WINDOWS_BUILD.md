# BracketBot Windows Build & Run Guide

## Quick Start (From Source)

### Prerequisites
- **Python 3.10+** — [python.org](https://www.python.org/downloads/)
- **Node.js 18+** — [nodejs.org](https://nodejs.org/)
- **Yarn** — `npm install -g yarn`
- **MongoDB 7+** — [mongodb.com/try/download](https://www.mongodb.com/try/download/community)
  - OR a MongoDB Atlas URI (free tier works)

### Run
Double-click `start-bracketbot.bat` or run in terminal:
```cmd
start-bracketbot.bat
```
This will:
1. Install Python & Node dependencies
2. Start the FastAPI backend on port 8001
3. Start the React dev server on port 3000
4. Open your browser

---

## Build Standalone Executable

### Prerequisites
Same as above, plus:
- **PowerShell 5.1+** (included in Windows 10/11)

### Build
Open PowerShell and run:
```powershell
.\build-windows.ps1
```

#### Build Options
```powershell
# Full build (default)
.\build-windows.ps1

# Clean build (remove previous artifacts first)
.\build-windows.ps1 -Clean

# Custom MongoDB URI (e.g., Atlas)
.\build-windows.ps1 -MongoUri "mongodb+srv://user:pass@cluster.mongodb.net/bracketbot"

# Skip frontend rebuild (if already built)
.\build-windows.ps1 -SkipFrontend

# Skip backend/exe rebuild
.\build-windows.ps1 -SkipBackend
```

### Output
```
dist/
├── Start BracketBot.bat    ← Double-click to launch
└── BracketBot/
    ├── BracketBot.exe      ← The standalone executable
    ├── static/             ← Built React frontend
    ├── .env                ← MongoDB config
    └── (runtime files)
```

### Run the Built Executable
1. Ensure MongoDB is running locally (`mongod`) or edit `.env` with your Atlas URI
2. Double-click `dist/Start BracketBot.bat`
3. Browser opens to `http://localhost:8001`

---

## Distributing to Others

### What to share
Zip the entire `dist/` folder.

### What recipients need
- **MongoDB** installed locally, OR
- Edit `dist/BracketBot/.env` and set `MONGO_URL` to a MongoDB Atlas URI
- No Python or Node.js installation required!

---

## Configuration

### MongoDB
Edit `backend/.env` (source mode) or `dist/BracketBot/.env` (packaged mode):
```env
MONGO_URL=mongodb://localhost:27017
DB_NAME=bracketbot
```

For MongoDB Atlas:
```env
MONGO_URL=mongodb+srv://username:password@cluster.mongodb.net/bracketbot
DB_NAME=bracketbot
```

### Telegram Bot (Optional)
Configure in the app's Settings tab — no file editing needed.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| "MongoDB connection failed" | Ensure `mongod` is running or check your Atlas URI |
| "Port 8001 already in use" | Kill any existing BracketBot process: `taskkill /f /im BracketBot.exe` |
| PowerShell script blocked | Run: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| PyInstaller build fails | Ensure you're in the venv: `backend\venv\Scripts\Activate.ps1` |
| Frontend build fails | Delete `frontend\node_modules` and re-run `yarn install` |
| White screen in packaged mode | Check `dist/BracketBot/static/` has `index.html` and `assets/` |

---

## Architecture (Packaged Mode)

```
BracketBot.exe
    ├── FastAPI server (port 8001)
    │   ├── /api/* endpoints
    │   ├── /ws WebSocket
    │   └── /* serves static React frontend
    └── Connects to MongoDB (configurable via .env)
```

In packaged mode, the React frontend is built into static files and served directly by the FastAPI backend — no separate Node.js process needed.
