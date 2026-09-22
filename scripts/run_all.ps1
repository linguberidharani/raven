<#
.SYNOPSIS
    Starts the whole of RAVEN: the backend and the frontend, each in its own window, then opens the browser.
.DESCRIPTION
    Backend  http://127.0.0.1:8000  (scripts\run_backend.ps1, with the project venv)
    Frontend http://localhost:5173  (scripts\run_frontend.ps1)
    Stop both with scripts\stop_all.ps1, or press Ctrl+C in each window.
.PARAMETER CheckOnly
    Only checks that everything needed is there (venv, Node.js, free ports) and starts nothing.
.PARAMETER NoBrowser
    Does not open the browser.
#>
[CmdletBinding()]
param(
    [switch]$CheckOnly,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$activate = Join-Path $root 'venv\Scripts\Activate.ps1'
$venvPython = Join-Path $root 'venv\Scripts\python.exe'
$backendScript = Join-Path $root 'scripts\run_backend.ps1'
$frontendScript = Join-Path $root 'scripts\run_frontend.ps1'
$stateFile = Join-Path $root 'data\run_all.json'
$healthUrl = 'http://127.0.0.1:8000/api/health'
$appUrl = 'http://localhost:5173'

function Test-PortBusy {
    param([int]$Port)
    if (-not (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue)) { return $false }
    return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Wait-ForUrl {
    param([string]$Url, [int]$Seconds)
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $answer = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
            if ($answer.StatusCode -ge 200 -and $answer.StatusCode -lt 500) { return $true }
        }
        catch {
            # not up yet
        }
        Start-Sleep -Seconds 1
    }
    return $false
}

# 1. Checks
$problems = @()
if (-not (Test-Path -LiteralPath $venvPython)) { $problems += "The Python environment was not found ($venvPython). Create it as described in README.md." }
if (-not (Test-Path -LiteralPath $backendScript)) { $problems += "scripts\run_backend.ps1 was not found." }
if (-not (Test-Path -LiteralPath $frontendScript)) { $problems += "scripts\run_frontend.ps1 was not found." }
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { $problems += 'Node.js was not found. Install Node.js 20 or newer.' }
if (-not (Test-Path -LiteralPath (Join-Path $root 'frontend\package.json'))) { $problems += 'The frontend folder was not found.' }
foreach ($port in 8000, 5173) {
    if (Test-PortBusy -Port $port) { $problems += "Port $port is already in use. Run scripts\stop_all.ps1, or close the window that uses it." }
}
if ($problems.Count -gt 0) {
    Write-Host 'RAVEN cannot start yet:' -ForegroundColor Red
    foreach ($problem in $problems) { Write-Host "  - $problem" -ForegroundColor Red }
    throw 'Fix the points above and run scripts\run_all.ps1 again.'
}
if (-not (Test-Path -LiteralPath (Join-Path $root '.env'))) {
    Write-Host 'Note: there is no .env file, so the default settings are used (copy .env.example to .env to change them).' -ForegroundColor Yellow
}
Write-Host 'Checks passed: the environment, Node.js and the ports 8000 and 5173 are ready.' -ForegroundColor Green
if ($CheckOnly) { return }

# 2. Start the two windows
$backendCommand = "`$Host.UI.RawUI.WindowTitle = 'RAVEN backend'; . '$activate'; & '$backendScript'"
$frontendCommand = "`$Host.UI.RawUI.WindowTitle = 'RAVEN frontend'; & '$frontendScript'"
$backend = Start-Process -FilePath 'powershell.exe' -WorkingDirectory $root -PassThru -ArgumentList @('-NoExit', '-ExecutionPolicy', 'Bypass', '-Command', ('"{0}"' -f $backendCommand))
$frontend = Start-Process -FilePath 'powershell.exe' -WorkingDirectory $root -PassThru -ArgumentList @('-NoExit', '-ExecutionPolicy', 'Bypass', '-Command', ('"{0}"' -f $frontendCommand))

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $stateFile) | Out-Null
@{ backend_window_pid = $backend.Id; frontend_window_pid = $frontend.Id; started = (Get-Date).ToString('o') } | ConvertTo-Json | Set-Content -LiteralPath $stateFile -Encoding UTF8

# 3. Wait until both answer
Write-Host 'Starting the backend ...'
if (-not (Wait-ForUrl -Url $healthUrl -Seconds 90)) {
    Write-Host "The backend did not answer at $healthUrl within 90 seconds. Read the window titled 'RAVEN backend' for the reason." -ForegroundColor Red
    throw 'The backend did not start.'
}
Write-Host "Backend is up:  $healthUrl" -ForegroundColor Green
Write-Host 'Starting the frontend (the first start installs packages and can take a minute) ...'
if (-not (Wait-ForUrl -Url $appUrl -Seconds 240)) {
    Write-Host "The frontend did not answer at $appUrl within 4 minutes. Read the window titled 'RAVEN frontend' for the reason." -ForegroundColor Red
    throw 'The frontend did not start.'
}
Write-Host "Frontend is up: $appUrl" -ForegroundColor Green

if (-not $NoBrowser) { Start-Process $appUrl }
Write-Host ''
Write-Host 'RAVEN is running. To stop it: scripts\stop_all.ps1 (or Ctrl+C in the two windows).'
