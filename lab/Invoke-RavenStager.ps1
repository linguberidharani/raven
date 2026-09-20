<#
.SYNOPSIS
  RAVEN lab: safe "stager-like" pattern. Run INSIDE the lab VM only.
.DESCRIPTION
  This launcher opens a test listener on a loopback or private address inside the VM, then starts
  one benign PowerShell child process (this same script with -Worker). The child makes ONE connection
  to the listener, then creates a few small text files with the test extension .raventest in
  C:\RavenLab\stager.
  Sysmon records a process creation (event 1), a network connection (event 3) and file creations
  (event 11) for the child's process ID: the telemetry that rule RAVEN-R002 looks for.
  Only loopback or private addresses are accepted. No external system is contacted.
  Nothing is downloaded, executed, encrypted, changed or deleted.
.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File \\VBoxSvr\raven_lab\Invoke-RavenStager.ps1
#>
[CmdletBinding()]
param(
    [string]$Address = '127.0.0.1',
    [ValidateRange(1024, 65535)][int]$Port = 47001,
    [ValidateRange(1, 50)][int]$FileCount = 5,
    [switch]$Worker
)

$ErrorActionPreference = 'Stop'
$TargetDir = 'C:\RavenLab\stager'
$Extension = '.raventest'

function Assert-LabVm {
    foreach ($serviceName in @('VBoxService', 'Sysmon*')) {
        if (-not (Get-Service -Name $serviceName -ErrorAction SilentlyContinue)) {
            throw "Refusing to run: service '$serviceName' not found. This script runs only inside the RAVEN lab VM (Guest Additions and Sysmon installed)."
        }
    }
}

function Test-PrivateAddress {
    param([string]$Text)
    $ip = $null
    if (-not [System.Net.IPAddress]::TryParse($Text, [ref]$ip)) { return $false }
    if ($ip.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) { return $false }
    $b = $ip.GetAddressBytes()
    return (($b[0] -eq 127) -or ($b[0] -eq 10) -or (($b[0] -eq 172) -and ($b[1] -ge 16) -and ($b[1] -le 31)) -or (($b[0] -eq 192) -and ($b[1] -eq 168)))
}

Assert-LabVm
if (-not (Test-PrivateAddress $Address)) {
    throw "Refusing to run: '$Address' is not a loopback or private IPv4 address."
}

if ($Worker) {
    $client = [System.Net.Sockets.TcpClient]::new()
    $client.Connect($Address, $Port)
    $stream = $client.GetStream()
    $stream.ReadTimeout = 10000
    $hello = [System.Text.Encoding]::ASCII.GetBytes("RAVEN-LAB-STAGER-HELLO`n")
    $stream.Write($hello, 0, $hello.Length)
    $buffer = New-Object byte[] 64
    $null = $stream.Read($buffer, 0, $buffer.Length)
    $client.Close()

    $null = New-Item -ItemType Directory -Path $TargetDir -Force
    for ($i = 1; $i -le $FileCount; $i++) {
        $file = Join-Path $TargetDir ('stager_{0:D3}{1}' -f $i, $Extension)
        Set-Content -LiteralPath $file -Value ('RAVEN lab stager file {0} of {1}' -f $i, $FileCount) -Encoding ascii
        Start-Sleep -Seconds 1
    }
    exit 0
}

$null = New-Item -ItemType Directory -Path $TargetDir -Force
$existing = @(Get-ChildItem -LiteralPath $TargetDir -File | Where-Object { $_.Extension -eq $Extension }).Count
if ($existing -gt 0) { throw "$TargetDir already holds $existing $Extension file(s). Run Invoke-RavenCleanup.ps1 first: Sysmon logs file creation, so a run over existing files leaves no file-creation events." }
$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Parse($Address), $Port)
$listener.Start()
$banner = ''
try {
    $psExe = Join-Path $PSHOME 'powershell.exe'
    $argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"{0}"' -f $PSCommandPath), '-Worker', '-Address', $Address, '-Port', $Port, '-FileCount', $FileCount)
    $child = Start-Process -FilePath $psExe -ArgumentList $argList -WindowStyle Hidden -PassThru
    $null = $child.Handle
    $deadline = (Get-Date).AddSeconds(30)
    while (-not $listener.Pending()) {
        if ((Get-Date) -gt $deadline) { throw 'No connection from the worker within 30 seconds.' }
        Start-Sleep -Milliseconds 100
    }
    $accepted = $listener.AcceptTcpClient()
    $stream = $accepted.GetStream()
    $stream.ReadTimeout = 10000
    $buffer = New-Object byte[] 256
    $read = $stream.Read($buffer, 0, $buffer.Length)
    $banner = [System.Text.Encoding]::ASCII.GetString($buffer, 0, $read).Trim()
    $reply = [System.Text.Encoding]::ASCII.GetBytes("OK`n")
    $stream.Write($reply, 0, $reply.Length)
    $accepted.Close()
}
finally {
    $listener.Stop()
}
$child.WaitForExit()

'Stager finished.'
'Worker PID:       {0}' -f $child.Id
'Worker exit code: {0}' -f $child.ExitCode
'Listener:         {0}:{1}' -f $Address, $Port
'Banner received:  {0}' -f $banner
'Files in folder:  {0}' -f @(Get-ChildItem -LiteralPath $TargetDir -File | Where-Object { $_.Extension -eq $Extension }).Count