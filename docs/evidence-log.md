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