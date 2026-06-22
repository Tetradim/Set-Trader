@echo off
setlocal
cd /d "%~dp0"
set "POWERSHELL=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%POWERSHELL%" (
  where powershell.exe >nul 2>nul
  if errorlevel 1 (
    echo.
    echo PowerShell was not found. Sentinel Pulse needs Windows PowerShell to start and repair missing dependencies.
    echo Please send this screenshot to Sentinel Pulse support.
    pause
    exit /b 9009
  )
  set "POWERSHELL=powershell.exe"
)
"%POWERSHELL%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0Launch-Sentinel-Pulse.ps1"
set EXIT_CODE=%ERRORLEVEL%
if not "%EXIT_CODE%"=="0" (
  echo.
  echo Sentinel Pulse launcher exited with code %EXIT_CODE%.
  pause
)
exit /b %EXIT_CODE%
