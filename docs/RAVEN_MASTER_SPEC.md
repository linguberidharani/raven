# RAVEN: Master Specification (complete project, frontend + backend + processing)

**RAVEN: Ransomware Attack Visualization and Event Navigator.**
Tagline: **"Trace the Attack. Measure the Impact."**

Version 1.0 (19 to 20 September 2026). This document is the single source of truth for rebuilding RAVEN from the beginning to the end.
It merges everything the owner specified (frontend design prompt, project-alignment prompt, backend master prompt) with facts that were verified on the owner's real machine during the first implementation.

How to read it:
- Sections marked **DECISION** need the owner's confirmation before the stage that uses them.
- Sections marked **VERIFIED** come from the first implementation on the owner's machine (real outputs).
- Sections marked **PROPOSED** are new design choices made in this document.

---

## 0. How the rebuild is done

1. The build is split into stages S0 to S17 (section 12). **One stage at a time.**
2. Every stage delivers complete files, exact Windows PowerShell commands, expected output, verification commands and tests.
3. The owner runs the commands and brings back the REAL output. Nothing is marked "passed" without real output.
4. If a step fails: stop, diagnose, fix, re-verify. Never continue past a failure.
5. Every command is labelled **[WINDOWS HOST]** or **[WINDOWS 11 VM]**. PowerShell only. No Linux commands.
6. Start every new chat with the block in section 17, so the assistant has full context.

---

## 1. Identity and scope

**RAVEN is** a defensive cybersecurity investigation platform. It takes real Sysmon telemetry from an isolated Windows 11 VM, processes it deterministically, and lets an analyst reconstruct and understand a ransomware-style incident:

- What happened? How did it happen?
- Which processes, files and network connections were involved?
- What was the impact?
- Which evidence supports every conclusion, all the way back to the raw Sysmon record?

**RAVEN is NOT and never claims to be:**
- an encryption or decryption tool (it never encrypts or decrypts anything)
- antivirus, EDR, or real-time protection; it never stops or blocks an attack
- a generative-AI system; no AI invents findings, intent or impact
- a platform that uses mock data as if it were telemetry

Ransomware behaviour (for example many files created with a new extension) may appear ONLY as an **observed incident event** or a **derived interpretation** inside an investigation.

**Users:** security analysts (one or many accounts). **Scale for v1:** one lab VM, one host machine, thousands to hundreds of thousands of events per investigation.

**Environment:**
- Host: Windows, Python 3.11, Node.js (LTS), PowerShell. Development happens here.
- Lab: Windows 11 VM in Oracle VirtualBox, isolated, with Sysmon. It is the only telemetry source.

---

## 2. Non-negotiable rules

1. **Evidence first.** Evidence, then analysis, then interpretation. Never assumption first and evidence later.
2. **No fabrication.** No fake telemetry, detections, impact numbers, database fields or report statements. Demo/test data is allowed only in clearly separated demo/test locations and is never presented as real.
3. **Deterministic.** Same input gives the same output (correlation, reconstruction, timeline, impact, RARF, report). No randomness, no network calls, no generative AI in the analysis path.
4. **Traceability.** Every result links back: report statement, finding, correlation group, normalized event, raw event, original Sysmon record (`raw_xml`).
5. **Observed vs derived.** Every statement and every UI element that shows information is labelled either **OBSERVED EVIDENCE** (recorded in the logs, or a direct count of recorded events) or **DERIVED / INTERPRETED** (concluded by RAVEN from observed events).
6. **No claims about attacker intent, malware identity, data exfiltration or full encryption** unless such evidence is explicitly present.
7. **No invented business or financial impact.**
8. **Safe lab.** Only harmless processes, safe file bursts, controlled local connections and synthetic activity inside the VM. No real ransomware or destructive payloads. No attacks on external systems.
9. **Security basics.** No plaintext passwords. No secrets in source code. `.env` is never committed. Uploaded filenames are never used as filesystem paths. All IDs used in paths are validated.
10. **Terminology.** Forbidden in the product text unless describing an observed incident event: "encrypt files", "decrypt files", "encryption engine", "encryption service", "automatically detects and prevents ransomware", "real-time protection".
11. **Dependencies** are added only with a reason, an exact install command, a verification command, and an update to the requirements file.
12. **Frontend does not fake data.** When the backend has no data, the UI shows an honest empty state.

---

## 3. Architecture

```
 WINDOWS 11 VM (VirtualBox, isolated)                 WINDOWS HOST
 +-----------------------------------+                +------------------------------------------------------------+
 | Sysmon (events 1, 3, 11, SHA256)  |                |  backend\  (FastAPI, Python 3.11, one virtual environment) |
 | Windows Event Log                 |   EVTX upload  |   API layer      REST + auth + error format                |
 | Collector (PowerShell)  ----------+--------------->|   Services       orchestration, async analysis runs        |
 |   safe test-activity scripts      |  or shared     |   Processing     collect > normalize > dedupe > ingest     |
 +-----------------------------------+  folder (JSONL)|                  > correlate > detect > reconstruct        |
                                                      |                  > timeline > impact > RARF > report       |
                                                      |   Persistence    registry DB + one workspace per case      |
                                                      +----------------------------+-------------------------------+
                                                                                   | REST (JSON)
                                                      frontend\  (React, Vite)     |
                                                                                   v
                                                                                ANALYST
```

**Traceability chain (stored, never recomputed):**
`Report statement > Finding > Correlation group > Normalized event > Raw event > raw_xml`

**Investigation workspace (DECISION D1, recommended):** every investigation owns a workspace folder with its own SQLite database (`data\investigations\<id>\raven.db`) plus raw and processed files. A small **registry database** (`data\registry.db`) holds users, investigations, evidence sources and analysis runs. The API opens the right workspace by investigation ID. This reuses the analysis schema unchanged and isolates cases.
Alternative: one database with an `investigation_id` column everywhere (needs composite uniqueness on `raw_event_ref`; more schema changes).

---

## 4. Technology decisions

| Area | Choice | Why | Alternative |
|---|---|---|---|
| Language (backend) | Python 3.11 | Owner's environment, existing tooling | none |
| API framework | FastAPI + Uvicorn | Typed routes, OpenAPI docs, tests via TestClient | Flask |
| Settings | pydantic-settings | Typed env config, no hardcoded settings | plain os.environ |
| ORM / DB | SQLAlchemy 2.x + SQLite | Zero-install, file-based, one file per workspace | PostgreSQL (deferred) |
| EVTX parsing | python-evtx | Reads EVTX files in Python | Get-WinEvent on the VM |
| Rules | YAML files parsed with PyYAML | Human-readable, versionable rules | JSON |
| Uploads | python-multipart | Required by FastAPI for file uploads | none |
| Auth | Argon2 password hashing (argon2-cffi) + server-side session in an HttpOnly, SameSite=Lax cookie | No plaintext passwords; works with the Vite same-origin proxy | JWT bearer token (**DECISION D6**) |
| Tests | pytest, httpx | Deterministic tests, temp directories only | none |
| Frontend | React 18, Vite 5, React Router 6, Recharts, lucide-react, plain CSS with design tokens | The design the owner selected; no CSS framework | TypeScript (**DECISION D2**: JavaScript was used for the chosen design; TypeScript is welcome if the owner prefers typed API contracts) |
| Fonts | IBM Plex Sans and Mono (Google Fonts, system fallbacks) | Legible, forensic-tool look | self-hosted fonts |
| Real-time | Controlled polling (**DECISION D4**) | Lowest complexity for one VM | SSE, WebSocket (deferred) |

Not used unless a stage proves it is needed: Kafka, Redis, message queues, WebSockets, Docker.

---

## 5. Target repository layout

```
D:\Projects\RAVEN\
|-- README.md                      how to run everything
|-- .gitignore
|-- requirements.txt               runtime dependencies (pinned in requirements.lock.txt)
|-- requirements-dev.txt
|-- pytest.ini
|-- .env.example                   copy to .env (never commit .env)
|-- venv\                          ONE Python virtual environment for the whole backend
|-- scripts\                       run_backend.ps1, run_frontend.ps1, run_tests.ps1, run_all.ps1
|-- docs\                          this specification, API contract, evidence log
|-- lab\                           [VM] safe test-activity scripts, collector, Sysmon config copy
|-- raven\                         the Python package
|   |-- config.py  logging_config.py
|   |-- collectors\                evtx_loader.py, incremental collector reader
|   |-- parsers\                   schema.py, normalizer.py, deduplicate.py, time_utils.py, hash_utils.py
|   |-- database\                  models.py (analysis schema), registry_models.py, session.py, ingest.py
|   |-- correlation\               rule_schema.py, engine.py, persist.py, rules\*.yaml
|   |-- reconstruction\            sequencer.py, persist.py
|   |-- timeline\                  builder.py, persist.py
|   |-- impact\                    analyzer.py, persist.py
|   |-- rarf\                      schema.py, builder.py, exporter.py
|   |-- report\                    schema.py, evidence.py, generator.py
|   |-- services\                  workspace.py, investigations.py, pipeline.py, analysis_runs.py
|   `-- api\                       main.py, dependencies.py, errors.py, routes\*.py, schemas\*.py
|-- tests\                         mirrors raven\ (unit), plus api\, integration\, e2e\
|-- data\                          [GENERATED, not committed]
|   |-- registry.db
|   |-- inbox\                     shared-folder drop for the VM collector (JSONL)
|   `-- investigations\<id>\       raw\, processed\, raven.db, evidence\
|-- frontend\
|   |-- package.json  vite.config.js  index.html
|   `-- src\  main.jsx  App.jsx  api\  hooks\  components\  pages\  styles\  demo\
`-- backups\                       (outside the repo; owner-managed)
```
The frontend lives beside the backend. Backend files are never placed inside `frontend\`.

---

## 6. Data specifications

### 6.1 Raw record (VERIFIED)
One JSON object per line in `raw\sysmon_events.jsonl`:
`event_id`, `time_created`, `computer`, `record_id`, `event_data`, `raw_xml`.
`raw_xml` is always preserved for traceability.

### 6.2 Normalized event, 27 fields (VERIFIED)
`raw_event_ref, event_id, event_type, timestamp, computer, process_guid, process_id, process_name, parent_process_guid, parent_process_id, parent_process_name, command_line, parent_command_line, user, integrity_level, hash_sha256, hash_md5, hash_imphash, hashes_raw, ip_address, port, source_ip, source_port, protocol, initiated, file_path, normalization_status`

Rules:
- `timestamp` is ISO-8601 UTC with milliseconds and a trailing `Z` (for example `2026-09-13T08:39:49.545Z`).
- `event_type`: Sysmon event 1 gives `process_creation`, 3 gives `network_connection`, 11 gives `file_create`. Every other event ID gives `unsupported` with `normalization_status = UNSUPPORTED_EVENT_ID`. **Unsupported events are retained, never dropped.** Supported ones have `normalization_status = OK`.
- `process_name` holds the full image path (VERIFIED).
- `raw_event_ref` (**PROPOSED change**): `"<evidence_id>:<record_id>"`, unique within an investigation. (In the first implementation it was the bare record ID, which collides across evidence files.)
- Hashes are parsed from the Sysmon `Hashes` field into `hash_sha256`, `hash_md5`, `hash_imphash`; the original text is kept in `hashes_raw`.

### 6.3 Deduplication (VERIFIED concept)
Deterministic fingerprint over the meaningful normalized fields (everything except the record-specific reference). Duplicates are removed from the deduplicated output; the removed count is reported. The exact fingerprint fields must be documented and unit-tested.
Reference dataset result: 2816 raw, 2816 normalized (1984 OK, 832 unsupported), 97 duplicates removed, 2719 unique, 0 remaining duplicate fingerprints. (The database of the first implementation held 2719 events: 1962 OK, 757 unsupported.)

### 6.4 Analysis database, 7 tables (VERIFIED)
Created per investigation workspace.

| Table | Columns |
|---|---|
| `events` | `id` (pk), the 27 normalized fields (`raw_event_ref` unique, indexed; `event_id`, `event_type`, `normalization_status` not null) |
| `correlation_rules` | `id`, `rule_name` (unique), `description`, `rule_definition` (JSON text), `enabled` |
| `correlated_events` | `id`, `rule_id` (fk), `event_id` (fk events), `correlation_group_id` (indexed), `correlation_type` |
| `attack_sessions` | `id`, `session_id` (unique), `start_time`, `end_time`, `description`, `severity`, `confidence` |
| `timeline_events` | `id`, `attack_session_id` (fk), `event_id` (fk), `sequence_number`, `timeline_timestamp`, `description` |
| `impact_analysis` | `id`, `attack_session_id` (fk), `impact_category`, `impact_score`, `affected_assets` (JSON text), `analysis` (JSON text) |
| `reports` | `id`, `attack_session_id` (fk), `report_title`, `report_text`, `generated_at` |

### 6.5 Registry database (PROPOSED, new)

| Table | Columns |
|---|---|
| `users` | `id`, `name`, `email` (unique), `organization`, `password_hash`, `created_at` |
| `sessions` | `id`, `user_id`, `token_hash`, `created_at`, `expires_at` |
| `investigations` | `id`, `code` (`INV-YYYY-NNN`), `title`, `description`, `host` (nullable), `status` (`open`, `active`, `closed`), `analyst_id`, `created_at`, `updated_at`, `workspace_dir` |
| `evidence_sources` | `id`, `investigation_id`, `filename`, `sha256`, `size_bytes`, `source_type` (`evtx_upload`, `vm_collector`), `status` (`uploaded`, `processing`, `ready`, `failed`), `events_total`, `error`, `created_at`, `ingested_at` |
| `analysis_runs` | `id`, `investigation_id`, `status` (`queued`, `running`, `completed`, `failed`), `stage`, `stages_json`, `error`, `started_at`, `finished_at` |
| `collector_cursors` | `id`, `investigation_id`, `source_name`, `last_offset`, `last_record_id`, `updated_at` |

Investigation severity is DERIVED: the highest severity among its attack sessions (none until analysis has run). Investigation "attack stage" is DERIVED from the latest analysis run stage.

### 6.5b Reference dataset numbers (for regression tests, VERIFIED)
Raw record count 2816. One attack session. 87 correlation groups (R001 19, R002 14, R003 54). 597 timeline events. Impact: files_affected 558 events / 475 distinct assets, network_activity 14 events / 12 destinations, process_activity 25 events / 14 images, unsupported_events 0. Computer name `Dharani`. Time range 2026-09-12T18:04:54Z to 2026-09-13T08:43:27Z. Raw evidence file `sysmon_export.evtx` (3,215,360 bytes). The owner keeps this file as a regression fixture.

### 6.6 Correlation rules (VERIFIED)
YAML, one file per rule, in `raven\correlation\rules\`:
```yaml
rule_id: "RAVEN-R001"
rule_name: "Mass File Modification Burst"
description: "..."
steps:
  - event_type: "process_creation"
    min_count: 1
  - event_type: "file_create"
    min_count: 5
match_key: "process_id"
time_window_seconds: 60
severity: "HIGH"          # HIGH | MEDIUM | LOW | INFO
confidence: 85
```
Shipped rules: **R001** Mass File Modification Burst (process_creation x1 then file_create x5 within 60 s, HIGH, 85), **R002** Process Network File Stager Pattern (process_creation, network_connection, file_create within 120 s, MEDIUM, 75), **R003** Sustained File Creation Burst (file_create x10 within 120 s, HIGH, 90). All match on `process_id`.
Test-only rules (for example `severity: TEST`) live in `tests\` fixtures, never in the shipped rules folder, and are never shown as findings.

Engine behaviour (deterministic): for each rule and each `match_key` value, order events by timestamp, find the ordered step sequence with the required counts inside the time window. Each hit becomes a **correlation group** with ID `"{rule_id}:{match_key_value}:{window_start_timestamp}"` (for example `RAVEN-R001:1224:2026-09-13T08:39:49.695Z`). Rows go to `correlated_events` (`correlation_type` = rule ID). Every group stores WHY it matched: the rule, the matched steps, the counts, the window.

### 6.7 Attack reconstruction (VERIFIED)
Groups are merged per computer: sort by start time; a group whose start is within `merge_gap_seconds` (default 300) of the current session end joins it. Session ID = `RAVEN-SESSION-{computer}-{first_group_id, non-alphanumerics replaced by "-"}`. Session severity = highest member severity. Description is generated deterministically ("Reconstructed attack session containing N correlation group(s) from rule(s): ..."). **DECISION D5:** `confidence` stays null (recommended, no unsupported claim) or becomes the maximum member-rule confidence. Reconstruction is DERIVED information.

### 6.8 Timeline (VERIFIED, improved)
All events belonging to the session's groups, unique, ordered by timestamp then event ID, numbered `sequence_number` from 1. **PROPOSED improvement:** `description` is generated from normalized fields, for example:
- process: `Process created: <image> (PID <pid>) by <user>; parent <parent image>`
- file: `File created: <path> by <image> (PID <pid>)`
- network: `Network connection: <image> to <ip>:<port>/<protocol>`
(The first implementation stored placeholders such as "Event 1403 (1475)", which the UI cannot show meaningfully.)

### 6.9 Impact (VERIFIED, semantics fixed)
Categories: `files_affected` (file_create events; assets = distinct `file_path`), `network_activity` (network events; assets = distinct `ip:port`; details include `protocols_seen`), `process_activity` (process_creation events; assets = distinct process image), `unsupported_events` (session events that are `unsupported`). Each row: `impact_score`, `affected_assets`, `analysis` = `{event_ids, raw_event_refs, event_count, details{distinct_computers, distinct_users, ...}}`.
**Score semantics (fixed by this spec):** `impact_score` = number of distinct affected assets (observed pattern in the reference data: 475, 12, 14). It is a DERIVED calculated metric. No monetary or business impact is ever computed. Delete-and-rebuild makes the analysis idempotent.

### 6.10 RARF v1.0 (VERIFIED)
One JSON file per session, `RARF-{session_id}.json`:
```
rarf_version, rarf_id ("RARF-<session_id>"),
attack_session { session_id, computer, start_time, end_time, severity, confidence, description },
detection { correlation_groups[ {correlation_group_id, correlation_type, event_ids[]} ], rules[ {rule_database_id, description, enabled, rule_definition ...} ], event_ids[] },
timeline { events[ {timeline_event_id, event_id, sequence_number, timestamp, raw_event_ref, event_type, computer, user} ] },
impact { categories { <name>: { impact_analysis_id, impact_score, affected_assets[], analysis{...} } } },
traceability { event_ids[], raw_event_refs[], correlation_group_ids[], timeline_event_ids[], impact_analysis_ids[] }
```
RARF never infers attacker intent, never detects, never recalculates impact; it only formalizes evidence already established. Only one RARF implementation exists in the project.

### 6.11 Report (VERIFIED, extended)
Deterministic controlled-language report built from RARF only. Structure: `report_title`, `attack_session_id`, `session_id`, `generated_at`, `sections[ {section_id, title, findings[ {statement, evidence{event_ids, correlation_group_ids, timeline_event_ids, impact_analysis_ids, raw_event_refs}} ]} ]`.
Sections: `executive_summary`, `session_overview`, `detection_evidence`, `timeline_summary`, `impact_analysis`, `evidence_traceability`, `confidence_limitations`.
**PROPOSED additions:**
- Every finding gets `basis`: `observed` (a direct fact or count of recorded events) or `derived` (RAVEN's conclusion, for example "consistent with ...").
- The UI presents two views built from these sections: **What happened?** (executive summary + session overview, short) and **How did it happen?** (ordered correlation groups + timeline milestones, technical).
- `generated_at` is set by the API when the report is requested and is excluded from the deterministic content.
- The `confidence_limitations` section always states that intent, malware identity, exfiltration and complete encryption are not established by the evidence.

---

## 7. Processing pipeline (module contracts)

Each module is a plain Python package with no web dependency, callable from the API service layer, and fully unit-tested with temporary directories (never the real `data\` folder).

| Stage | Module | Input | Output | Idempotent |
|---|---|---|---|---|
| Collect | `collectors.evtx_loader.load_evtx(input_evtx, output_jsonl)` | EVTX file | raw JSONL, returns record count | yes |
| Collect (incremental) | `collectors.inbox.read_new_records(path, cursor)` | JSONL dropped by the VM collector | new raw records + new cursor | yes (cursor + duplicate-safe ingest) |
| Normalize | `parsers.normalizer.normalize_record(raw)` and `normalize_all(in, out)` | raw JSONL | normalized JSONL (27 fields), returns totals and status counts | yes |
| Deduplicate | `parsers.deduplicate.deduplicate(in, out)` | normalized JSONL | deduplicated JSONL, returns (input, unique, removed) | yes |
| Ingest | `database.ingest.ingest_events(input, summary, session_factory)` | deduplicated JSONL | rows in `events`; skips existing `raw_event_ref` | yes |
| Correlate + detect | `correlation.engine` + `run_correlation(session_factory, summary_file)` | `events`, rules YAML | `correlation_rules`, `correlated_events`, summary | yes |
| Reconstruct | `reconstruction.sequencer` + runner | groups | `attack_sessions`, mapping file | yes (deterministic session IDs) |
| Timeline | `timeline.builder` / `persist` | session + its groups | `timeline_events` | yes (replace per session) |
| Impact | `impact.analyzer` / `persist` | timeline events | `impact_analysis` | yes (delete and rebuild) |
| RARF | `rarf.builder` / `exporter` | database rows | `RARF-<session_id>.json` | yes |
| Report | `report.evidence` + `report.generator` | RARF JSON | report document | yes (deterministic) |

Orchestration (`services.pipeline.run_full_pipeline`) runs these in order for one investigation workspace and records each stage in `analysis_runs.stages_json`. It never touches another workspace. It never writes outside the workspace.

Acceptance for the pipeline on the reference dataset: the numbers in 6.3 and 6.5b are reproduced exactly.

---

## 8. Backend API specification (PROPOSED, based on the frontend needs)

### 8.1 Conventions
- Base `http://127.0.0.1:8000`; all routes under `/api`. Legacy `GET /health` may remain for tooling.
- JSON, **snake_case** field names, timestamps ISO-8601 UTC ending in `Z`.
- Errors: `{"detail": <string or list>, "code": "<machine code>", "request_id": "<id>"}` with the correct HTTP status. `X-Request-ID` header on every response.
- Auth (stage S11): session cookie; every route except health, register and login requires it. Until then every route is documented "auth deferred" and the server binds to 127.0.0.1 only.
- Pagination: `?page=1&page_size=100` returning `{items, total, page, page_size}` for large lists (timeline, events).
- IDs in paths are validated (investigation IDs numeric; evidence and run IDs numeric; group IDs URL-encoded strings).
- The Vite dev server proxies `/api` to the backend, so the browser sees one origin.

### 8.2 Endpoints

| Method and path | Purpose | Source of truth | Frontend consumer |
|---|---|---|---|
| `GET /api/health` | Service and artifact status | settings | ops |
| `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me` | Accounts and session | registry `users`, `sessions` | Register, Login, shell |
| `GET /api/dashboard` | Totals, severity split, status split, recent investigations, alerts, recent activity, evidence queue | aggregates over registry and workspaces | Dashboard |
| `GET /api/investigations` (`?status=&severity=&q=`) | List | registry + derived severity/stage | Investigations |
| `POST /api/investigations` | Create (title, description) | registry | Investigations |
| `GET /api/investigations/{id}` | Header data: code, title, status, severity, stage, counts (evidence, detections, sessions, timeline events) | registry + workspace counts | case header |
| `GET /api/investigations/{id}/evidence` | Evidence items with status and counts, event-type breakdown | `evidence_sources`, `events` | Evidence |
| `POST /api/investigations/{id}/evidence` | Upload `.evtx` (multipart, max size configurable, extension checked, hashed with SHA-256) | filesystem + registry | Evidence |
| `POST /api/investigations/{id}/analysis` | Start analysis run (async, returns run ID) | pipeline | Evidence |
| `GET /api/investigations/{id}/analysis` | Latest run with per-stage status, for polling | `analysis_runs` | Evidence |
| `GET /api/investigations/{id}/detections` | Rules, correlation groups (rule, match key, window, event count, severity, confidence), and WHY each matched | `correlation_rules`, `correlated_events` | Detection |
| `GET /api/investigations/{id}/reconstruction` | Sessions with member groups ordered by time, process tree, evidence refs | `attack_sessions`, events | Reconstruction |
| `GET /api/investigations/{id}/timeline` (`?session=&event_type=&page=`) | Ordered events | `timeline_events` + `events` | Timeline |
| `GET /api/investigations/{id}/events/{event_ref}` | One event: normalized fields, raw fields, `raw_xml` | `events` + raw JSONL | Technical details drawer |
| `GET /api/investigations/{id}/impact` | Impact categories (observed counts and derived score) | `impact_analysis` | Impact |
| `GET /api/investigations/{id}/rarf` | The RARF JSON | RARF file | RARF |
| `GET /api/investigations/{id}/report` | Deterministic report (with `basis`) | report generator | Report |
| `GET /api/rules` | Shipped rule definitions | rules folder | Detection |

Request and response field lists for each endpoint are written in `docs\api-contract.md` at the start of the stage that builds it, from the real database columns in section 6, and are enforced by contract tests.

### 8.3 Real-time and analysis runs (DECISION D4)
Analysis runs asynchronously in a background worker thread inside the API process (one run per investigation at a time). The frontend polls `GET .../analysis` every 2 to 3 seconds while a run is active. New VM telemetry is picked up by the inbox watcher (section 10.3), which triggers an incremental run.

---

## 9. Frontend specification

### 9.1 Product feel
Professional cybersecurity investigation platform, dark, restrained, evidence-driven. SOC + digital forensics + incident reconstruction. **Not** a generic admin dashboard, not a gaming or cyberpunk interface. No heavy glow, no excessive gradients, no glassmorphism, no clutter, no unnecessary animation. Important information prominent, supporting information secondary, technical detail expandable.

### 9.2 Design system
- Colours (tokens in `styles\tokens.css`): background `#0a0e15`, surfaces `#121925` / `#17202e`, borders `#1b2637` / `#263349`, text `#e8edf6` / `#a5b1c6` / `#7d8aa1`, accent blue `#5a9df5` (button `#2f6fd6`).
- Severity: critical `#f0605d`, high `#f2903f`, medium `#e8bb4a`, low `#4fbb8c`, info `#7c93b6`.
- Observed = teal `#3db7aa`, solid. Derived = violet `#a78ff3`, dashed outline. Always also a text label (never colour alone).
- Type: IBM Plex Sans for UI, IBM Plex Mono for IDs, paths, hashes, timestamps. Body 15 px.
- Shared components: badges (severity, status, basis), cards, responsive tables, stat cards, tabs, expandable panels, evidence-reference chips, empty states, loading skeletons, error banners, page headers.
- Motion: only the intro, expanding panels and hover states. `prefers-reduced-motion` respected.

### 9.3 Screens and routes
Public: `/` intro, `/login` (Analyst sign in: "Access your investigation workspace."), `/register`.
Signed in: `/dashboard`, `/investigations`, `/investigations/:id/{evidence,detection,reconstruction,timeline,impact,rarf,report}`, `/profile`, `/settings`.
Sidebar: Dashboard, Investigations, then the workflow of the current case (Evidence & Log Upload, Detection & Correlation, Attack Reconstruction, Attack Timeline, Impact Analysis, RARF, Investigation Report), then Profile and Settings. No dead links. Breadcrumbs on every page. On screens under 1024 px the sidebar becomes a drawer.

Investigation pages share a header (code, title, severity, status, analyst, updated) and a stepper Evidence > Detection > Reconstruction > Timeline > Impact > RARF > Report with previous/next buttons, so the stages read as one workflow.

### 9.4 Page content and real data mapping

| Page | Shows | Data (real) | Notes |
|---|---|---|---|
| Intro | RAVEN, full name, tagline, animation: scattered event dots converge on one axis and light five nodes (Telemetry, Detection, Reconstruction, Impact, Report). About 4.8 s, Skip button, always continues to sign in | none | never mentions encryption |
| Login / Register | Validation, show/hide password, clear errors, responsive, brand panel | `/api/auth/*` | real auth, no demo bypass |
| Dashboard | Active investigations, open cases, critical findings, evidence items, attack progress of the latest session, cases by severity, status split, recent investigations, important alerts (latest high findings), recent activity, evidence processing status | `/api/dashboard` | every figure counted from real records; mock data never shown |
| Investigations | Table (code, title, host, severity, status, attack stage, evidence count, created, updated), search, status and severity filters, New investigation dialog | `/api/investigations` | stacked cards on mobile |
| Evidence | Upload (drag and drop, progress), pipeline strip Evidence > Processing > Normalization > Ready, evidence table (file, type, events, size, SHA-256, status), Sysmon event-type breakdown (counts by event ID, including unsupported IDs), Run analysis button and per-stage run status | evidence + analysis endpoints | honest statuses, real progress from polling |
| Detection | Rules, correlation groups grouped by rule, per group: rule, process ID, time window, event count, severity, confidence, expandable "why it matched" and the evidence references | `/detections` | 87 groups in the reference case: needs filtering by rule/severity and pagination |
| Reconstruction | Session card (computer, start, end, duration, severity, number of groups, rules), attack chain = groups ordered in time (a horizontal/vertical chain, selectable), process tree from `process_guid` / `parent_process_guid`, per selected group: **Observed evidence** (events) and **Derived interpretation** box | `/reconstruction` | no invented "stages": the chain is the correlation groups |
| Timeline | Chronological list with timestamp, description, host, event type, evidence reference, group/rule membership, observed/derived marker; filters (type, rule, search), pagination, technical-details drawer (normalized + raw + raw XML) | `/timeline`, `/events/{ref}` | 597 events in the reference case |
| Impact | **Observed impact** (per category: event count, assets list, top assets) and **Calculated / derived metrics** (impact score = distinct assets, bursts over time computed from event timestamps), charts only where they help, evidence chips | `/impact` | no financial figures; registry activity is not shown because it is unsupported telemetry; unsupported-event count is shown honestly |
| RARF | Overview cards (identity, detection, reconstruction, timeline, impact, traceability counts), structured tree viewer, raw JSON view, copy, download | `/rarf` | schema v1.0 shown as is |
| Report | Executive summary, **What happened?**, **How did it happen?**, attack timeline, detection evidence, impact, evidence references, investigation metadata. Each statement labelled OBSERVED EVIDENCE or DERIVED / INTERPRETED and linked to evidence. Print / save as PDF | `/report` | "Based on the available evidence..." wording; states limitations |
| Profile / Settings | Account details, current investigation, sign out; preferences, clear local UI state | `/auth/me` | no fake toggles |

### 9.5 Data layer
- One `api\client.js` (fetch wrapper, same-origin, error class carrying `detail`, `code`, `request_id`) and small per-resource modules. One `useApi` hook returning `{data, loading, error, reload}`. Every page has loading, empty and error states.
- The old mock data moves to `src\demo\` and is available only with `VITE_DATA_SOURCE=demo` (for design work and screenshots). The default is `api`. Demo mode shows a permanent banner: "Demo data, not real telemetry."
- The frontend renders exactly what the API returns. It never computes findings.

### 9.6 Responsive, accessible, fast
Desktop, laptop, tablet, mobile. No horizontal page overflow, no clipped text. Tables stack into cards under 720 px. Charts resize. Timeline stays readable on mobile. Touch targets at least 44 px. Skip link, visible focus, labelled controls, form errors linked to fields, semantic landmarks, keyboard-operable tabs, charts have text alternatives, print stylesheet for the report. Large lists are paginated.

---

## 10. Telemetry lab and near-real-time ingestion

### 10.1 VM
Windows 11 VM in VirtualBox, isolated (host-only or internal network; no shared clipboard/drag-and-drop needed for the pipeline). Sysmon installed and running, logging at least Event IDs 1, 3, 11 with SHA256 hashes, into `Microsoft-Windows-Sysmon/Operational`. The Sysmon configuration file in use is stored in `lab\sysmon-config.xml`. Take a VM snapshot before each test session.

### 10.2 Safe test activity (`lab\`)
Harmless PowerShell scripts run INSIDE the VM that generate telemetry matching the shipped rules:
- **Burst script:** starts a benign PowerShell process that creates N small text files with a fixed test extension in `C:\RavenLab\burst\` (for example 60 files over 30 seconds). This produces `process_creation` then many `file_create` events for one process (matches R001 and R003).
- **Stager-like script:** benign process, then one connection to a local test listener on the host-only network, then creates a few files (matches R002).
- **Cleanup script** removes the test files.
Forbidden: real ransomware, real encryption of user data, credential access, connections to external systems.

### 10.3 Transport (DECISION D4, recommended)
1. **Collector (VM):** PowerShell reads Sysmon events with `Get-WinEvent` newer than the last saved `RecordId`, writes JSONL in the raw record shape (6.1, including `raw_xml`) to a VirtualBox shared folder.
2. **Inbox watcher (host):** polls `data\inbox\` every few seconds, reads only new bytes (saved offset in `collector_cursors`), ingests through the normal pipeline (duplicate-safe), and triggers an incremental analysis run for the linked investigation.
3. **Manual path:** upload an exported `.evtx` through the UI (always available).
4. The frontend polls the run status. WebSockets, SSE and queues are deferred unless polling proves insufficient.

---

## 11. Testing strategy

| Level | What | Tools |
|---|---|---|
| Unit | normalizer, dedupe, hash parsing, rule schema, engine, sequencer, timeline builder, impact analyzer, RARF builder, report generator | pytest, temp directories |
| Service | pipeline on the small fixtures and on the reference EVTX (marked `slow`), analysis runs, workspace isolation, upload validation | pytest |
| API | every endpoint: success, not found, validation error, auth required; response shapes | pytest + httpx TestClient with a temp registry and temp workspaces |
| Contract | API responses match `docs\api-contract.md` | pytest |
| Integration | upload EVTX, run analysis, read every endpoint, compare numbers with 6.5b | pytest (`slow`) |
| Frontend | `npm run build`, `npm run lint`, unit tests for the API client and data-mapping helpers (Vitest) | Vite, Vitest |
| End to end | VM safe activity, collector, inbox, analysis, UI shows results | scripted checklist with saved evidence (section 12, S17) |

Rules: tests are deterministic; no test writes into the real `data\` folder (lesson from the first implementation); no test depends on the network or the VM unless marked `vm`.

---

## 12. Build plan (stages)

Every stage ends with: files created, tests passing, verification commands, evidence saved, then STOP for the owner's real output.

| Stage | Name | Deliverable | Acceptance |
|---|---|---|---|
| S0 | Workspace | Folder layout, git, one venv, `requirements*.txt`, `.env.example`, `pytest.ini`, `scripts\*.ps1`, README | `python -m pytest` runs (0 tests ok); `git status` clean |
| S1 | Telemetry lab | Sysmon verified on the VM, `lab\` safe scripts, Sysmon config saved, VM snapshot | Events 1, 3, 11 with SHA256 visible in the event log after running the scripts |
| S2 | Collection | `evtx_loader`, raw JSONL writer, raw record schema, tests | reference EVTX yields 2816 raw records with `raw_xml` |
| S3 | Normalization | 27-field schema, normalizer, time and hash utils, tests | 2816 normalized, 1984 OK, unsupported retained |
| S4 | Deduplication + database | dedupe, models (6.4), per-workspace DB creation, idempotent ingest, validation script | 2719 unique; re-ingest inserts 0 |
| S5 | Correlation + rules | rule schema, YAML rules, engine, persistence | 87 groups (R001 19, R002 14, R003 54) on the reference data; each group explainable |
| S6 | Reconstruction | sequencer, persistence, mapping | 1 session, deterministic ID |
| S7 | Timeline | builder with generated descriptions, persistence | 597 events ordered; descriptions meaningful |
| S8 | Impact | analyzer, persistence, score semantics (6.9) | 4 categories: 475, 12, 14, 0 distinct assets |
| S9 | RARF | schema v1.0, builder, exporter | RARF JSON valid; traceability counts 597/597/87/4 |
| S10 | Report | evidence extractor, generator with `basis`, deterministic | same RARF gives byte-identical content twice |
| S11 | Backend foundation + registry + auth | FastAPI app, settings, error format, request IDs, registry DB, register/login/logout/me, Argon2 | unauthenticated requests rejected; no plaintext passwords |
| S12 | Investigations, evidence, analysis runs | CRUD, upload (validated, hashed), workspace per case, async run + status | upload and run produce the same numbers as S2 to S10 |
| S13 | Read APIs | dashboard, detections, reconstruction, timeline, events, impact, rarf, report, rules + `docs\api-contract.md` | contract tests pass; numbers match 6.5b |
| S14 | Near-real-time | VM collector script, inbox watcher, cursors, incremental run | new VM events appear in the investigation without a manual rebuild |
| S15 | Frontend foundation | Vite app, tokens, shell, sidebar, auth pages, intro, API client, `useApi`, demo mode separated | build passes; sign in works against the real API |
| S16 | Frontend pages on real data | Dashboard, Investigations, Evidence, Detection, Reconstruction, Timeline, Impact, RARF, Report, Profile, Settings | every page shows real data with loading, empty and error states |
| S17 | End-to-end, hardening, release | full chain with safe VM activity, responsive check, accessibility pass, `scripts\run_all.ps1`, docs, final tree | checklist in section 14 fully ticked, with saved evidence |

Suggested shortcuts (owner's choice, **DECISION D3**): the processing stages S2 to S10 are the most valuable and most tested part of the first implementation. They may be rebuilt from the specification above, or the archived, already-tested modules may be reviewed and copied in stage by stage. Either way the acceptance numbers must match.

---

## 13. Windows conventions
- PowerShell only. Label every command [WINDOWS HOST] or [WINDOWS 11 VM].
- Project root: `D:\Projects\RAVEN`. Everything is relative to the repository root (`Path(__file__)`-based); no hard-coded `C:\` or `D:\` paths in code.
- One Python virtual environment: `D:\Projects\RAVEN\venv`. Activate with `.\venv\Scripts\Activate.ps1`. If scripts are blocked: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force` (this window only).
- Ports: backend 8000, frontend dev server 5173 (proxying `/api` to 8000).
- Frontend commands run from `frontend\`. `npm run dev` may need the same execution-policy command in a new window.
- Never work inside a backup folder. Never delete a backup until the new project passes S17.

---

## 14. Definition of done (final checklist)
- [ ] One project folder contains frontend, backend, processing, tests, scripts, docs, configuration
- [ ] `scripts\run_all.ps1` starts everything; the documented commands work from a clean clone plus `.env`
- [ ] Dependencies installed from `requirements.txt`; lock file recorded
- [ ] Database and registry created automatically; migrations or creation are idempotent
- [ ] Real telemetry can enter (EVTX upload and VM collector)
- [ ] Normalization and deduplication reproduce the reference numbers
- [ ] Correlation, rules, evidence references work; every finding explains why it matched
- [ ] Investigation, reconstruction, timeline, impact, RARF, report all work
- [ ] API returns real data only; frontend receives it; no operational mock findings
- [ ] Observed vs derived is visible everywhere it matters
- [ ] Authentication is real; no plaintext passwords; no secrets in code
- [ ] All tests pass (unit, service, API, contract, integration, frontend build and unit tests)
- [ ] End-to-end test with safe VM activity succeeds and its evidence is saved
- [ ] Responsive and accessible: desktop, laptop, tablet, mobile; no horizontal overflow
- [ ] No encryption/decryption wording anywhere except describing observed incident events
- [ ] An analyst can follow an investigation from the report back to the raw Sysmon record

---

## 15. Out of scope (deferred)
Machine-learning detection, cloud or distributed deployment, enterprise SIEM integration, multi-tenancy, threat-intelligence feeds, automatic response or blocking, real malware or ransomware execution, telemetry formats other than Sysmon EVTX, Sysmon events beyond 1, 3, 11 (for example 5, 7, 13, 22 are FUTURE), multi-host correlation across different computers, PostgreSQL, WebSockets/SSE unless polling fails, PDF generation on the server (browser print is used).

---

## 16. Evidence the owner saves at each stage
Command outputs (installation, `pip check`, test runs), database counts, API responses (JSON), correlation and detection output, RARF and report files, browser screenshots of each page with real data, VM screenshots of Sysmon events, end-to-end run logs.

---

## 17. Start block for every new chat
Paste this at the beginning of a new chat, with this file attached:

> Project: RAVEN. The attached `RAVEN_MASTER_SPEC.md` is the source of truth. We build it one stage at a time (S0 to S17). Current stage: **S__**. Decisions made so far: D1 = ___, D2 = ___, D3 = ___, D4 = ___, D5 = ___, D6 = ___. Environment: Windows host, project at D:\Projects\RAVEN, one venv at D:\Projects\RAVEN\venv, Windows 11 VM with Sysmon. Rules: PowerShell only, label [WINDOWS HOST]/[WINDOWS 11 VM], complete files, exact commands, expected output, verification, then stop and wait for my real output. Last completed stage output: (paste).

---

## Appendix A: Lessons from the first implementation (VERIFIED, avoid repeating)
1. **Read/write mismatch:** pipeline jobs wrote to per-job databases while the read endpoints always read one global database, so newly uploaded evidence never appeared. Fix: one accessor that opens the correct workspace by investigation ID for both reads and writes.
2. **Tests polluted real data:** a test used a fixed job folder inside the real `data\` directory and failed on the second run (`sessions_already_present`). Fix: tests use temporary directories only.
3. **Placeholder timeline descriptions** ("Event 1403 (1475)") are useless in a UI. Fix: generated descriptions (6.8).
4. **Unsupported telemetry:** only Sysmon events 1, 3, 11 are normalized; events 4, 5, 16, 255 (and any registry, DNS, image-load events) are unsupported. The UI must not show registry or DNS activity; it shows unsupported-event counts honestly.
5. **Report had no observed/derived flag**; `generated_at` was empty. Fix: `basis` per finding (6.11).
6. **Frontend mock concepts that do not exist in real data:** "attack stages" with kill-chain labels, per-event severity, confidence per detection, monetary or business impact. Use correlation groups, rule severity and confidence, and observed counts instead.
7. **Two frontends and two backends drifted apart.** Keep one of each.
8. **Two virtual environments** caused confusion. Keep exactly one.
9. **Drive and path confusion (C: and D:).** Keep one drive, use relative paths, never hard-code drive letters.
10. **`job_id` was used as a folder name without validation.** Validate every ID that becomes part of a path.
11. **Fake authentication** (always signed in). Replace with real authentication.
12. **Dependencies:** the existing processing code needs SQLAlchemy, PyYAML, python-evtx, python-multipart, FastAPI, Uvicorn, pydantic, pytest and httpx; the backend foundation adds pydantic-settings and python-dotenv.
13. **Windows specifics:** execution policy blocks `Activate.ps1` and `npm.ps1` in new windows; use `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force`. Auto-reload must not watch `data\` (pipeline writes would restart the server).
14. **Frontend API contract of the first TypeScript app** used snake_case and read `detail` from errors. The new API keeps snake_case and `detail`.
15. The dev-server proxy (`/api`, `/health` to `127.0.0.1:8000`) avoids CORS problems in development.

## Appendix B: Decisions the owner must confirm
- **D1** Workspace model: one SQLite database per investigation plus a registry (recommended) or one shared database.
- **D2** Frontend language: JavaScript (matches the chosen design) or TypeScript.
- **D3** Processing stages S2 to S10: rebuild from the spec, or review and copy the archived tested modules.
- **D4** Real-time transport: shared-folder JSONL + polling (recommended), HTTP push from the VM, or SSE.
- **D5** Session `confidence`: null (recommended) or maximum member-rule confidence.
- **D6** Auth: server-side session cookie (recommended) or JWT.
- **D7** Single VM/host for v1 (recommended) or several computers.
- **D8** Report delivery: on-screen + browser print (recommended) or server-generated PDF later.
