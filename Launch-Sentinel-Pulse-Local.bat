@echo off
title Sentinel Pulse - Local Source
echo.
echo ========================================
echo   Sentinel Pulse - Local Source
echo ========================================
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Launch-Sentinel-Pulse-Local.ps1"
set EXITCODE=%ERRORLEVEL%
echo.
echo Sentinel Pulse local launcher exited with code %EXITCODE%.
pause
exit /b %EXITCODE%
