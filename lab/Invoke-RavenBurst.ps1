<#
.SYNOPSIS
  RAVEN lab: safe file-creation burst. Run INSIDE the lab VM only.
.DESCRIPTION
  Starts one benign PowerShell child process (this same script with -Worker).
  The child creates a fixed number of small text files with the test extension
  .raventest in C:\RavenLab\burst, spread over a fixed number of seconds.
  Sysmon records one process creation (event 1) and many file creations (event 11)
  for the child's process ID: the telemetry that rules RAVEN-R001 and RAVEN-R003 look for.
  The files hold one short text line. Nothing is read, encrypted, changed or deleted.
  The target folder is fixed and cannot be changed from the command line.
.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File \\VBoxSvr\raven_lab\Invoke-RavenBurst.ps1
#>
[CmdletBinding()]
param(
    [ValidateRange(10, 500)][int]$Count = 60,
    [ValidateRange(5, 300)][int]$DurationSeconds = 30,
    [switch]$Worker
)

$ErrorActionPreference = 'Stop'
$TargetDir = 'C:\RavenLab\burst'
$Extension = '.raventest'

function Assert-LabVm {
    foreach ($serviceName in @('VBoxService', 'Sysmon*')) {
        if (-not (Get-Service -Name $serviceName -ErrorAction SilentlyContinue)) {
            throw "Refusing to run: service '$serviceName' not found. This script runs only inside the RAVEN lab VM (Guest Additions and Sysmon installed)."
        }
    }
}
Assert-LabVm

if ($Worker) {
    $null = New-Item -ItemType Directory -Path $TargetDir -Force
    $delayMs = [int](($DurationSeconds * 1000) / $Count)
    for ($i = 1; $i -le $Count; $i++) {
        $file = Join-Path $TargetDir ('burst_{0:D4}{1}' -f $i, $Extension)
        Set-Content -LiteralPath $file -Value ('RAVEN lab test file {0} of {1}' -f $i, $Count) -Encoding ascii
        Start-Sleep -Milliseconds $delayMs
    }
    exit 0
}

$null = New-Item -ItemType Directory -Path $TargetDir -Force
$before = @(Get-ChildItem -LiteralPath $TargetDir -File | Where-Object { $_.Extension -eq $Extension }).Count
$started = Get-Date
$psExe = Join-Path $PSHOME 'powershell.exe'
$argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"{0}"' -f $PSCommandPath), '-Worker', '-Count', $Count, '-DurationSeconds', $DurationSeconds)
$child = Start-Process -FilePath $psExe -ArgumentList $argList -WindowStyle Hidden -Wait -PassThru
$after = @(Get-ChildItem -LiteralPath $TargetDir -File | Where-Object { $_.Extension -eq $Extension }).Count

'Burst finished.'
'Worker PID:       {0}' -f $child.Id
'Worker exit code: {0}' -f $child.ExitCode
'Files created:    {0}' -f ($after - $before)
'Files in folder:  {0}' -f $after
'Started (UTC):    {0}' -f $started.ToUniversalTime().ToString('o')
'Finished (UTC):   {0}' -f (Get-Date).ToUniversalTime().ToString('o')