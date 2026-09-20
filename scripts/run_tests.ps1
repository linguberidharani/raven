<#
.SYNOPSIS
  Runs the RAVEN test suite with the project virtual environment.
.EXAMPLE
  .\scripts\run_tests.ps1
  .\scripts\run_tests.ps1 -m "not slow"
#>
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root 'venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $Python)) {
    Write-Host "Virtual environment not found: $Python" -ForegroundColor Red
    Write-Host "Create it from the project root: python -m venv venv" -ForegroundColor Red
    exit 1
}

Set-Location $Root
& $Python -m pytest @args
$code = $LASTEXITCODE

# pytest exits with 5 when it collects no tests. Accepted only while the suite is empty (S0 to S1).
if ($code -eq 5) {
    Write-Host "pytest collected 0 tests (exit code 5). Expected until the first tests arrive in S2." -ForegroundColor Yellow
    exit 0
}
exit $code