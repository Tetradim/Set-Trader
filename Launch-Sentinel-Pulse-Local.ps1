# Sentinel Pulse Local Source Launcher
# Runs the edited local source tree without building or downloading an installer.

param(
    [int]$MongoPort = 27017,
    [int]$BackendPort = 8002,
    [int]$FrontendPort = 3000,
    [string]$DataPath = "",
    [switch]$NoBrowser,
    [switch]$SkipMongo,
    [switch]$InstallDeps
)

$ErrorActionPreference = "Stop"
$ProjectRoot = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not $ProjectRoot) { $ProjectRoot = (Get-Location).Path }

$Backend = Join-Path $ProjectRoot "backend"
$Frontend = Join-Path $ProjectRoot "frontend"
$DesktopPath = [Environment]::GetFolderPath("Desktop")
if (-not $DesktopPath) { $DesktopPath = Join-Path $HOME "Desktop" }
if (-not $DataPath) { $DataPath = Join-Path $env:SystemDrive "data\db" }

$LogFile = Join-Path $DesktopPath "Sentinel-Pulse-Local.log"
$OwnedProcesses = New-Object System.Collections.Generic.List[System.Diagnostics.Process]
$BrowserProcess = $null
$BrowserProfileDir = $null
$BrowserProcessIds = @()
$BrowserMonitorDisabled = $false

function Write-Status {
    param([string]$Message, [string]$Level = "INFO")
    $color = switch ($Level) {
        "OK" { "Green" }
        "WARN" { "Yellow" }
        "ERROR" { "Red" }
        default { "Cyan" }
    }
    Write-Host "[$Level] $Message" -ForegroundColor $color
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss.fff"
    Add-Content -Path $LogFile -Value "$timestamp [$Level] $Message" -Encoding UTF8
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
    param([int]$Port, [int]$Seconds = 30)
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-PortOpen -Port $Port) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Find-Mongo {
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

function Find-Npm {
    foreach ($name in @("npm.cmd", "npm.exe", "npm")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }
    return $null
}

function Get-PythonVersion {
    param(
        [string]$FilePath,
        [string[]]$ArgumentPrefix = @()
    )
    try {
        $args = @($ArgumentPrefix + @("-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"))
        $version = (& $FilePath @args 2>$null | Select-Object -First 1)
        if (-not $version) { return $null }
        return [version]$version
    } catch {
        return $null
    }
}

function Test-CompatiblePythonVersion {
    param([version]$Version)
    return $Version -and $Version.Major -eq 3 -and $Version.Minor -ge 11 -and $Version.Minor -le 13
}

function Find-CompatiblePython {
    $candidates = New-Object System.Collections.Generic.List[object]

    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($py) {
        foreach ($selector in @("-3.11", "-3.12", "-3.13")) {
            $candidates.Add([pscustomobject]@{
                FilePath = $py.Source
                ArgumentPrefix = @($selector)
                Label = "py $selector"
            })
        }
    }

    foreach ($name in @("python3.11.exe", "python3.12.exe", "python3.13.exe", "python.exe")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) {
            $candidates.Add([pscustomobject]@{
                FilePath = $cmd.Source
                ArgumentPrefix = @()
                Label = $cmd.Source
            })
        }
    }

    foreach ($candidate in $candidates) {
        $version = Get-PythonVersion -FilePath $candidate.FilePath -ArgumentPrefix $candidate.ArgumentPrefix
        if (Test-CompatiblePythonVersion -Version $version) {
            return [pscustomobject]@{
                FilePath = $candidate.FilePath
                ArgumentPrefix = $candidate.ArgumentPrefix
                Version = $version
                Label = $candidate.Label
            }
        }
    }

    return $null
}

function Invoke-CompatiblePython {
    param(
        [object]$PythonInfo,
        [string[]]$Arguments
    )
    $fullArgs = @($PythonInfo.ArgumentPrefix + $Arguments)
    & $PythonInfo.FilePath @fullArgs
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

function Test-BrowserWindowClosed {
    if ($BrowserMonitorDisabled) { return $false }
    if (-not $BrowserProcess -and -not $BrowserProfileDir -and $BrowserProcessIds.Count -eq 0) { return $false }

    $profileProcesses = @(Update-BrowserProcessIds)
    if ($profileProcesses.Count -gt 0) { return $false }

    $knownProcesses = @($BrowserProcessIds | ForEach-Object { Get-Process -Id $_ -ErrorAction SilentlyContinue })
    if ($knownProcesses.Count -gt 0) { return $false }
    if ($BrowserProcessIds.Count -gt 0) { return $true }

    if ($BrowserProcess -and $BrowserProcess.HasExited) {
        Write-Status "Browser process handed off; close monitoring disabled" "WARN"
        $script:BrowserMonitorDisabled = $true
    }
    return $false
}

function Start-BrowserWindow {
    param([string]$Url)

    $browserExe = Find-BrowserExecutable
    if ($browserExe) {
        Write-Status "Opening dedicated browser window"
        $script:BrowserProfileDir = Join-Path ([System.IO.Path]::GetTempPath()) "SentinelPulse-Local-Browser-$PID"
        New-Item -ItemType Directory -Path $script:BrowserProfileDir -Force | Out-Null
        $browserArgs = Join-ProcessArguments -Arguments @("--new-window", "--app=$Url", "--user-data-dir=$script:BrowserProfileDir", "--no-first-run", "--disable-background-mode")
        $process = Start-Process -FilePath $browserExe -ArgumentList $browserArgs -PassThru
        Start-Sleep -Milliseconds 500
        Update-BrowserProcessIds | Out-Null
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
        [string]$WorkingDirectory,
        [switch]$Visible
    )
    $startParams = @{
        FilePath = $FilePath
        WorkingDirectory = $WorkingDirectory
        PassThru = $true
    }
    if ($ArgumentList -and $ArgumentList.Count -gt 0) {
        $startParams.ArgumentList = Join-ProcessArguments -Arguments $ArgumentList
    }
    if (-not $Visible) {
        $startParams.WindowStyle = "Hidden"
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
            Write-Status "Stopping process $($current.ProcessName) ($($current.Id))"
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

try {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  Sentinel Pulse - Local Source" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Status "Project root: $ProjectRoot"
    Write-Status "Local log: $LogFile"

    if (-not (Test-Path $Backend)) { throw "Backend folder not found: $Backend" }
    if (-not (Test-Path $Frontend)) { throw "Frontend folder not found: $Frontend" }

    if (-not $SkipMongo) {
        if (-not (Test-PortOpen -Port $MongoPort)) {
            New-Item -ItemType Directory -Path $DataPath -Force | Out-Null
            $mongoExe = Find-Mongo
            if (-not $mongoExe) {
                throw "MongoDB was not found. Install MongoDB Community Server or start MongoDB manually with -SkipMongo."
            }
            $mongoBin = Split-Path -Parent $mongoExe
            $mongoLog = Join-Path $DesktopPath "Sentinel-Pulse-MongoDB.log"
            Write-Status "Starting MongoDB from $mongoBin"
            $mongoProcess = Start-OwnedProcess -FilePath $mongoExe -ArgumentList @("--dbpath", $DataPath, "--port", "$MongoPort", "--logpath", $mongoLog, "--quiet") -WorkingDirectory $mongoBin
            if (-not (Wait-Port -Port $MongoPort -Seconds 15)) {
                if ($mongoProcess.HasExited) {
                    throw "MongoDB exited with code $($mongoProcess.ExitCode) before opening port $MongoPort. Check $mongoLog."
                }
                throw "MongoDB did not open port $MongoPort. Check $mongoLog."
            }
            Write-Status "MongoDB is ready" "OK"
        } else {
            Write-Status "MongoDB already running on port $MongoPort" "WARN"
        }
    }

    $venvPath = Join-Path $Backend ".venv"
    $venvPython = Join-Path $venvPath "Scripts\python.exe"
    if (Test-Path $venvPython) {
        $venvVersion = Get-PythonVersion -FilePath $venvPython
        if (-not (Test-CompatiblePythonVersion -Version $venvVersion)) {
            Write-Status "Backend virtual environment uses Python $venvVersion; recreating with Python 3.11-3.13" "WARN"
            Remove-Item -LiteralPath $venvPath -Recurse -Force
        }
    }

    if (-not (Test-Path $venvPython)) {
        $pythonInfo = Find-CompatiblePython
        if (-not $pythonInfo) {
            throw "A compatible Python was not found. Sentinel Pulse local source requires Python 3.11-3.13 because current pinned wheels do not support Python 3.14. Install Python 3.11 and rerun."
        }
        Write-Status "Creating backend virtual environment with $($pythonInfo.Label) ($($pythonInfo.Version))"
        Invoke-CompatiblePython -PythonInfo $pythonInfo -Arguments @("-m", "venv", $venvPath)
        $InstallDeps = $true
    }

    if ($InstallDeps) {
        Write-Status "Installing backend dependencies"
        & $venvPython -m pip install --retries 10 --timeout 180 --prefer-binary -r (Join-Path $Backend "requirements.txt")
    }

    $npm = Find-Npm
    if (-not $npm) { throw "npm was not found. Install Node.js." }
    if ($InstallDeps -or -not (Test-Path (Join-Path $Frontend "node_modules"))) {
        Write-Status "Installing frontend dependencies"
        Start-OwnedProcess -FilePath $npm -ArgumentList @("install") -WorkingDirectory $Frontend -Visible | Wait-Process
    }

    $backendUrl = "http://127.0.0.1:$BackendPort"
    $frontendUrl = "http://127.0.0.1:$FrontendPort"
    $env:PORT = "$BackendPort"
    $env:SENTINEL_OPEN_BROWSER = "0"
    $env:VITE_BACKEND_URL = $backendUrl
    $env:REACT_APP_BACKEND_URL = $backendUrl
    $env:LOG_FILE = $LogFile

    if (-not (Test-PortOpen -Port $BackendPort)) {
        Write-Status "Starting backend from source on port $BackendPort"
        Start-OwnedProcess -FilePath $venvPython -ArgumentList @("-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", "$BackendPort", "--reload") -WorkingDirectory $Backend | Out-Null
        if (-not (Wait-Port -Port $BackendPort -Seconds 45)) {
            throw "Backend did not open port $BackendPort. Check $LogFile."
        }
        Write-Status "Backend is ready" "OK"
    } else {
        Write-Status "Backend already running on port $BackendPort" "WARN"
    }

    if (-not (Test-PortOpen -Port $FrontendPort)) {
        Write-Status "Starting Vite frontend from source on port $FrontendPort"
        Start-OwnedProcess -FilePath $npm -ArgumentList @("run", "dev", "--", "--host", "127.0.0.1", "--port", "$FrontendPort") -WorkingDirectory $Frontend | Out-Null
        if (-not (Wait-Port -Port $FrontendPort -Seconds 45)) {
            throw "Frontend did not open port $FrontendPort. Check $LogFile."
        }
        Write-Status "Frontend is ready" "OK"
    } else {
        Write-Status "Frontend already running on port $FrontendPort" "WARN"
    }

    if (-not $NoBrowser) {
        $BrowserProcess = Start-BrowserWindow -Url $frontendUrl
    }

    Write-Host ""
    Write-Host "Ready: $frontendUrl" -ForegroundColor Green
    Write-Host "Backend: $backendUrl" -ForegroundColor Gray
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
    Stop-BrowserWindow
    Stop-OwnedProcesses
}
