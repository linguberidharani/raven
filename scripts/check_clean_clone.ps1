<#
.SYNOPSIS
    Proves that the documented commands work from a clean clone: clones the repository, builds a fresh Python
    environment, installs the requirements, and runs the backend tests and the frontend checks there.
.DESCRIPTION
    Only what is committed is in a clone, so this finds files that were forgotten. The reference EVTX file is not
    committed (it is git-ignored); the tests that need it are skipped in the clone unless -WithReference is given.
.PARAMETER Target
    Where the clone goes. Default: a folder in %TEMP%. An existing folder there is replaced.
.PARAMETER WithReference
    Copies tests\fixtures\sysmon_export.evtx into the clone, so the whole test suite runs.
.PARAMETER Keep
    Keeps the clone afterwards (by default it is deleted when everything passed).
#>
[CmdletBinding()]
param(
    [string]$Target = (Join-Path ([System.IO.Path]::GetTempPath()) 'raven-clean-clone'),
    [switch]$WithReference,
    [switch]$Keep
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$basePython = Join-Path $root 'venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $basePython)) { throw "The Python environment of the project was not found ($basePython)." }
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'git was not found.' }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw 'Node.js and npm were not found.' }

function Invoke-Step {
    param([string]$Title, [scriptblock]$Action)
    Write-Host "=== $Title" -ForegroundColor Cyan
    & $Action
    if ($LASTEXITCODE -ne 0) { throw "Step failed: $Title" }
}

if (Test-Path -LiteralPath $Target) { Remove-Item -LiteralPath $Target -Recurse -Force }
$uncommitted = git -C $root status --short
if ($uncommitted) {
    Write-Host 'Note: these changes are not committed, so they are NOT in the clone:' -ForegroundColor Yellow
    $uncommitted | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
}

Invoke-Step 'Clone the repository' { git clone --quiet $root $Target }
Push-Location $Target
try {
    if ($WithReference) {
        $reference = Join-Path $root 'tests\fixtures\sysmon_export.evtx'
        New-Item -ItemType Directory -Force -Path (Join-Path $Target 'tests\fixtures') | Out-Null
        Copy-Item -LiteralPath $reference -Destination (Join-Path $Target 'tests\fixtures\sysmon_export.evtx')
        Write-Host 'The reference EVTX file was copied into the clone.'
    }
    $python = Join-Path $Target 'venv\Scripts\python.exe'
    Invoke-Step 'Create a new Python environment' { & $basePython -m venv (Join-Path $Target 'venv') }
    Invoke-Step 'Install the requirements' { & $python -m pip install --quiet -r requirements.txt -r requirements-dev.txt }
    Invoke-Step 'pip check' { & $python -m pip check }
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
    Invoke-Step 'Backend tests (pytest)' { & $python -m pytest -q }
    Push-Location (Join-Path $Target 'frontend')
    try {
        Invoke-Step 'Install the frontend packages (npm ci)' { npm ci --no-audit --no-fund }
        Invoke-Step 'Frontend lint' { npm run lint }
        Invoke-Step 'Frontend unit tests' { npm test }
        Invoke-Step 'Frontend build' { npm run build }
    }
    finally {
        Pop-Location
    }
    $dirty = git status --short
    if ($dirty) {
        Write-Host 'The checks changed tracked files in the clone (they should not):' -ForegroundColor Yellow
        $dirty | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
    }
}
finally {
    Pop-Location
}

Write-Host ''
Write-Host 'The clean clone works: the requirements install, the tests pass, the frontend builds.' -ForegroundColor Green
if ($Keep) {
    Write-Host "The clone was kept at $Target."
}
else {
    Remove-Item -LiteralPath $Target -Recurse -Force
    Write-Host 'The clone was deleted.'
}
