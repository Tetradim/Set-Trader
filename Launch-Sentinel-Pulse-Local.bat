@echo off
setlocal
title Sentinel Pulse - Local Source
echo.
echo ========================================
echo   Sentinel Pulse - Local Source
echo ========================================
echo.

set "LAUNCHER=%~dp0Launch-Sentinel-Pulse-Local.ps1"
if not exist "%LAUNCHER%" (
  echo Sentinel Pulse local launcher file is missing:
  echo   %LAUNCHER%
  echo.
  echo Extract the full Sentinel Pulse folder first, or install with SentinelPulse-Setup.exe.
  echo If you opened a zip preview or copied only this .bat file, Windows cannot find the PowerShell launcher.
  pause
  exit /b 2
)

set "POWERSHELL=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%POWERSHELL%" (
  where powershell.exe >nul 2>nul
  if errorlevel 1 (
    echo.
    echo PowerShell was not found. Sentinel Pulse needs Windows PowerShell to start.
    echo Please send this screenshot to Sentinel Pulse support.
    pause
    exit /b 9009
  )
  set "POWERSHELL=powershell.exe"
)

"%POWERSHELL%" -NoProfile -ExecutionPolicy Bypass -File "%LAUNCHER%"
set EXITCODE=%ERRORLEVEL%
if not "%EXITCODE%"=="0" (
  echo.
  echo Sentinel Pulse local launcher exited with code %EXITCODE%.
  pause
)
exit /b %EXITCODE%
