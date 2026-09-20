<#
.SYNOPSIS
  Starts the RAVEN frontend dev server on http://127.0.0.1:5173 (available from stage S15).
#>
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$FrontendDir = Join-Path $Root 'frontend'

if (-not (Test-Path -LiteralPath (Join-Path $FrontendDir 'package.json'))) {
    Write-Host "Frontend is not built yet (frontend\package.json arrives in stage S15)." -ForegroundColor Yellow
    exit 1
}

Set-Location $FrontendDir
# npm.cmd avoids the npm.ps1 execution-policy block in new windows.
& npm.cmd run dev
exit $LASTEXITCODE