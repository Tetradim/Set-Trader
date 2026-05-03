@echo off
title Sentinel Pulse Terminal (Dev Mode)
echo.
echo  ========================================
echo    Sentinel Pulse Terminal - Dev Mode
echo  ========================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python not found. Install from https://python.org
    pause
    exit /b 1
)

:: Check Node
node --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Node.js not found. Install from https://nodejs.org
    pause
    exit /b 1
)

:: Check Yarn
yarn --version >nul 2>&1
if errorlevel 1 (
    echo  Installing Yarn...
    npm install -g yarn
)

:: Install backend deps
echo  [1/4] Installing Python dependencies...
cd /d "%~dp0backend"
if not exist "venv" (
    python -m venv venv
)
call venv\Scripts\activate.bat
pip install -q -r requirements.txt

:: Install frontend deps
echo  [2/4] Installing Node dependencies...
cd /d "%~dp0frontend"
if not exist "node_modules" (
    yarn install
)

:: Start backend
echo  [3/4] Starting backend (port 8001)...
cd /d "%~dp0backend"
start /b cmd /c "call venv\Scripts\activate.bat && python -m uvicorn server:app --host 0.0.0.0 --port 8001 --reload"

:: Start frontend
echo  [4/4] Starting frontend (port 3000)...
cd /d "%~dp0frontend"
set REACT_APP_BACKEND_URL=http://localhost:8001
start /b cmd /c "yarn dev --port 3000 --host 0.0.0.0"

:: Wait and open browser
timeout /t 5 /nobreak > nul
start http://localhost:3000

echo.
echo  ========================================
echo    Sentinel Pulse is running!
echo  ========================================
echo.
echo  Frontend: http://localhost:3000
echo  Backend:  http://localhost:8001
echo.
echo  Press any key to stop all services...
pause > nul

:: Cleanup
taskkill /f /im python.exe /fi "WINDOWTITLE eq *uvicorn*" >nul 2>&1
taskkill /f /im node.exe >nul 2>&1
echo  Stopped.
