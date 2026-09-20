<#
.SYNOPSIS
  Starts the RAVEN backend API on http://127.0.0.1:8000 (available from stage S11).
#>
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root 'venv\Scripts\python.exe'
$AppFile = Join-Path $Root 'raven\api\main.py'

if (-not (Test-Path -LiteralPath $Python)) {
    Write-Host "Virtual environment not found: $Python" -ForegroundColor Red
    Write-Host "Create it from the project root: python -m venv venv" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path -LiteralPath $AppFile)) {
    Write-Host "Backend API is not built yet (raven\api\main.py arrives in stage S11)." -ForegroundColor Yellow
    exit 1
}

Set-Location $Root
# --reload-dir raven watches source code only, never data\ (pipeline writes must not restart the server).
& $Python -m uvicorn raven.api.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir raven
exit $LASTEXITCODE