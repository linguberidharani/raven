<#
.SYNOPSIS
    Runs the tests of RAVEN: the backend (pytest) and the frontend (lint, unit tests, build).
.PARAMETER Backend
    Only the backend tests.
.PARAMETER Frontend
    Only the frontend checks.
#>
[CmdletBinding()]
param(
    [switch]$Backend,
    [switch]$Frontend
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$both = -not ($Backend -or $Frontend)
$failed = @()

if ($Backend -or $both) {
    $python = Join-Path $root 'venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python)) { throw "The Python environment was not found ($python)." }
    Write-Host '=== Backend: pytest' -ForegroundColor Cyan
    Push-Location $root
    try {
        & $python -m pytest -q
        if ($LASTEXITCODE -ne 0) { $failed += 'backend tests' }
    }
    finally {
        Pop-Location
    }
}

if ($Frontend -or $both) {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw 'Node.js and npm were not found.' }
    Push-Location (Join-Path $root 'frontend')
    try {
        if (-not (Test-Path -LiteralPath 'node_modules')) { npm ci; if ($LASTEXITCODE -ne 0) { throw 'npm ci failed.' } }
        foreach ($step in @(@('lint', 'run lint'), @('unit tests', 'test'), @('build', 'run build'))) {
            Write-Host "=== Frontend: $($step[0])" -ForegroundColor Cyan
            Invoke-Expression "npm $($step[1])"
            if ($LASTEXITCODE -ne 0) { $failed += "frontend $($step[0])" }
        }
    }
    finally {
        Pop-Location
    }
}

if ($failed.Count -gt 0) {
    Write-Host ('FAILED: ' + ($failed -join ', ')) -ForegroundColor Red
    exit 1
}
Write-Host 'All checks passed.' -ForegroundColor Green
