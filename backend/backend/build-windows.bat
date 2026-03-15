@echo off
REM ══════════════════════════════════════════════════════════════════════
REM Bracket Bot - Windows Build Script
REM Run this from the bracket-bot directory
REM ══════════════════════════════════════════════════════════════════════

setlocal enabledelayedexpansion

echo.
echo  ____                 _        _     ____        _   
echo ^| __ ) _ __ __ _  ___^| ^| _____^| ^|_  ^| __ )  ___ ^| ^|_ 
echo ^|  _ \^| '__/ _` ^|/ __^| ^|/ / _ \ __^| ^|  _ \ / _ \^| __^|
echo ^| ^|_) ^| ^| ^| (_^| ^| (__^|   ^<  __/ ^|_  ^| ^|_) ^| (_) ^| ^|_ 
echo ^|____/^|_^|  \__,_^|\___^|_^|\_\___^|\__^| ^|____/ \___/ \__^|
echo.
echo  Windows Build Script v3.0
echo ══════════════════════════════════════════════════════════════════════
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found!
    echo Please install Python 3.11+ from https://python.org
    exit /b 1
)
echo [OK] Python found

REM Check Node
node --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found!
    echo Please install Node.js 20+ from https://nodejs.org
    exit /b 1
)
echo [OK] Node.js found

echo.
echo ──────────────────────────────────────────────────────────────────────
echo [1/6] Installing Python dependencies...
echo ──────────────────────────────────────────────────────────────────────
cd backend
pip install -r requirements.txt --quiet
pip install pyinstaller --quiet
if errorlevel 1 (
    echo [ERROR] Failed to install Python dependencies
    exit /b 1
)
echo [OK] Python dependencies installed

echo.
echo ──────────────────────────────────────────────────────────────────────
echo [2/6] Building Python backend...
echo ──────────────────────────────────────────────────────────────────────
pyinstaller --onefile --name bracket-bot-server --clean --noconfirm main.py
if errorlevel 1 (
    echo [ERROR] Failed to build Python backend
    exit /b 1
)
echo [OK] Backend built: dist\bracket-bot-server.exe
cd ..

echo.
echo ──────────────────────────────────────────────────────────────────────
echo [3/6] Installing frontend dependencies...
echo ──────────────────────────────────────────────────────────────────────
cd frontend
call npm install --silent
if errorlevel 1 (
    echo [ERROR] Failed to install frontend dependencies
    exit /b 1
)
echo [OK] Frontend dependencies installed

echo.
echo ──────────────────────────────────────────────────────────────────────
echo [4/6] Building frontend...
echo ──────────────────────────────────────────────────────────────────────
call npm run build
if errorlevel 1 (
    echo [ERROR] Failed to build frontend
    exit /b 1
)
echo [OK] Frontend built
cd ..

echo.
echo ──────────────────────────────────────────────────────────────────────
echo [5/6] Preparing desktop resources...
echo ──────────────────────────────────────────────────────────────────────
cd desktop
call npm install --silent

REM Create resources directories
if not exist resources\backend mkdir resources\backend
if not exist resources\frontend mkdir resources\frontend

REM Copy backend
copy /Y ..\backend\dist\bracket-bot-server.exe resources\backend\ >nul
echo [OK] Backend copied to resources

REM Copy frontend
xcopy /E /I /Y ..\frontend\dist resources\frontend >nul
echo [OK] Frontend copied to resources

echo.
echo ──────────────────────────────────────────────────────────────────────
echo [6/6] Building Windows executable...
echo ──────────────────────────────────────────────────────────────────────
call npm run dist:win
if errorlevel 1 (
    echo [ERROR] Failed to build Electron app
    exit /b 1
)
cd ..

echo.
echo ══════════════════════════════════════════════════════════════════════
echo  BUILD COMPLETE!
echo ══════════════════════════════════════════════════════════════════════
echo.
echo  Output files in: desktop\dist\
echo.
dir /B desktop\dist\*.exe 2>nul
echo.
echo  To install: Run "Bracket Bot Setup *.exe"
echo  Portable:   Run "Bracket Bot *portable*.exe" directly
echo.
echo ══════════════════════════════════════════════════════════════════════

pause
