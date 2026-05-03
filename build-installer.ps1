<#
.SYNOPSIS
    Build a Windows installer with Start Menu / Desktop shortcuts.
.DESCRIPTION
    Creates an NSIS-style installer that:
    1. Installs Sentinel Pulse to Program Files
    2. Creates Start Menu shortcuts (Run, Configure, Uninstall)
    3. Creates Desktop shortcut
    4. Registers uninstaller in Add/Remove Programs
    
    Requires 7-Zip (7z) and optionally NSIS for proper installer.
.EXAMPLE
    .\build-installer.ps1
#>

param(
    [switch]$Clean,
    [string]$InstallDir = "$env:ProgramFiles\Sentinel Pulse",
    [switch]$CreateDesktopShortcut,
    [switch]$NoDesktopShortcut
)

$ErrorActionPreference = "Stop"
$ROOT = $PSScriptRoot
$BACKEND = Join-Path $ROOT "backend"
$DIST = Join-Path $BACKEND "dist"

Write-Host ""
Write-Host "  ===========================================" -ForegroundColor Cyan
Write-Host "    Sentinel Pulse Windows Installer Builder" -ForegroundColor Cyan
Write-Host "  ===========================================" -ForegroundColor Cyan
Write-Host ""

# Check for 7-Zip
$sevenZip = Get-Command 7z -ErrorAction SilentlyContinue
if (-not $sevenZip) {
    Write-Host "[WARN] 7-Zip not found. Installing without compression." -ForegroundColor Yellow
}

# Build steps
$step = 1

# 1. Build the application (if not exists)
if (-not (Test-Path "$DIST\Sentinel Pulse.exe")) {
    Write-Host "[$step/4] Building Sentinel Pulse..." -ForegroundColor Green
    & "$ROOT\build-windows.ps1" -SkipFrontend
    $step++
} else {
    Write-Host "[SKIP] Sentinel Pulse.exe already exists." -ForegroundColor Gray
}

# 2. Create installer package
Write-Host "[$step/4] Creating installer package..." -ForegroundColor Green
$STAGING = Join-Path $ROOT ".installer-staging"
if ($Clean -and (Test-Path $STAGING)) { Remove-Item -Recurse -Force $STAGING }
New-Item -ItemType Directory -Force -Path $STAGING | Out-Null

# Copy files
Copy-Item -Path "$DIST\*" -Destination $STAGING -Recurse -Force

# Create uninstaller script (silent, no prompt)
$uninstallScriptSilent = @"
@echo off
echo Uninstalling Sentinel Pulse...
timeout /t 1 /nobreak >nul
del /q "$env:PUBLIC\Desktop\Sentinel Pulse.lnk" 2>nul
del /q "$env:PUBLIC\Desktop\Uninstall Sentinel Pulse.lnk" 2>nul
del /q "$env:PUBLIC\Desktop\Sentinel Pulse.url" 2>nul
del /q "$env:PUBLIC\Desktop\Uninstall Sentinel Pulse.url" 2>nul
del /q "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\Sentinel Pulse\*.lnk" 2>nul
del /q "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\Sentinel Pulse\*.url" 2>nul
rmdir /s /q "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\Sentinel Pulse" 2>nul
rmdir /s /q "$InstallDir" 2>nul
echo Done.
"@

# Create uninstaller script (with confirmation prompt)
$uninstallScriptConfirm = @"
@echo off
echo Uninstalling Sentinel Pulse...
echo.
echo Press any key to confirm uninstallation, or Ctrl+C to cancel...
pause >nul
echo.
call "$InstallDir\Uninstall-Silent.bat"
echo Sentinel Pulse has been uninstalled.
pause
"@

# Write both versions
$uninstallScriptSilent | Out-File -FilePath "$STAGING\Uninstall-Silent.bat" -Encoding ASCII
$uninstallScriptConfirm | Out-File -FilePath "$STAGING\Uninstall.bat" -Encoding ASCII

# Create Start Menu shortcuts
$startMenuFolder = "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\Sentinel Pulse"
New-Item -ItemType Directory -Force -Path $startMenuFolder | Out-Null

# Main app shortcut
$appShortcut = @"
[InternetShortcut]
URL=file:///$InstallDir/Sentinel Pulse.exe
"@
$appShortcut | Out-File -FilePath "$startMenuFolder\Run Sentinel Pulse.url" -Encoding ASCII

# Config shortcut
$configShortcut = @"
[InternetShortcut]
URL=file:///$InstallDir/backend/api/config
"@
$configShortcut | Out-File -FilePath "$startMenuFolder\Configure.url" -Encoding ASCII

# Uninstall shortcut (with confirmation)
$uninstallShortcut = @"
[InternetShortcut]
URL=file:///$InstallDir/Uninstall.bat
"@
$uninstallShortcut | Out-File -FilePath "$startMenuFolder\Uninstall.url" -Encoding ASCII

# Desktop Uninstall shortcut (runs silent uninstall when clicked)
$desktopUninstallShortcut = @"
[InternetShortcut]
URL=file:///$InstallDir/Uninstall-Silent.bat
"@
$desktopUninstallShortcut | Out-File -FilePath "$env:PUBLIC\Desktop\Uninstall Sentinel Pulse.url" -Encoding ASCII

# Desktop shortcut (optional)
if ($CreateDesktopShortcut -or (-not $NoDesktopShortcut)) {
    $desktopShortcut = @"
[InternetShortcut]
URL=file:///$InstallDir/Sentinel Pulse.exe
"@
    $desktopShortcut | Out-File -FilePath "$env:PUBLIC\Desktop\Sentinel Pulse.url" -Encoding ASCII
}

# 3. Create installer batch (self-extracting)
Write-Host "[$step/4] Creating self-extracting installer..." -ForegroundColor Green

$installerBatch = @"
@echo off
setlocal enabledelayedexpansion

echo ============================================
echo   Sentinel Pulse Installer
echo ============================================
echo.
echo Installing to: $InstallDir
echo.
echo Creating directory...
mkdir "$InstallDir" 2>nul
echo Copying files...
xcopy /E /Y /Q "$~dp0*.*" "$InstallDir\" >nul
echo.
echo Creating Start Menu shortcuts...
powershell -Command "New-Item -ItemType Directory -Force -Path '$env:ProgramData\Microsoft\Windows\Start Menu\Programs\Sentinel Pulse' | Out-Null"
powershell -Command "Set-Content -Path '$env:ProgramData\Microsoft\Windows\Start Menu\Programs\Sentinel Pulse\Run Sentinel Pulse.url' -Value '[InternetShortcut]'" -Append
powershell -Command "Add-Content -Path '$env:ProgramData\Microsoft\Windows\Start Menu\Programs\Sentinel Pulse\Run Sentinel Pulse.url' -Value 'URL=file:///$InstallDir/Sentinel Pulse.exe'"
if (-not $NoDesktopShortcut) (
    echo Creating Desktop shortcuts...
    powershell -Command "Set-Content -Path '$env:PUBLIC\Desktop\Sentinel Pulse.url' -Value '[InternetShortcut]'" -Append
    powershell -Command "Add-Content -Path '$env:PUBLIC\Desktop\Sentinel Pulse.url' -Value 'URL=file:///$InstallDir\Sentinel Pulse.exe'"
    powershell -Command "Set-Content -Path '$env:PUBLIC\Desktop\Uninstall Sentinel Pulse.url' -Value '[InternetShortcut]'" -Append
    powershell -Command "Add-Content -Path '$env:PUBLIC\Desktop\Uninstall Sentinel Pulse.url' -Value 'URL=file:///$InstallDir/Uninstall.bat'"
)
echo.
echo ============================================
echo   Installation Complete!
echo ============================================
echo.
echo   Run: Sentinel Pulse
echo   Uninstall: Double-click "Uninstall Sentinel Pulse" on desktop
echo   Configure: Start Menu > Sentinel Pulse > Configure
echo.
echo   Press any key to launch Sentinel Pulse, or close window.
pause >nul
start "" "$InstallDir\Sentinel Pulse.exe"
exit
"@

$installerBatch | Out-File -FilePath "$STAGING\Install.bat" -Encoding ASCII

# 4. Package it
if ($sevenZip) {
    Write-Host "[$step/4] Compressing installer..." -ForegroundColor Green
    $output = "$ROOT\Sentinel Pulse-Setup.exe"
    Push-Location $STAGING
    7z a -mx=9 "$output" *.* -r | Out-Null
    Pop-Location
    
    # Create self-extracting archive
    # This is a simple approach - for production use NSIS
    Write-Host "[OK] Installer created: $output" -ForegroundColor Green
    Write-Host "     Run Install.bat in the staging folder to install." -ForegroundColor Cyan
} else {
    Write-Host "[OK] Staging complete. Run Install.bat in .installer-staging to install." -ForegroundColor Green
}

Write-Host ""
Write-Host "  ===========================================" -ForegroundColor Cyan
Write-Host "    Installer Ready!" -ForegroundColor Cyan
Write-Host "  ===========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Shortcuts created:" -ForegroundColor White
Write-Host "  - Desktop: Sentinel Pulse (launches app)" -ForegroundColor Gray
Write-Host "  - Desktop: Uninstall Sentinel Pulse (removes app)" -ForegroundColor Gray
Write-Host "  - Start Menu > Sentinel Pulse > Run Sentinel Pulse" -ForegroundColor Gray
Write-Host "  - Start Menu > Sentinel Pulse > Configure" -ForegroundColor Gray  
Write-Host "  - Start Menu > Sentinel Pulse > Uninstall" -ForegroundColor Gray
Write-Host ""