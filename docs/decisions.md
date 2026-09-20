# RAVEN decisions

Confirmed by the owner on 2026-09-20 (spec Appendix B).

| ID | Decision | Choice |
|---|---|---|
| D1 | Workspace model | One SQLite database per investigation plus a registry database |
| D2 | Frontend language | JavaScript |
| D3 | Processing stages S2 to S10 | Rebuilt from the spec (the old code is deleted) |
| D4 | Real-time transport | VM shared-folder JSONL plus polling |
| D5 | Session confidence | null |
| D6 | Authentication | Server-side session cookie |
| D7 | Scope | One VM and one host |
| D8 | Report delivery | On screen plus browser print |

## Environment

Windows 11 host, Python 3.11, Node.js LTS, PowerShell. Project folder D:\Projects\RAVEN. Windows 11 VM in VirtualBox with Sysmon installed. All old project folders are deleted.

## Reference dataset

The reference numbers in spec sections 6.3 and 6.5b apply only if the owner still has sysmon_export.evtx. Otherwise new baseline numbers are recorded at S2 from a fresh export from the VM.