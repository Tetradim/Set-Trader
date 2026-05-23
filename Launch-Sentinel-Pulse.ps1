# Sentinel Pulse Launcher
# Starts MongoDB and Sentinel Pulse from an installed package or source checkout.

param(
    [string]$MongoPath = "",
    [string]$DataPath = "",
    [string]$LogPath = "",
    [string]$SettingsPath = "",
    [int]$MongoPort = 27017,
    [int]$AppPort = 8002,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$ProjectRoot = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not $ProjectRoot) { $ProjectRoot = (Get-Location).Path }

if (-not $DataPath) { $DataPath = Join-Path $ProjectRoot "data\db" }
if (-not $LogPath) { $LogPath = Join-Path $ProjectRoot "logs" }
if (-not $SettingsPath) { $SettingsPath = Join-Path $ProjectRoot "launcher-settings.ini" }

$OwnedProcesses = New-Object System.Collections.Generic.List[System.Diagnostics.Process]
$LogFile = Join-Path $LogPath "launcher.log"

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

function Start-OwnedProcess {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$WorkingDirectory
    )
    $process = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList -WorkingDirectory $WorkingDirectory -PassThru -WindowStyle Hidden
    $OwnedProcesses.Add($process)
    return $process
}

function Stop-OwnedProcesses {
    for ($i = $OwnedProcesses.Count - 1; $i -ge 0; $i--) {
        $process = $OwnedProcesses[$i]
        try {
            $current = Get-Process -Id $process.Id -ErrorAction SilentlyContinue
            if ($current) {
                Write-Status "Stopping process $($current.ProcessName) ($($current.Id))" "INFO"
                Stop-Process -Id $current.Id -Force -ErrorAction SilentlyContinue
            }
        } catch {
        }
    }
}

try {
    New-Item -ItemType Directory -Path $DataPath -Force | Out-Null
    New-Item -ItemType Directory -Path $LogPath -Force | Out-Null

    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  Sentinel Pulse Launcher" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Status "Project root: $ProjectRoot"
    Write-Status "Logs: $LogPath"

    if (-not (Test-PortOpen -Port $MongoPort)) {
        $mongoExe = Find-Mongo
        if (-not $mongoExe) {
            throw "MongoDB was not found. Install MongoDB Community Server or pass -MongoPath."
        }
        Write-Status "Starting MongoDB on port $MongoPort"
        $mongoLog = Join-Path $LogPath "mongod.log"
        Start-OwnedProcess -FilePath $mongoExe -ArgumentList @("--dbpath", $DataPath, "--port", "$MongoPort", "--logpath", $mongoLog, "--quiet") -WorkingDirectory $ProjectRoot | Out-Null
        if (-not (Wait-Port -Port $MongoPort -Seconds 20)) {
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
            Start-OwnedProcess -FilePath $rootExe -ArgumentList @() -WorkingDirectory $ProjectRoot | Out-Null
        } elseif (Test-Path $backendExe) {
            Write-Status "Starting backend packaged SentinelPulse.exe"
            Start-OwnedProcess -FilePath $backendExe -ArgumentList @() -WorkingDirectory (Split-Path -Parent $backendExe) | Out-Null
        } elseif (Test-Path $serverPy) {
            $python = Find-Python
            if (-not $python) {
                throw "Python was not found. Install Python 3.11+ or create backend\.venv."
            }
            Write-Status "Starting backend server on port $AppPort"
            $env:PORT = "$AppPort"
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

    $url = "http://localhost:$AppPort"
    if (-not $NoBrowser) {
        Write-Status "Opening $url"
        Start-Process $url | Out-Null
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
        Start-Sleep -Seconds 1
    }
} catch {
    Write-Status $_.Exception.Message "ERROR"
    exit 1
} finally {
    Stop-OwnedProcesses
}
