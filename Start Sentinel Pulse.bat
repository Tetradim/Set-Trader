@echo off
title Sentinel Pulse

:: Trap Ctrl+C for graceful shutdown
echo.
echo  ========================================
echo    Sentinel Pulse - Trading Bot
echo  ========================================
echo.
echo  Press Ctrl+C to stop the application.
echo.

:: Start the application
start /b cmd /c "SentinelPulse.exe"

:: Wait for user to press Ctrl+C
pause > nul

:: Graceful shutdown - kill the process
echo.
echo  Stopping Sentinel Pulse...
taskkill /f /im SentinelPulse.exe >nul 2>&1
echo  Done.
