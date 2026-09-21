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

## Design choices made in S3 and S4 (2026-09-21)

- timestamp: the record time (TimeCreated), UTC, milliseconds cut off (not rounded). The Sysmon UtcTime is not used; it stays in event_data and raw_xml. Reason: on the reference data 132 events carry a UtcTime about 3.5 hours after the record time, and the spec time range and the spec example group ID follow the record time.
- raw_event_ref: "<evidence_id>:<record_id>" with a numeric evidence ID.
- Status INVALID_EVENT_DATA: a supported event (1, 3, 11) with a missing required field or an unreadable number or true/false value. It is still stored. The reference data has none.
- Unsupported events keep only identity fields (reference, event ID, type, timestamp, computer, status). Two of them with the same event ID and millisecond are duplicates in deduplication.
- Empty text values are stored as null. Extracted hashes are upper case.
- Deduplication fingerprint: the 26 fields other than raw_event_ref; the first event is kept; a duplicates file records every removal.
- Database: timestamps are stored as text (2026-09-13T08:39:49.545Z); raw_event_ref, timestamp and computer are NOT NULL; extra indexes on timestamp and on (event_type, process_id); foreign keys are enforced.