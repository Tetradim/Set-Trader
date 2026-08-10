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
CORS_ORIGINS=http://localhost:8002,http://127.0.0.1:8002
"@
$envContent | Out-File -Encoding UTF8 (Join-Path $BACKEND ".env")
Write-Host "  .env created with MONGO_URL=$MongoUri" -ForegroundColor Green

# --- PYINSTALLER BUILD ---
if (-not $SkipBackend) {
    Write-Host "[5/6] Building executable with PyInstaller..." -ForegroundColor Yellow
    Push-Location $BACKEND
    pyinstaller sentinel_win.spec
    Pop-Location
    Write-Host "  Executable built." -ForegroundColor Green
} else {
    Write-Host "[5/6] Skipping backend build (--SkipBackend)" -ForegroundColor DarkGray
}

# --- PACKAGE LAUNCHERS ---
Write-Host "[6/6] Packaging first-run launcher..." -ForegroundColor Yellow
$PACKAGE = Join-Path $DIST "SentinelPulse"
if (-not (Test-Path $PACKAGE)) {
    throw "Expected PyInstaller output at $PACKAGE"
}

$launcherFiles = @(
    "Launch-Sentinel-Pulse.bat",
    "Launch-Sentinel-Pulse.ps1",
    "Setup-And-Launch.bat"
)
foreach ($file in $launcherFiles) {
    Copy-Item -Path (Join-Path $ROOT $file) -Destination (Join-Path $PACKAGE $file) -Force
}

$compatLauncher = @"
@echo off
call "%~dp0Launch-Sentinel-Pulse.bat"
"@
$compatLauncher | Out-File -Encoding ASCII (Join-Path $PACKAGE "Start Sentinel Pulse.bat")

# --- ALSO COPY .ENV TO PACKAGE ---
Copy-Item (Join-Path $BACKEND ".env") (Join-Path $PACKAGE ".env") -Force

Write-Host ""
Write-Host "  ========================================" -ForegroundColor Green
Write-Host "    BUILD COMPLETE!" -ForegroundColor Green
Write-Host "  ========================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Output: backend\dist\SentinelPulse\" -ForegroundColor Cyan
Write-Host "    - Launch-Sentinel-Pulse.bat  (double-click to launch and repair dependencies)" -ForegroundColor White
Write-Host "    - SentinelPulse.exe          (packaged backend/frontend app)" -ForegroundColor White
Write-Host ""
Write-Host "  To distribute:" -ForegroundColor Yellow
Write-Host "    1. Build the installer with setup.iss or zip backend\dist\SentinelPulse" -ForegroundColor White
Write-Host "    2. Share SentinelPulse-Beta-Setup-<version>.exe with beta testers" -ForegroundColor White
Write-Host "    3. First launch downloads missing runtime dependencies automatically" -ForegroundColor White
Write-Host ""
