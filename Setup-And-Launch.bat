@echo off
title Sentinel Pulse - Auto Setup
echo.
echo  ========================================
echo    Sentinel Pulse - Auto Setup ^& Launch
echo  ========================================
echo.

set DEMO_MODE=
echo Checking for MongoDB...

:: Method 1: Check if Docker MongoDB exists
docker ps -a | findstr mongo >nul 2>&1
if %errorlevel% equ 0 (
    echo Found Docker MongoDB container - starting...
    docker start mongo >nul 2>&1
    set MONGO_URL=mongodb://localhost:27017
    goto :writeEnv
)

:: Method 2: Check if local MongoDB installed
where mongod >nul 2>&1
if %errorlevel% equ 0 (
    echo Starting local MongoDB...
    start /b cmd /c "mongod --dbpath %%USERPROFILE%%\data\db"
    timeout /t 2 /nobreak >nul
    set MONGO_URL=mongodb://localhost:27017
    goto :writeEnv
)

:: Method 3: Check if already running
netstat | findstr ":27017" >nul
if %errorlevel% equ 0 (
    echo MongoDB already running
    set MONGO_URL=mongodb://localhost:27017
    goto :writeEnv
)

:: No MongoDB - Enable Demo Mode
echo.
echo  ========================================
echo    No MongoDB found. Using demo mode.
echo  ========================================
set DEMO_MODE=true
set MONGO_URL=

:writeEnv
echo Writing config...
(
echo CREDENTIAL_KEY=sentinel-%RANDOM%-%TIME:~0,2%
if "%DEMO_MODE%"=="true" (
    echo DEMO_MODE=true
    echo MONGO_URL=
) else (
    if defined MONGO_URL echo MONGO_URL=%MONGO_URL%
)
) > .env

:startSentinel
echo.
echo Starting Sentinel Pulse...
start /b cmd /c "SentinelPulse.exe"

echo.
echo  ========================================
echo    Done! Opening browser...
echo  ========================================
timeout /t 3 /nobreak >nul
start http://localhost:3000
echo.
echo  Press any key to exit...
pause >nul