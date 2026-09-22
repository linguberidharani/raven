<#
.SYNOPSIS
    RAVEN VM collector: copies new Sysmon events to the shared inbox as raw JSONL records.

.DESCRIPTION
    Runs INSIDE the RAVEN lab VM (it refuses to run anywhere else). Every few seconds it reads the Sysmon events that are
    newer than the last saved record ID and appends them, one JSON object per line, to
        <InboxPath>\sysmon-<COMPUTERNAME>.jsonl
    The record has the shape of a RAVEN raw record: event_id, time_created, computer, record_id, event_data, raw_xml.
    On the host, the RAVEN inbox watcher reads only the new complete lines, so a line is always written in one piece.
    Nothing else is read or changed on the VM. The state (the last record ID) is kept in StatePath.
    If the state is lost, events are simply sent again; the host ignores records it already has.

.PARAMETER InboxPath
    The shared folder that the host reads. Default \\VBoxSvr\raven_inbox (read/write shared folder raven_inbox).

.PARAMETER StatePath
    Where the last sent record ID is saved. Default C:\RavenLab\collector-state.json.

.PARAMETER FromNow
    On the first start, skip the events that are already in the log and send only new ones.

.PARAMETER Once
    Do one pass (until there is nothing new) and stop, instead of watching.

.PARAMETER Reset
    Forget the saved state (all events of the log are sent again).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File \\VBoxSvr\raven_lab\Invoke-RavenCollector.ps1 -FromNow
#>
[CmdletBinding()]
param(
    [string]$InboxPath = '\\VBoxSvr\raven_inbox',
    [string]$StatePath = 'C:\RavenLab\collector-state.json',
    [string]$LogName = 'Microsoft-Windows-Sysmon/Operational',
    [ValidateRange(1, 3600)][int]$IntervalSeconds = 5,
    [ValidateRange(1, 5000)][int]$MaxEventsPerPass = 500,
    [switch]$FromNow,
    [switch]$Once,
    [switch]$Reset
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

function Assert-LabVm {
    if (-not (Get-Service -Name 'VBoxService' -ErrorAction SilentlyContinue)) {
        throw 'This collector runs only inside the RAVEN lab VM (VBoxService was not found). Refusing to run here.'
    }
    $principal = New-Object System.Security.Principal.WindowsPrincipal([System.Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $principal.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Run this in a PowerShell window that was started as Administrator (the Sysmon log needs it).'
    }
    if (-not (Test-Path -LiteralPath $InboxPath -PathType Container)) {
        throw "The inbox folder was not found: $InboxPath (is the shared folder raven_inbox available?)"
    }
}

function Get-SourceFileName {
    $name = ('sysmon-' + $env:COMPUTERNAME + '.jsonl') -replace '[^A-Za-z0-9._-]', '-'
    return $name
}

function Read-LastRecordId {
    if (-not (Test-Path -LiteralPath $StatePath)) { return $null }
    try {
        $state = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
        return [long]$state.last_record_id
    }
    catch {
        Write-Warning "The state file could not be read ($StatePath); events will be sent again."
        return $null
    }
}

function Save-LastRecordId([long]$RecordId) {
    $folder = Split-Path -Parent $StatePath
    if (-not (Test-Path -LiteralPath $folder)) { New-Item -ItemType Directory -Path $folder -Force | Out-Null }
    $temporary = $StatePath + '.tmp'
    $json = (@{ last_record_id = $RecordId } | ConvertTo-Json -Compress)
    [System.IO.File]::WriteAllText($temporary, $json, (New-Object System.Text.UTF8Encoding($false)))
    Move-Item -LiteralPath $temporary -Destination $StatePath -Force
}

function ConvertTo-RawRecordLine($EventRecord) {
    $xmlText = $EventRecord.ToXml()
    $xml = New-Object System.Xml.XmlDocument
    $xml.LoadXml($xmlText)
    $ns = New-Object System.Xml.XmlNamespaceManager($xml.NameTable)
    $ns.AddNamespace('e', 'http://schemas.microsoft.com/win/2004/08/events/event')
    $system = $xml.SelectSingleNode('/e:Event/e:System', $ns)
    $data = [ordered]@{}
    foreach ($item in $xml.SelectNodes('/e:Event/e:EventData/e:Data', $ns)) {
        $dataName = $item.GetAttribute('Name')
        if (-not [string]::IsNullOrEmpty($dataName)) { $data[$dataName] = [string]$item.InnerText }
    }
    $record = [ordered]@{
        event_id     = [int]$system.SelectSingleNode('e:EventID', $ns).InnerText
        time_created = [string]$system.SelectSingleNode('e:TimeCreated', $ns).GetAttribute('SystemTime')
        computer     = [string]$system.SelectSingleNode('e:Computer', $ns).InnerText
        record_id    = [long]$system.SelectSingleNode('e:EventRecordID', $ns).InnerText
        event_data   = $data
        raw_xml      = [string]$xmlText
    }
    return ($record | ConvertTo-Json -Compress -Depth 4)
}

function Get-NewEvents([long]$After) {
    try {
        return @(Get-WinEvent -LogName $LogName -FilterXPath ("*[System[EventRecordID > " + $After + "]]") -Oldest -MaxEvents $MaxEventsPerPass -ErrorAction Stop)
    }
    catch {
        if ($_.Exception.Message -like '*No events were found*') { return @() }
        throw
    }
}

function Invoke-Pass {
    $last = Read-LastRecordId
    if ($null -eq $last) {
        if ($FromNow) {
            $newest = @(Get-WinEvent -LogName $LogName -MaxEvents 1 -ErrorAction SilentlyContinue)
            $last = if ($newest.Count -gt 0) { [long]$newest[0].RecordId } else { 0 }
            Save-LastRecordId $last
            Write-Host ("Starting after record ID {0} (only new events are sent)." -f $last)
        }
        else {
            $last = 0
        }
    }
    $events = @(Get-NewEvents $last)
    if ($events.Count -eq 0) { return 0 }

    $lines = New-Object System.Collections.Generic.List[string]
    $highest = $last
    foreach ($eventRecord in $events) {
        $lines.Add((ConvertTo-RawRecordLine $eventRecord))
        if ([long]$eventRecord.RecordId -gt $highest) { $highest = [long]$eventRecord.RecordId }
    }
    $file = Join-Path $InboxPath (Get-SourceFileName)
    $text = ($lines -join "`n") + "`n"
    [System.IO.File]::AppendAllText($file, $text, (New-Object System.Text.UTF8Encoding($false)))
    Save-LastRecordId $highest
    Write-Host ("[{0}] wrote {1} events (record IDs {2} to {3}) to {4}" -f (Get-Date -Format 'HH:mm:ss'), $events.Count, ([long]$events[0].RecordId), $highest, $file)
    return $events.Count
}

Assert-LabVm
if ($Reset -and (Test-Path -LiteralPath $StatePath)) { Remove-Item -LiteralPath $StatePath -Force }
Write-Host ("RAVEN collector: log '{0}' -> {1}" -f $LogName, (Join-Path $InboxPath (Get-SourceFileName)))
if (-not $Once) { Write-Host 'Watching. Press Ctrl+C to stop.' }

while ($true) {
    $count = Invoke-Pass
    if ($count -ge $MaxEventsPerPass) { continue }
    if ($Once) { break }
    Start-Sleep -Seconds $IntervalSeconds
}
if ($Once) { Write-Host 'Done: nothing new to send.' }
