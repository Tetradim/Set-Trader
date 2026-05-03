<#
.SYNOPSIS
    Build Sentinel Pulse into a standalone Windows executable.
.DESCRIPTION
    This script:
    1. Creates/activates a Python virtual environment
    2. Installs Python dependencies
    3. Builds the React frontend
    4. Copies the built frontend into backend/static
    5. Packages everything into a single .exe via PyInstaller
    6. Creates a launcher batch file
.PARAMETER Clean
    Remove previous build artifacts before building.
.PARAMETER MongoUri
    Custom MongoDB URI (default: mongodb://localhost:27017).
.PARAMETER SkipFrontend
    Skip the frontend build step (use existing backend/static).
.PARAMETER SkipBackend
    Skip the backend/exe build step.
.EXAMPLE
    .\build-windows.ps1
    .\build-windows.ps1 -Clean
    .\build-windows.ps1 -MongoUri "mongodb+srv://user:pass@cluster.mongodb.net/sentinel_pulse"
#>

param(
    [switch]$Clean,
    [string]$MongoUri = "mongodb://localhost:27017",
    [switch]$SkipFrontend,
    [switch]$SkipBackend
)

$ErrorActionPreference = "Stop"
$ROOT = $PSScriptRoot
$BACKEND = Join-Path $ROOT "backend"
$FRONTEND = Join-Path $ROOT "frontend"
$STATIC = Join-Path $BACKEND "static"
$DIST = Join-Path $BACKEND "dist"

Write-Host ""
Write-Host "  ========================================" -ForegroundColor Cyan
Write-Host "    Sentinel Pulse Windows Build" -ForegroundColor Cyan
Write-Host "  ========================================" -ForegroundColor Cyan
Write-Host ""

# --- CLEAN ---
if ($Clean) {
    Write-Host "[1/6] Cleaning previous build..." -ForegroundColor Yellow
    if (Test-Path $STATIC) { Remove-Item -Recurse -Force $STATIC }
    if (Test-Path $DIST) { Remove-Item -Recurse -Force $DIST }
    if (Test-Path (Join-Path $BACKEND "build")) { Remove-Item -Recurse -Force (Join-Path $BACKEND "build") }
    Write-Host "  Cleaned." -ForegroundColor Green
} else {
    Write-Host "[1/6] Skipping clean (use -Clean flag to remove old builds)" -ForegroundColor DarkGray
}

# --- PYTHON VENV ---
Write-Host "[2/6] Setting up Python environment..." -ForegroundColor Yellow
$venvPath = Join-Path $BACKEND "venv"
if (-not (Test-Path $venvPath)) {
    Write-Host "  Creating virtual environment..." -ForegroundColor DarkGray
    python -m venv $venvPath
}
& "$venvPath\Scripts\Activate.ps1"
Write-Host "  Installing Python dependencies..." -ForegroundColor DarkGray
pip install -q -r (Join-Path $BACKEND "requirements.txt")
pip install -q pyinstaller
Write-Host "  Python ready." -ForegroundColor Green

# --- FRONTEND BUILD ---
if (-not $SkipFrontend) {
    Write-Host "[3/6] Building React frontend..." -ForegroundColor Yellow
    Push-Location $FRONTEND
    if (-not (Test-Path "node_modules")) {
        Write-Host "  Installing Node dependencies..." -ForegroundColor DarkGray
        yarn install
    }
    $env:REACT_APP_BACKEND_URL = ""
    yarn build
    Pop-Location

    # Copy to backend/static
    if (Test-Path $STATIC) { Remove-Item -Recurse -Force $STATIC }
    Copy-Item -Recurse (Join-Path $FRONTEND "dist") $STATIC
    Write-Host "  Frontend built and copied to backend/static." -ForegroundColor Green
} else {
    Write-Host "[3/6] Skipping frontend build (--SkipFrontend)" -ForegroundColor DarkGray
    if (-not (Test-Path $STATIC)) {
        Write-Host "  WARNING: backend/static does not exist!" -ForegroundColor Red
    }
}

# --- CREATE .ENV ---
Write-Host "[4/6] Creating production .env..." -ForegroundColor Yellow
$envContent = @"
MONGO_URL=$MongoUri
DB_NAME=sentinel_pulse
CORS_ORIGINS=http://localhost:8001,http://127.0.0.1:8001
"@
$envContent | Out-File -Encoding UTF8 (Join-Path $BACKEND ".env")
Write-Host "  .env created with MONGO_URL=$MongoUri" -ForegroundColor Green

# --- PYINSTALLER BUILD ---
if (-not $SkipBackend) {
    Write-Host "[5/6] Building executable with PyInstaller..." -ForegroundColor Yellow
    Push-Location $BACKEND
    pyinstaller `
        --name "Sentinel Pulse" `
        --onedir `
        --noconsole `
        --add-data "static;static" `
        --add-data ".env;." `
        --hidden-import "uvicorn.logging" `
        --hidden-import "uvicorn.loops" `
        --hidden-import "uvicorn.loops.auto" `
        --hidden-import "uvicorn.protocols" `
        --hidden-import "uvicorn.protocols.http" `
        --hidden-import "uvicorn.protocols.http.auto" `
        --hidden-import "uvicorn.protocols.websockets" `
        --hidden-import "uvicorn.protocols.websockets.auto" `
        --hidden-import "uvicorn.lifespan" `
        --hidden-import "uvicorn.lifespan.on" `
        --hidden-import "motor" `
        --hidden-import "motor.motor_asyncio" `
        --hidden-import "pymongo" `
        --hidden-import "dns.resolver" `
        --hidden-import "yfinance" `
        --hidden-import "telegram" `
        --hidden-import "telegram.ext" `
        --collect-all "yfinance" `
        --collect-all "certifi" `
        --noconfirm `
        server.py
    Pop-Location
    Write-Host "  Executable built." -ForegroundColor Green
} else {
    Write-Host "[5/6] Skipping backend build (--SkipBackend)" -ForegroundColor DarkGray
}

# --- CREATE LAUNCHER ---
Write-Host "[6/6] Creating launcher..." -ForegroundColor Yellow
$launcher = @"
@echo off
title Sentinel Pulse Terminal
echo.
echo  ========================================
echo    Sentinel Pulse Terminal
echo  ========================================
echo.
echo  Starting Sentinel Pulse...
echo  Browser will open at http://localhost:8001
echo.
echo  Prerequisites:
echo    - MongoDB running locally (mongod)
echo    - OR edit Sentinel Pulse\.env with your Atlas URI
echo.
echo  Press Ctrl+C to stop.
echo.
timeout /t 2 /nobreak > nul
start http://localhost:8001
cd /d "%~dp0Sentinel Pulse"
Sentinel Pulse.exe
"@
$launcher | Out-File -Encoding ASCII (Join-Path $DIST "Start Sentinel Pulse.bat")

# --- ALSO COPY .ENV TO DIST ---
Copy-Item (Join-Path $BACKEND ".env") (Join-Path $DIST "Sentinel Pulse\.env") -Force

Write-Host ""
Write-Host "  ========================================" -ForegroundColor Green
Write-Host "    BUILD COMPLETE!" -ForegroundColor Green
Write-Host "  ========================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Output: backend\dist\" -ForegroundColor Cyan
Write-Host "    - Start Sentinel Pulse.bat  (double-click to launch)" -ForegroundColor White
Write-Host "    - Sentinel Pulse\           (executable + static files)" -ForegroundColor White
Write-Host ""
Write-Host "  To distribute:" -ForegroundColor Yellow
Write-Host "    1. Zip the entire 'dist' folder" -ForegroundColor White
Write-Host "    2. Share the zip file" -ForegroundColor White
Write-Host "    3. Recipients need MongoDB installed (or set Atlas URI in .env)" -ForegroundColor White
Write-Host ""
