# RAVEN evidence log

Real command outputs, counts and screenshots saved per stage (spec section 16).
Only real output is recorded here. Nothing is marked passed without it.

## Entry format

- Stage and date
- Commands run
- Where the real output is saved
- Result: passed or failed, with the reason if failed

## Entries

### S0 Workspace, 2026-09-21

- Host: Windows PowerShell 5.1.26100.9444, Python 3.11.9 (venv), Node v24.12.0, npm 11.12.0, git 2.53.0.windows.2
- Installed: pytest 9.1.1 (with colorama, iniconfig, packaging, pluggy, Pygments); `pip check` reported no broken requirements; exact versions in requirements.lock.txt
- `python -m pytest`: collected 0 items, exit code 5 (expected for an empty suite)
- `scripts\run_tests.ps1`: exit code 0 with the "0 tests" note
- `run_backend.ps1`, `run_frontend.ps1`, `run_all.ps1`: "not built yet" message, exit code 1 (expected until S11 and S15)
- Git: `.env` and `venv` are ignored; first commit tracked 45 files, 46 after `docs\RAVEN_MASTER_SPEC.md` was added; `git status` clean
- Result: passed

### S1 Telemetry lab, part 1 (Sysmon verified, VM recovered), 2026-09-21

- Sysmon on RAVEN-Windows-Lab: service running (automatic), HashingAlgorithms SHA256, network connection logging enabled, config file C:\Sysmon\sysmonconfig.xml (244 bytes, SHA256 8AB64C55DAD6EF7D1B89000F4FC6B4D48E815A9E346BE8AB21F6A329133D2410); the ProcessCreate, NetworkConnect and FileCreate rules are empty exclude lists
- Config copied byte-exact to lab\sysmon-config.xml (VM hash equals host hash, 244 bytes) and committed; .gitattributes keeps it -text
- Sysmon log checked on the VM: events 1, 3, 11 present; event 1 carries SHA256 in the Hashes field; unsupported IDs 4, 5, 16, 255 also present; log mode circular, 64 MB maximum
- Reference file found: D:\Backups\RAVEN_snapshot\data\raw_evtx\sysmon_export.evtx, 3215360 bytes (matches the size in the spec), so the spec reference numbers apply at S2
- Incident: cold boots of the VM showed a black screen (VirtualBox 7.2.16, host Windows 11 build 26200, VM with 2 CPUs, EFI, VBoxSVGA, NEM mode because VT-x was not available). The VirtualBox log of three cold boots ended at the EFI step DXE_AP with no Guest Additions report; a screenshot failed with resolution 0x0. Restoring snapshot Phase 1 Verified resumed normally (saved state) but a cold boot was still black
- Safety copy made before restoring: clone RAVEN-Windows-Lab-backup-2026-09-21 (32.6 GB). VirtualBox logs saved in D:\Backups\vbox-logs-2026-09-21
- Change made: VM CPUs 2 to 3 (VBoxManage modifyvm --cpus 3). Two cold boots afterwards reached Windows with Sysmon and VBoxService running
- Snapshot S1-cold-boot-ok-3cpu taken (VM powered off, 3 CPUs)
- Cause: not proven. The symptoms match forum reports of VirtualBox 7.2.x black screens with 2 CPUs; not confirmed for 7.2.16
- Rules from now on: do not restore Phase 1 Verified (it brings back 2 CPUs); close the VM with shutdown /s /t 0
- Still open in S1: host-only network, shared folder, safe scripts, run and verify events 1, 3, 11, final snapshot

### S1 Telemetry lab, part 2 (network, shares, lab scripts, Sysmon events), 2026-09-21

- Times below are UTC as recorded in the VM unless stated.
- Two more cold boots after the network and share changes also reached Windows (VM local times 23:27:59 and 23:38:44), so the VM cold-booted four times in a row with 3 CPUs.
- VM network: nic1 is host-only on VirtualBox Host-Only Ethernet Adapter (host 192.168.56.1/24, DHCP server range 192.168.56.101 to .254). The VM address is 192.168.56.101 and there is no default IPv4 route (route count 0), so the VM has no route to the internet. Guest Additions 7.2.16 match VirtualBox 7.2.16r174877 on the host.
- Shared folders: raven_inbox (read-write) maps to D:\Projects\RAVEN\data\inbox (the VM wrote a 19-byte file, the host read it, then removed it). raven_lab (read-only) maps to D:\Projects\RAVEN\lab (a write from the VM was refused with "The media is write protected"; the script hashes seen in the VM equal the host hashes).
- Lab scripts committed in lab\: Invoke-RavenBurst.ps1 SHA256 79A322769F6AAA3E456D0E20177F4CFB14E0CFF8D15DCAF24DB1DCF63CA88EC2, Invoke-RavenStager.ps1 SHA256 BE0DBFA571D8604CB03416775969B7B54A1409151024901C2FA60D4419F5A5F3, Invoke-RavenCleanup.ps1 SHA256 96D3E9330207394097921E81CB6DDEB512DE397A99FCBF85F6A389E94661848F. On the host all three refused to run (service VBoxService not found) and C:\RavenLab was not created.
- Burst, first run at 21:45 (worker PID 9164): the folder already held 60 .raventest files (Files created 0, Files in folder 60), and Sysmon recorded no file creation in the burst folder for that process (3 event 11 records, none in the folder). Guard added: burst and stager refuse to run when .raventest files already exist. Guard test in the VM: one leftover file in each folder, both scripts refused with exit code 1, cleanup removed 2. The first cleanup had removed 65 files (the 60 already present plus 5 stager files).
- Burst, second run at 21:51 in an empty folder (worker PID 8968): event 1 with command line "-Worker -Count 60 -DurationSeconds 30" and Hashes SHA256=0FF6F2C94BC7E2833A5F7E16DE1622E5DBA70396F31C7D5F56381870317E8C46, equal to Get-FileHash of powershell.exe; event 3: 0; event 11: 63 for this PID, 60 of them burst_0001.raventest to burst_0060.raventest in C:\RavenLab\burst (first 21:51:10.502, last 21:51:36.602, 26.1 s by event log time); the other 3 are PowerShell temp and profile files. Cleanup removed 60.
- Stager, run at 21:55 (worker PID 2344): event 1 with the same SHA256; event 3: 1 (tcp, initiated true, 127.0.0.1:49675 to 127.0.0.1:47001); event 11: 8 for this PID, 5 of them stager_001 to stager_005 in C:\RavenLab\stager. An earlier run at 21:46 (PID 2796) had the same shape (event 3: 1, 5 files in the folder). Cleanup removed 5.
- Result: events 1, 3 and 11 are visible in Microsoft-Windows-Sysmon/Operational for the lab activity. The SHA256 hash appears in event 1 only. Events 3 and 11 carry no Hashes field (seen in the fields printed on the VM), so the SHA256 requirement is met by event 1.
- Deviation from the spec: the stager test listener runs on 127.0.0.1 inside the VM instead of on the host-only network, to avoid host firewall changes. Sysmon logs the loopback connection.
- To check at S2 and S3 on real records: the event log time (TimeCreated) against UtcTime inside the event. In the stager run the connection event (21:55:21.220) was logged after the first file event (21:55:20.410) although the script connects before it creates files, and the burst file events spanned 26.1 s although the script sleeps 500 ms between 60 files. Cause not established.- Snapshot S1-lab-verified-poweroff taken with the VM powered off (3 CPUs, host-only network, both shares).
