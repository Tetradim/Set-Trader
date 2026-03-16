@echo off
title BracketBot - Desktop Launcher
echo.
echo  ========================================
echo    BracketBot Terminal v3.0
echo  ========================================
echo.

:: Check if running from dist or source
if exist "%~dp0dist\BracketBot\BracketBot.exe" (
    echo  [MODE] Running packaged executable
    echo  Opening http://localhost:8001 in 2 seconds...
    timeout /t 2 /nobreak > nul
    start http://localhost:8001
    cd /d "%~dp0dist\BracketBot"
    BracketBot.exe
    goto :end
)

:: Source mode - run with Python directly
echo  [MODE] Running from source
echo.

:: Check Python
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo  [ERROR] Python not found. Install Python 3.10+ from python.org
    pause
    exit /b 1
)

:: Check Node
where node >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo  [ERROR] Node.js not found. Install Node.js 18+ from nodejs.org
    pause
    exit /b 1
)

:: Create .env if missing
if not exist "%~dp0backend\.env" (
    echo MONGO_URL=mongodb://localhost:27017> "%~dp0backend\.env"
    echo DB_NAME=bracketbot>> "%~dp0backend\.env"
    echo CORS_ORIGINS=http://localhost:8001,http://localhost:3000>> "%~dp0backend\.env"
    echo  [INFO] Created backend\.env with default MongoDB settings
)

:: Install backend deps
echo  [1/3] Installing Python dependencies...
cd /d "%~dp0backend"
pip install -r requirements.txt --quiet 2>nul

:: Install frontend deps
echo  [2/3] Installing frontend dependencies...
cd /d "%~dp0frontend"
call yarn install --frozen-lockfile 2>nul

:: Start backend in background
echo  [3/3] Starting services...
cd /d "%~dp0backend"
start /b "BracketBot-Backend" python -m uvicorn server:app --host 0.0.0.0 --port 8001

:: Start frontend
cd /d "%~dp0frontend"
echo.
echo  Backend: http://localhost:8001/api/health
echo  Frontend: http://localhost:3000
echo.
echo  Opening browser...
timeout /t 3 /nobreak > nul
start http://localhost:3000

call yarn start

:end
echo.
echo  BracketBot stopped.
pause
