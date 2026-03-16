# BracketBot Windows Build Script
# Run this in PowerShell from the project root directory
# Prerequisites: Python 3.10+, Node.js 18+, MongoDB installed or Atlas URI

param(
    [switch]$SkipFrontend,
    [switch]$SkipBackend,
    [switch]$Clean,
    [string]$MongoUri = "mongodb://localhost:27017"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $ProjectRoot "backend"
$FrontendDir = Join-Path $ProjectRoot "frontend"
$DistDir = Join-Path $ProjectRoot "dist"
$StaticDir = Join-Path $BackendDir "static"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  BracketBot Windows Build" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# --- Clean ---
if ($Clean) {
    Write-Host "[CLEAN] Removing previous build artifacts..." -ForegroundColor Yellow
    if (Test-Path $DistDir) { Remove-Item -Recurse -Force $DistDir }
    if (Test-Path $StaticDir) { Remove-Item -Recurse -Force $StaticDir }
    if (Test-Path (Join-Path $BackendDir "build")) { Remove-Item -Recurse -Force (Join-Path $BackendDir "build") }
}

# --- Step 1: Build Frontend ---
if (-not $SkipFrontend) {
    Write-Host "[1/4] Building React frontend..." -ForegroundColor Green

    Push-Location $FrontendDir

    # Set the backend URL to localhost for desktop mode
    $envFile = Join-Path $FrontendDir ".env.production"
    "REACT_APP_BACKEND_URL=http://localhost:8001" | Out-File -Encoding UTF8 $envFile

    # Install dependencies
    Write-Host "  -> Installing dependencies..." -ForegroundColor Gray
    & yarn install --frozen-lockfile 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [ERROR] yarn install failed" -ForegroundColor Red
        Pop-Location
        exit 1
    }

    # Build
    Write-Host "  -> Building production bundle..." -ForegroundColor Gray
    & yarn build 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [ERROR] yarn build failed. Run 'yarn build' manually to see errors." -ForegroundColor Red
        Pop-Location
        exit 1
    }

    Pop-Location

    # Copy dist to backend/static
    $frontendDist = Join-Path $FrontendDir "dist"
    if (Test-Path $StaticDir) { Remove-Item -Recurse -Force $StaticDir }
    Copy-Item -Recurse $frontendDist $StaticDir
    Write-Host "  -> Frontend built and copied to backend/static/" -ForegroundColor Green
} else {
    Write-Host "[1/4] Skipping frontend build" -ForegroundColor Yellow
}

# --- Step 2: Create Python Virtual Environment ---
if (-not $SkipBackend) {
    Write-Host "[2/4] Setting up Python environment..." -ForegroundColor Green

    Push-Location $BackendDir

    $VenvDir = Join-Path $BackendDir "venv"
    if (-not (Test-Path $VenvDir)) {
        Write-Host "  -> Creating virtual environment..." -ForegroundColor Gray
        & python -m venv venv
    }

    # Activate venv
    $activateScript = Join-Path $VenvDir "Scripts" "Activate.ps1"
    & $activateScript

    # Install dependencies
    Write-Host "  -> Installing Python dependencies..." -ForegroundColor Gray
    & pip install -r requirements.txt --quiet 2>&1 | Out-Null
    & pip install pyinstaller --quiet 2>&1 | Out-Null

    Pop-Location
    Write-Host "  -> Python environment ready" -ForegroundColor Green
} else {
    Write-Host "[2/4] Skipping Python setup" -ForegroundColor Yellow
}

# --- Step 3: Create .env for desktop mode ---
Write-Host "[3/4] Creating desktop configuration..." -ForegroundColor Green

$envContent = @"
MONGO_URL=$MongoUri
DB_NAME=bracketbot
CORS_ORIGINS=http://localhost:8001,http://127.0.0.1:8001
"@

$desktopEnv = Join-Path $BackendDir ".env"
$envContent | Out-File -Encoding UTF8 $desktopEnv
Write-Host "  -> .env configured (MongoDB: $MongoUri)" -ForegroundColor Green

# --- Step 4: Build Executable with PyInstaller ---
if (-not $SkipBackend) {
    Write-Host "[4/4] Building Windows executable with PyInstaller..." -ForegroundColor Green

    Push-Location $BackendDir

    $activateScript = Join-Path $BackendDir "venv" "Scripts" "Activate.ps1"
    & $activateScript

    # PyInstaller command
    & pyinstaller `
        --name "BracketBot" `
        --onedir `
        --noconsole `
        --icon "NONE" `
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
        --collect-all "yfinance" `
        --collect-all "certifi" `
        server.py 2>&1

    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [ERROR] PyInstaller build failed" -ForegroundColor Red
        Pop-Location
        exit 1
    }

    Pop-Location

    # Move output to dist/
    $pyinstallerDist = Join-Path $BackendDir "dist" "BracketBot"
    if (-not (Test-Path $DistDir)) { New-Item -ItemType Directory -Path $DistDir | Out-Null }
    if (Test-Path (Join-Path $DistDir "BracketBot")) { Remove-Item -Recurse -Force (Join-Path $DistDir "BracketBot") }
    Move-Item $pyinstallerDist $DistDir

    Write-Host "  -> Executable built at dist/BracketBot/BracketBot.exe" -ForegroundColor Green
} else {
    Write-Host "[4/4] Skipping executable build" -ForegroundColor Yellow
}

# --- Create launcher batch file ---
$launcherContent = @"
@echo off
title BracketBot Terminal v3.0
echo.
echo  ========================================
echo    BracketBot Terminal v3.0
echo    Starting trading engine...
echo  ========================================
echo.
echo  Opening browser at http://localhost:8001
echo  Press Ctrl+C to stop the bot.
echo.
timeout /t 2 /nobreak > nul
start http://localhost:8001
cd /d "%~dp0BracketBot"
BracketBot.exe
"@

$launcherPath = Join-Path $DistDir "Start BracketBot.bat"
$launcherContent | Out-File -Encoding ASCII $launcherPath

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  BUILD COMPLETE!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Output: $DistDir" -ForegroundColor White
Write-Host ""
Write-Host "  To run:" -ForegroundColor White
Write-Host "    1. Ensure MongoDB is running (localhost:27017)" -ForegroundColor Gray
Write-Host "       OR set MONGO_URL in dist/BracketBot/.env" -ForegroundColor Gray
Write-Host "    2. Double-click 'Start BracketBot.bat'" -ForegroundColor Gray
Write-Host "    3. Browser opens to http://localhost:8001" -ForegroundColor Gray
Write-Host ""
Write-Host "  To distribute:" -ForegroundColor White
Write-Host "    Zip the dist/ folder and share it." -ForegroundColor Gray
Write-Host "    Recipients need MongoDB installed or an Atlas URI." -ForegroundColor Gray
Write-Host ""
