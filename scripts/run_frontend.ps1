<#
.SYNOPSIS
    Starts the RAVEN frontend (dev server on http://localhost:5173) in this window.
.DESCRIPTION
    The dev server forwards /api to the backend on port 8000, so the backend must be running too
    (scripts\run_backend.ps1, or use scripts\run_all.ps1 to start both).
    The first time, and whenever node_modules is missing, it installs the packages with "npm ci".
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$frontend = Join-Path $root 'frontend'

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw 'Node.js was not found. Install Node.js 20 or newer, then open a new PowerShell window.'
}
if (-not (Test-Path -LiteralPath (Join-Path $frontend 'package.json'))) {
    throw "The frontend folder was not found at $frontend."
}

Push-Location $frontend
try {
    if (-not (Test-Path -LiteralPath (Join-Path $frontend 'node_modules'))) {
        Write-Host 'Installing the frontend packages (npm ci). This takes a minute the first time.'
        npm ci
        if ($LASTEXITCODE -ne 0) { throw 'npm ci failed.' }
    }
    Write-Host 'Starting the frontend on http://localhost:5173 (Ctrl+C stops it).'
    npm run dev
}
finally {
    Pop-Location
}
