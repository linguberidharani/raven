<#
.SYNOPSIS
  RAVEN lab: removes the test files created by the burst and stager scripts. Run INSIDE the lab VM only.
.DESCRIPTION
  Deletes only files with the extension .raventest inside C:\RavenLab\burst and C:\RavenLab\stager.
  Nothing else is touched. Use -WhatIf to see what would be removed.
.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File \\VBoxSvr\raven_lab\Invoke-RavenCleanup.ps1
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param()

$ErrorActionPreference = 'Stop'
$Extension = '.raventest'
$Folders = @('C:\RavenLab\burst', 'C:\RavenLab\stager')

function Assert-LabVm {
    foreach ($serviceName in @('VBoxService', 'Sysmon*')) {
        if (-not (Get-Service -Name $serviceName -ErrorAction SilentlyContinue)) {
            throw "Refusing to run: service '$serviceName' not found. This script runs only inside the RAVEN lab VM (Guest Additions and Sysmon installed)."
        }
    }
}
Assert-LabVm

$removed = 0
foreach ($folder in $Folders) {
    if (-not (Test-Path -LiteralPath $folder)) { continue }
    $files = @(Get-ChildItem -LiteralPath $folder -File | Where-Object { $_.Extension -eq $Extension })
    foreach ($file in $files) {
        if ($PSCmdlet.ShouldProcess($file.FullName, 'Remove test file')) {
            Remove-Item -LiteralPath $file.FullName
            $removed++
        }
    }
}
'Removed {0} test file(s) from: {1}' -f $removed, ($Folders -join ', ')