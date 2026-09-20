<#
.SYNOPSIS
  Starts the backend and the frontend, each in its own PowerShell window.
#>
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $PSScriptRoot 'run_backend.ps1'
$Frontend = Join-Path $PSScriptRoot 'run_frontend.ps1'

if (-not (Test-Path -LiteralPath (Join-Path $Root 'raven\api\main.py'))) {
    Write-Host "Backend is not built yet (stage S11). Nothing started." -ForegroundColor Yellow
    exit 1
}
if (-not (Test-Path -LiteralPath (Join-Path $Root 'frontend\package.json'))) {
    Write-Host "Frontend is not built yet (stage S15). Nothing started." -ForegroundColor Yellow
    exit 1
}

$PowerShellExe = (Get-Process -Id $PID).Path
foreach ($Target in @($Backend, $Frontend)) {
    Start-Process -FilePath $PowerShellExe -ArgumentList @('-NoExit', '-ExecutionPolicy', 'Bypass', '-File', "`"$Target`"")
}
Write-Host "Backend:  http://127.0.0.1:8000"
Write-Host "Frontend: http://127.0.0.1:5173"