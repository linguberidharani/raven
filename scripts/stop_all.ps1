<#
.SYNOPSIS
    Stops what scripts\run_all.ps1 started: the backend and the frontend windows and the servers in them.
.DESCRIPTION
    First it closes the two windows recorded in data\run_all.json (with everything they started).
    Then it looks at ports 8000 and 5173; a python or node process still listening there is stopped too.
    Nothing else is touched.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
$stateFile = Join-Path $root 'data\run_all.json'

function Stop-Tree {
    param([int]$ProcessId, [string]$Label)
    if (-not (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)) { return }
    & taskkill.exe /PID $ProcessId /T /F | Out-Null
    Write-Host "Stopped $Label (process $ProcessId)."
}

if (Test-Path -LiteralPath $stateFile) {
    try {
        $state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
        Stop-Tree -ProcessId ([int]$state.backend_window_pid) -Label 'the backend window'
        Stop-Tree -ProcessId ([int]$state.frontend_window_pid) -Label 'the frontend window'
    }
    catch {
        Write-Host "Could not read $stateFile : $($_.Exception.Message)" -ForegroundColor Yellow
    }
    Remove-Item -LiteralPath $stateFile -ErrorAction SilentlyContinue
}

if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
    foreach ($port in 8000, 5173) {
        $listeners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        foreach ($listener in $listeners) {
            $process = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
            if ($null -eq $process) { continue }
            if ($process.ProcessName -in @('python', 'node')) {
                Stop-Tree -ProcessId $process.Id -Label "the $($process.ProcessName) server on port $port"
            }
            else {
                Write-Host "Port $port is used by $($process.ProcessName) (process $($process.Id)); it was left alone." -ForegroundColor Yellow
            }
        }
    }
}
Write-Host 'Done.'
