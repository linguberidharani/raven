# RAVEN VM collector

`Invoke-RavenCollector.ps1` runs inside the lab VM and copies new Sysmon events to the shared inbox
(`\\VBoxSvr\raven_inbox`, on the host `D:\Projects\RAVEN\data\inbox`) as raw JSONL records, one per line:
`event_id`, `time_created`, `computer`, `record_id`, `event_data`, `raw_xml` (spec section 6.1).

- It refuses to run on the host (no VBoxService) and needs a PowerShell window started as Administrator.
- It reads only the Sysmon log, only events newer than the saved record ID (`C:\RavenLab\collector-state.json`).
- One pass writes all its lines in one append, so the host never sees a half-written line.
- `-FromNow` skips the events already in the log on the first start. `-Once` does one pass and stops.
  `-Reset` forgets the state (everything is sent again; the host ignores records it already has).

Start it in the VM (Administrator PowerShell):

    powershell -ExecutionPolicy Bypass -File \\VBoxSvr\raven_lab\Invoke-RavenCollector.ps1 -FromNow

Check the file on the host (needs the venv):

    python -m raven.collectors.inbox D:\Projects\RAVEN\data\inbox\sysmon-<COMPUTERNAME>.jsonl

On the host, link the file to an investigation (`POST /api/investigations/{id}/collector`). The API then reads new
lines every few seconds (`RAVEN_INBOX_POLL_SECONDS`) and runs the analysis again by itself.
