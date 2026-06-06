# Sentinel Pulse Launcher
# Starts MongoDB and Sentinel Pulse from an installed package or source checkout.

param(
    [string]$MongoPath = "",
    [string]$DataPath = "",
    [string]$LogPath = "",
    [string]$SettingsPath = "",
    [int]$MongoPort = 27017,
    [int]$AppPort = 8002,
    [int]$FrontendPort = 3000,
    [switch]$NoBrowser,
    [switch]$SmokeTest
)

$ErrorActionPreference = "Stop"
$ProjectRoot = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not $ProjectRoot) { $ProjectRoot = (Get-Location).Path }

$DesktopPath = [Environment]::GetFolderPath("Desktop")
if (-not $DesktopPath) { $DesktopPath = Join-Path $HOME "Desktop" }

if (-not $DataPath) { $DataPath = Join-Path $env:SystemDrive "data\db" }
if (-not $LogPath) { $LogPath = $DesktopPath }
if (-not $SettingsPath) { $SettingsPath = Join-Path $ProjectRoot "launcher-settings.ini" }

$OwnedProcesses = New-Object System.Collections.Generic.List[System.Diagnostics.Process]
$LogFile = Join-Path $LogPath "Sentinel-Pulse.log"
$TranscriptFile = Join-Path $LogPath "Sentinel-Pulse-Transcript.log"
$TranscriptStarted = $false
$serverWillOpenBrowser = $false
$BrowserProcess = $null
$BrowserProfileDir = $null
$BrowserProcessIds = @()
$BrowserStartedAt = $null
$BrowserMonitorDisabled = $false
$ShutdownStarted = $false
$CleanupEventSubscription = $null
$CancelKeyPressHandler = $null

function Write-Status {
    param([string]$Message, [string]$Level = "INFO")
    $color = switch ($Level) {
        "OK" { "Green" }
        "WARN" { "Yellow" }
        "ERROR" { "Red" }
        default { "Cyan" }
    }
    Write-Host "[$Level] $Message" -ForegroundColor $color
    if (Test-Path $LogPath) {
        $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss.fff"
        Add-Content -Path $LogFile -Value "$timestamp [$Level] $Message" -Encoding UTF8
    }
}

function Test-PortOpen {
    param([int]$Port)
    try {
        $client = New-Object Net.Sockets.TcpClient
        $async = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        $connected = $async.AsyncWaitHandle.WaitOne(750, $false)
        if ($connected) { $client.EndConnect($async) }
        $client.Close()
        return $connected
    } catch {
        return $false
    }
}

function Wait-Port {
    param([int]$Port, [int]$Seconds = 15)
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-PortOpen -Port $Port) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Wait-PortAttempts {
    param([int]$Port, [int]$Attempts = 3, [int]$IntervalSeconds = 3)
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        Start-Sleep -Seconds $IntervalSeconds
        if (Test-PortOpen -Port $Port) {
            Write-Status "Port $Port opened on check $attempt of $Attempts" "OK"
            return $true
        }
        Write-Status "Port $Port not open yet; check $attempt of $Attempts" "WARN"
    }
    return $false
}

function Find-Mongo {
    if ($MongoPath) {
        $candidate = Join-Path $MongoPath "mongod.exe"
        if (Test-Path $candidate) { return $candidate }
        if (Test-Path $MongoPath) { return $MongoPath }
    }

    $candidates = @(
        "C:\Program Files\MongoDB\Server\8.2\bin\mongod.exe",
        "C:\Program Files\MongoDB\Server\8.0\bin\mongod.exe",
        "C:\Program Files\MongoDB\Server\7.0\bin\mongod.exe",
        "C:\Program Files\MongoDB\Server\6.0\bin\mongod.exe"
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) { return $candidate }
    }

    $cmd = Get-Command mongod.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

function Find-Python {
    $candidates = @(
        (Join-Path $ProjectRoot "backend\.venv\Scripts\python.exe"),
        (Join-Path $ProjectRoot "backend\venv\Scripts\python.exe"),
        (Join-Path $ProjectRoot ".venv\Scripts\python.exe")
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) { return $candidate }
    }

    foreach ($name in @("python.exe", "py.exe")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }

    return $null
}

function Find-Npm {
    foreach ($name in @("npm.cmd", "npm.exe", "npm")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }
    return $null
}

function Find-BrowserExecutable {
    $candidates = @(
        "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
        "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
        "$env:LOCALAPPDATA\Microsoft\Edge\Application\msedge.exe",
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
    )

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) { return $candidate }
    }

    foreach ($name in @("msedge.exe", "chrome.exe")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }

    return $null
}

function Get-BrowserProfileProcesses {
    if (-not $BrowserProfileDir) { return @() }
    try {
        return @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -and $_.CommandLine.IndexOf($BrowserProfileDir, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 } |
            ForEach-Object { Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue })
    } catch {
        return @()
    }
}

function Update-BrowserProcessIds {
    $profileProcesses = @(Get-BrowserProfileProcesses)
    if ($profileProcesses.Count -gt 0) {
        $script:BrowserProcessIds = @($profileProcesses | Select-Object -ExpandProperty Id)
    }
    return $profileProcesses
}

function Wait-BrowserProfileProcesses {
    param([int]$Seconds = 10)

    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        $profileProcesses = @(Update-BrowserProcessIds)
        if ($profileProcesses.Count -gt 0) { return $profileProcesses }
        Start-Sleep -Milliseconds 250
    }
    return @(Update-BrowserProcessIds)
}

function Test-BrowserWindowClosed {
    if ($BrowserMonitorDisabled) { return $false }
    if (-not $BrowserProcess -and -not $BrowserProfileDir -and $BrowserProcessIds.Count -eq 0) { return $false }

    $profileProcesses = @(Update-BrowserProcessIds)
    if ($profileProcesses.Count -gt 0) { return $false }

    $knownProcesses = @($BrowserProcessIds | ForEach-Object { Get-Process -Id $_ -ErrorAction SilentlyContinue })
    if ($knownProcesses.Count -gt 0) { return $false }
    if ($BrowserProcessIds.Count -gt 0) { return $true }

    if ($BrowserProfileDir -and $BrowserStartedAt) {
        $elapsed = ((Get-Date) - $BrowserStartedAt).TotalSeconds
        if ($elapsed -lt 15) { return $false }
    }

    if ($BrowserProcess -and $BrowserProcess.HasExited) {
        return $true
    }
    return $false
}

function Start-BrowserWindow {
    param([string]$Url)

    $browserExe = Find-BrowserExecutable
    if ($browserExe) {
        Write-Status "Opening dedicated browser window"
        $script:BrowserProfileDir = Join-Path ([System.IO.Path]::GetTempPath()) "SentinelPulse-Browser-$PID"
        $script:BrowserStartedAt = Get-Date
        New-Item -ItemType Directory -Path $script:BrowserProfileDir -Force | Out-Null
        $browserArgs = Join-ProcessArguments -Arguments @("--new-window", "--app=$Url", "--user-data-dir=$script:BrowserProfileDir", "--no-first-run", "--disable-background-mode")
        $process = Start-Process -FilePath $browserExe -ArgumentList $browserArgs -PassThru
        Wait-BrowserProfileProcesses -Seconds 10 | Out-Null
        return $process
    }

    Write-Status "Opening default browser without close monitoring" "WARN"
    Start-Process $Url | Out-Null
    return $null
}

function Join-ProcessArguments {
    param([string[]]$Arguments)

    return (($Arguments | ForEach-Object {
        $arg = $_
        if ($null -eq $arg) {
            '""'
        } elseif ($arg -match '[\s"]') {
            $escaped = $arg.Replace('"', '\"')
            '"' + $escaped + '"'
        } else {
            $arg
        }
    }) -join " ")
}

function Start-OwnedProcess {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$WorkingDirectory
    )
    $startParams = @{
        FilePath = $FilePath
        WorkingDirectory = $WorkingDirectory
        PassThru = $true
        WindowStyle = "Hidden"
    }
    if ($ArgumentList -and $ArgumentList.Count -gt 0) {
        $startParams.ArgumentList = Join-ProcessArguments -Arguments $ArgumentList
    }
    $process = Start-Process @startParams
    $OwnedProcesses.Add($process)
    return $process
}

function Stop-ProcessTree {
    param([int]$ProcessId)
    try {
        $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $ProcessId" -ErrorAction SilentlyContinue)
        foreach ($child in $children) {
            Stop-ProcessTree -ProcessId $child.ProcessId
        }

        $current = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
        if ($current) {
            Write-Status "Stopping process $($current.ProcessName) ($($current.Id))" "INFO"
            Stop-Process -Id $current.Id -Force -ErrorAction SilentlyContinue
        }
    } catch {
    }
}

function Stop-OwnedProcesses {
    for ($i = $OwnedProcesses.Count - 1; $i -ge 0; $i--) {
        $process = $OwnedProcesses[$i]
        Stop-ProcessTree -ProcessId $process.Id
    }
}

function Stop-BrowserWindow {
    $profileProcesses = @(Get-BrowserProfileProcesses)
    try {
        foreach ($current in $profileProcesses) {
            Write-Status "Closing browser window ($($current.Id))" "INFO"
            $current.CloseMainWindow() | Out-Null
        }
        Start-Sleep -Milliseconds 500
        foreach ($current in $profileProcesses) {
            $remaining = Get-Process -Id $current.Id -ErrorAction SilentlyContinue
            if ($remaining) {
                Stop-Process -Id $remaining.Id -Force -ErrorAction SilentlyContinue
            }
        }
    } catch {
    }
    if ($profileProcesses.Count -eq 0 -and $BrowserProcess) {
        try {
            $current = Get-Process -Id $BrowserProcess.Id -ErrorAction SilentlyContinue
            if ($current) {
                Write-Status "Closing browser window ($($current.Id))" "INFO"
                $current.CloseMainWindow() | Out-Null
                Start-Sleep -Milliseconds 500
                $current = Get-Process -Id $BrowserProcess.Id -ErrorAction SilentlyContinue
                if ($current) {
                    Stop-Process -Id $current.Id -Force -ErrorAction SilentlyContinue
                }
            }
        } catch {
        }
    }
    if ($BrowserProfileDir -and (Test-Path $BrowserProfileDir)) {
        try { Remove-Item -LiteralPath $BrowserProfileDir -Recurse -Force -ErrorAction SilentlyContinue } catch {}
    }
}

function Invoke-LauncherCleanup {
    if ($script:ShutdownStarted) { return }
    $script:ShutdownStarted = $true
    Stop-BrowserWindow
    Stop-OwnedProcesses
    if ($TranscriptStarted) {
        try { Stop-Transcript | Out-Null } catch {}
    }
}

function Register-LauncherShutdownHandlers {
    try {
        $script:CleanupEventSubscription = Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action {
            Invoke-LauncherCleanup
        }
    } catch {
    }

    try {
        $script:CancelKeyPressHandler = [ConsoleCancelEventHandler]{
            param($sender, $eventArgs)
            $eventArgs.Cancel = $true
            Write-Status "Shutdown requested; closing browser and processes" "WARN"
            Invoke-LauncherCleanup
            exit 0
        }
        [Console]::CancelKeyPress += $script:CancelKeyPressHandler
    } catch {
    }
}

if ($SmokeTest) {
    Write-Status "Running launcher smoke test"
    $basicArgs = Join-ProcessArguments -Arguments @("--dbpath", "C:\data\db", "--port", "27017")
    if (-not $basicArgs.Contains("--dbpath") -or -not $basicArgs.Contains("C:\data\db")) {
        throw "Basic argument smoke test failed."
    }
    $spacedArgs = Join-ProcessArguments -Arguments @("--logpath", "C:\Users\Lite OS\Desktop\Sentinel-Pulse.log")
    if (-not $spacedArgs.Contains('"C:\Users\Lite OS\Desktop\Sentinel-Pulse.log"')) {
        throw "Spaced argument quoting smoke test failed."
    }
    if (-not (Get-Command Start-Process -ErrorAction SilentlyContinue)) {
        throw "Start-Process is unavailable."
    }
    $browserArgs = Join-ProcessArguments -Arguments @("--user-data-dir=C:\Users\Lite OS\AppData\Local\Temp\SentinelPulse-Browser-1234")
    if (-not $browserArgs.Contains('"--user-data-dir=C:\Users\Lite OS\AppData\Local\Temp\SentinelPulse-Browser-1234"')) {
        throw "Browser argument quoting smoke test failed."
    }
    Write-Status "Launcher smoke test passed" "OK"
    exit 0
}

Register-LauncherShutdownHandlers

try {
    New-Item -ItemType Directory -Path $DataPath -Force | Out-Null
    New-Item -ItemType Directory -Path $LogPath -Force | Out-Null
    try {
        Start-Transcript -Path $TranscriptFile -Append | Out-Null
        $TranscriptStarted = $true
    } catch {
        $TranscriptStarted = $false
    }

    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  Sentinel Pulse Launcher" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Status "Project root: $ProjectRoot"
    Write-Status "App log: $LogFile"
    Write-Status "Launcher transcript: $TranscriptFile"
    Write-Status "MongoDB data path: $DataPath"
    $env:LOG_FILE = $LogFile
    $localCorsOrigins = @(
        "http://localhost:$FrontendPort",
        "http://127.0.0.1:$FrontendPort",
        "http://localhost:$AppPort",
        "http://127.0.0.1:$AppPort"
    ) -join ","
    if (-not $env:CORS_ORIGINS) {
        $env:CORS_ORIGINS = $localCorsOrigins
    }

    if (-not (Test-PortOpen -Port $MongoPort)) {
        $mongoExe = Find-Mongo
        if (-not $mongoExe) {
            throw "MongoDB was not found. Install MongoDB Community Server or pass -MongoPath."
        }
        $mongoBin = Split-Path -Parent $mongoExe
        Write-Status "Preparing MongoDB working directory: $mongoBin"
        Start-Sleep -Seconds 3
        Write-Status "Starting MongoDB on port $MongoPort"
        $mongoLog = Join-Path $LogPath "Sentinel-Pulse-MongoDB.log"
        Start-OwnedProcess -FilePath $mongoExe -ArgumentList @("--dbpath", $DataPath, "--port", "$MongoPort", "--logpath", $mongoLog, "--quiet") -WorkingDirectory $mongoBin | Out-Null
        if (-not (Wait-PortAttempts -Port $MongoPort -Attempts 3 -IntervalSeconds 3)) {
            throw "MongoDB did not open port $MongoPort. Check $mongoLog."
        }
        Write-Status "MongoDB is ready" "OK"
    } else {
        Write-Status "MongoDB already running on port $MongoPort" "WARN"
    }

    if (-not (Test-PortOpen -Port $AppPort)) {
        $rootExe = Join-Path $ProjectRoot "SentinelPulse.exe"
        $backendExe = Join-Path $ProjectRoot "backend\SentinelPulse.exe"
        $serverPy = Join-Path $ProjectRoot "backend\server.py"

        if (Test-Path $rootExe) {
            Write-Status "Starting packaged SentinelPulse.exe"
            $env:SENTINEL_OPEN_BROWSER = "0"
            Start-OwnedProcess -FilePath $rootExe -ArgumentList @() -WorkingDirectory $ProjectRoot | Out-Null
        } elseif (Test-Path $backendExe) {
            Write-Status "Starting backend packaged SentinelPulse.exe"
            $env:SENTINEL_OPEN_BROWSER = "0"
            Start-OwnedProcess -FilePath $backendExe -ArgumentList @() -WorkingDirectory (Split-Path -Parent $backendExe) | Out-Null
        } elseif (Test-Path $serverPy) {
            $python = Find-Python
            if (-not $python) {
                throw "Python was not found. Install Python 3.11+ or create backend\.venv."
            }
            Write-Status "Starting backend server on port $AppPort"
            $env:PORT = "$AppPort"
            $env:SENTINEL_OPEN_BROWSER = "0"
            Start-OwnedProcess -FilePath $python -ArgumentList @("server.py") -WorkingDirectory (Join-Path $ProjectRoot "backend") | Out-Null
        } else {
            throw "No Sentinel Pulse server was found. Expected SentinelPulse.exe or backend\server.py."
        }

        if (-not (Wait-Port -Port $AppPort -Seconds 30)) {
            throw "Sentinel Pulse did not open port $AppPort. Check $LogFile and backend logs."
        }
        Write-Status "Sentinel Pulse is ready on port $AppPort" "OK"
    } else {
        Write-Status "Sentinel Pulse already running on port $AppPort" "WARN"
    }

    $url = ("http://127.0.0.1:{0}" -f $AppPort)
    $frontendPackage = Join-Path $ProjectRoot "frontend\package.json"
    if (Test-Path $frontendPackage) {
        $frontendRoot = Split-Path -Parent $frontendPackage
        $url = "http://127.0.0.1:$FrontendPort"
        $env:VITE_BACKEND_URL = ""
        $env:REACT_APP_BACKEND_URL = ""
        if (-not (Test-PortOpen -Port $FrontendPort)) {
            $npm = Find-Npm
            if (-not $npm) {
                throw "Frontend source was found, but npm was not found. Install Node.js/npm or use the packaged installer."
            }
            Write-Status "Starting frontend UI on port $FrontendPort"
            Start-OwnedProcess -FilePath $npm -ArgumentList @("run", "dev", "--", "--host", "127.0.0.1", "--port", "$FrontendPort") -WorkingDirectory $frontendRoot | Out-Null
            if (-not (Wait-Port -Port $FrontendPort -Seconds 45)) {
                throw "Frontend UI did not open port $FrontendPort. Check $LogFile."
            }
            Write-Status "Frontend UI is ready on port $FrontendPort" "OK"
        } else {
            Write-Status "Frontend UI already running on port $FrontendPort" "WARN"
        }
    }

    if (-not $NoBrowser) {
        $BrowserProcess = Start-BrowserWindow -Url $url
    }

    Write-Host ""
    Write-Host "Ready: $url" -ForegroundColor Green
    Write-Host "Close this window or press Ctrl+C to stop processes started by this launcher." -ForegroundColor Gray
    Write-Host ""

    while ($true) {
        foreach ($process in @($OwnedProcesses)) {
            if ($process.HasExited) {
                throw "Process $($process.Id) exited unexpectedly."
            }
        }
        if (Test-BrowserWindowClosed) {
            Write-Status "Browser window closed; shutting down Sentinel Pulse" "OK"
            break
        }
        Start-Sleep -Seconds 1
    }
} catch {
    Write-Status $_.Exception.Message "ERROR"
    exit 1
} finally {
    Invoke-LauncherCleanup
}
