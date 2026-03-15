# Bracket Bot - Desktop Build Guide

## Quick Build (Windows)

Double-click `build-windows.bat` or run:
```cmd
build-windows.bat
```

## Quick Build (macOS/Linux)

```bash
chmod +x build.sh
./build.sh
```

## Manual Build Steps

### 1. Build Python Backend

```bash
cd backend
pip install -r requirements.txt pyinstaller
pyinstaller --onefile --name bracket-bot-server main.py
```

Output: `backend/dist/bracket-bot-server.exe`

### 2. Build React Frontend

```bash
cd frontend
npm install
npm run build
```

Output: `frontend/dist/`

### 3. Build Electron Desktop App

```bash
cd desktop
npm install
npm run dist:win    # Windows
npm run dist:mac    # macOS
npm run dist:linux  # Linux
```

Output: `desktop/dist/`

## GitHub Actions (Automated)

Push a tag to trigger automatic builds:
```bash
git tag v3.0.0
git push origin v3.0.0
```

This will:
1. Build Windows installer (`.exe`)
2. Build Windows portable (`.exe`)
3. Build macOS DMG (`.dmg`)
4. Create GitHub Release with all artifacts

## Output Files

| Platform | Type | File |
|----------|------|------|
| Windows | Installer | `Bracket Bot Setup 3.0.0.exe` |
| Windows | Portable | `Bracket Bot 3.0.0 portable.exe` |
| macOS | DMG | `Bracket Bot-3.0.0.dmg` |
| Linux | AppImage | `Bracket-Bot-3.0.0.AppImage` |

## Requirements

- **Python 3.11+** with pip
- **Node.js 20+** with npm
- **Windows**: Visual Studio Build Tools (for native modules)
- **macOS**: Xcode Command Line Tools

## Icon Generation

To generate platform-specific icons from the SVG:

```bash
# Install icon converter
npm install -g icon-gen

# Generate all formats
icon-gen -i assets/icon.svg -o assets --ico --icns --favicon
```

Or use online tools:
- https://icoconvert.com/ (ICO for Windows)
- https://cloudconvert.com/svg-to-icns (ICNS for macOS)

## Troubleshooting

### PyInstaller fails with missing modules
Add to `hiddenimports` in `bracket-bot-server.spec`:
```python
hiddenimports=['missing_module_name']
```

### Electron build fails
Clear cache and reinstall:
```bash
rm -rf node_modules desktop/node_modules
npm install
cd desktop && npm install
```

### Backend doesn't start in packaged app
Check the console output. Common issues:
- Missing dependencies in PyInstaller bundle
- Wrong path to executable
- Firewall blocking port 8000

## Development Mode

Run all components separately for development:

```bash
# Terminal 1 - Backend
cd backend
uvicorn main:app --reload

# Terminal 2 - Frontend
cd frontend
npm run dev

# Terminal 3 - Desktop (optional, uses browser otherwise)
cd desktop
npm run dev
```
