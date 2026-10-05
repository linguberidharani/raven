# RAVEN API contract

Written from the real code. Contract tests in `tests\api` enforce the shapes below. The endpoints of later stages
(later stages) are added here at the start of the stage that builds them.

## Conventions

- Base URL `http://127.0.0.1:8000`. The server listens on the loopback address only. All routes are under `/api`
  (plus the legacy `GET /health` for tooling).
- JSON bodies, `snake_case` field names, timestamps ISO-8601 UTC with milliseconds and a trailing `Z`
  (for example `2026-09-13T08:39:49.545Z`).
- Every response has an `X-Request-ID` header. A client may send its own `X-Request-ID` (1 to 64 characters from
  `A-Z a-z 0-9 . _ -`); otherwise the server makes one. The same ID is in the body of error responses.
- Every route except `GET /api/health`, `GET /health`, `POST /api/auth/register`, `POST /api/auth/login`,
  `POST /api/auth/forgot-password` and `POST /api/auth/reset-password` requires a signed-in user (session
  cookie). Without one the answer is `401` with the code `not_authenticated`.
- The interactive documentation (`/docs`, `/openapi.json`) exists only when `RAVEN_ENV=development`.

## Errors

Every error has this shape (no request body is ever echoed back):

```json
{ "detail": "<text or list>", "code": "<machine code>", "request_id": "<id>" }
```

| Status | code | When |
|---|---|---|
| 401 | `not_authenticated` | no session cookie, unknown, expired or ended session |
| 401 | `invalid_credentials` | wrong email or password at login (the same answer for both) |
| 404 | `not_found` | unknown route |
| 405 | `method_not_allowed` | wrong HTTP method |
| 404 | `investigation_not_found` | no investigation with this ID |
| 404 | `inbox_file_not_found` | linking a file that is not in the inbox |
| 409 | `source_already_linked` | the inbox file is already linked to an investigation |
| 422 | `invalid_source_name` | a source name is not a plain `.jsonl` file name |
| 404 | `not_analysed` | RARF or report asked for, but no analysis has produced sessions yet |
| 404 | `session_not_found` | the `session` query names no attack session of the investigation |
| 404 | `rarf_not_found`, `report_not_found` | the file of the session is missing; run the analysis again |
| 404 | `event_not_found`, `raw_record_not_found` | no stored event, or no raw record, for this reference |
| 409 | `email_already_registered` | registration with an email that already has an account |
| 409 | `duplicate_evidence` | the same file (SHA-256) is already part of the investigation |
| 409 | `no_evidence` | an analysis was requested but there is no usable evidence file |
| 409 | `analysis_already_running` | a run is already queued or running for this investigation |
| 413 | `file_too_large` | an uploaded file is larger than `RAVEN_MAX_UPLOAD_MB` |
| 413 | `payload_too_large` | a request body far over the upload limit (refused before it is read) |
| 422 | `invalid_file_type` | the uploaded name does not end in `.evtx` |
| 422 | `invalid_filename` | the uploaded name is empty, too long or has control characters |
| 422 | `invalid_evtx` | the file is not a Windows event log (wrong signature or too short) |
| 422 | `validation_error` | invalid body; `detail` is a list of `{ "loc": [...], "msg": "..." }` |
| 500 | `internal_error` | unexpected failure; `detail` is always `Internal server error` |
| 503 | (health body) | `GET /api/health` when the registry or the rules are not usable |

## Session cookie (decision D6)

`POST /api/auth/login` sets `raven_session`: a random token, `HttpOnly`, `SameSite=Lax`, `Path=/`,
`Max-Age` = `RAVEN_SESSION_HOURS` x 3600 (default 43200), and `Secure` when `RAVEN_COOKIE_SECURE=true`.
The server stores only the SHA-256 hash of the token. `POST /api/auth/logout` deletes the session and clears
the cookie. Responses of the auth endpoints carry `Cache-Control: no-store`.

## Endpoints (stage S11)

### GET /api/health

No sign-in. `200` (or `503` with `"status": "degraded"`):

```json
{
  "status": "ok",
  "service": "raven-api",
  "version": "0.1.0",
  "environment": "development",
  "registry": "ok",
  "rules_loaded": 3,
  "rarf_version": "1.0"
}
```

### GET /health

Legacy path. `200` `{ "status": "ok" }`.

### POST /api/auth/register

No sign-in. It does not sign in; call login next.

Request (unknown fields are rejected):

| Field | Type | Rule |
|---|---|---|
| `name` | string | 1 to 100 characters (spaces at the ends are removed) |
| `email` | string | a valid address, at most 254 characters, stored in lower case |
| `organization` | string or null | optional, at most 100 characters |
| `password` | string | 10 to 128 characters, not only spaces |

Response `201`: the user, see below. Errors: `409 email_already_registered`, `422 validation_error`.

### POST /api/auth/login

No sign-in. Request: `{ "email": "...", "password": "..." }` (unknown fields are rejected).
Response `200`: the user, and the `raven_session` cookie. Errors: `401 invalid_credentials`, `422 validation_error`.

### POST /api/auth/forgot-password

No sign-in. Request: `{ "email": "..." }`. Response `202`: `{ "detail": "..." }`, always the same text whether
or not the address has an account, so this cannot be used to test which addresses are registered. A reset
email is sent only when the address does have one; when `RAVEN_SMTP_HOST` is not configured, the request is
still accepted and no email is sent. Error: `422 validation_error` for a malformed address.

### POST /api/auth/reset-password

No sign-in. Request: `{ "token": "...", "password": "..." }` (the token is the one from the reset email link,
`?token=...`). Response `200`: `{ "detail": "..." }`. The token can be used once and expires after
`RAVEN_PASSWORD_RESET_HOURS` (default 1 hour); on success every existing session of the account is deleted,
so the analyst must sign in again everywhere. Errors: `400 invalid_reset_token` (unknown, expired or already
used), `422 validation_error` (the new password does not meet the rules).

### POST /api/auth/logout

Needs a signed-in user. Response `204` without a body; the cookie is cleared. Error: `401 not_authenticated`.

### GET /api/auth/me

Needs a signed-in user. Response `200`: the user. Error: `401 not_authenticated`.

### The user object

```json
{
  "id": 1,
  "name": "Ada Lovelace",
  "email": "ada@example.com",
  "organization": "Analytical Engines",
  "created_at": "2026-09-21T10:15:30.123Z"
}
```

A password or a password hash is never part of any response.

## Endpoints (stage S12): investigations, evidence, analysis

All of these need a signed-in user. IDs in paths are whole numbers of at least 1 (otherwise `422`). All signed-in
analysts can see all investigations; the analyst who created one is recorded.

### The investigation object

```json
{
  "id": 1,
  "code": "INV-2026-001",
  "title": "Boot activity",
  "description": "Startup review",
  "host": "HOST-1",
  "status": "open",
  "severity": "HIGH",
  "stage": "report",
  "analysis_status": "completed",
  "analyst": { "id": 1, "name": "Ada Lovelace" },
  "counts": { "evidence": 1, "detections": 87, "sessions": 1, "timeline_events": 597 },
  "created_at": "2026-09-21T10:15:30.123Z",
  "updated_at": "2026-09-21T10:20:00.000Z"
}
```

`status` is `open`, `active` or `closed`. `severity` is DERIVED: the highest severity of the attack sessions of the
workspace (`null` until an analysis has run). `stage` and `analysis_status` come from the latest analysis run
(`null` when there has been none). `detections` is the number of correlation groups.

### POST /api/investigations

Request (unknown fields are rejected): `title` (1 to 200 characters), `description` (optional, at most 5000),
`host` (optional, at most 100). Response `201`: the investigation. The code is `INV-<year>-<number>`; the number
counts within the year and is never reused. The workspace folder is created.

### GET /api/investigations

Query: `status` (`open|active|closed`), `severity` (`HIGH|MEDIUM|LOW|INFO`, the derived severity), `q` (text in
code, title or description, at most 100 characters), `page` (from 1), `page_size` (1 to 200, default 100).
Response `200`: `{ "items": [investigation, ...], "total": n, "page": 1, "page_size": 100 }`, newest first.

### GET /api/investigations/{id}

Response `200`: the investigation. Error: `404 investigation_not_found`.

### PATCH /api/investigations/{id}

Request: any of `title`, `description` (`null` clears it), `host` (`null` clears it), `status`. Only the fields
that are sent are changed. Response `200`: the investigation.

### GET /api/investigations/{id}/evidence

Response `200`:

```json
{
  "items": [
    {
      "id": 1, "investigation_id": 1, "filename": "sysmon_export.evtx", "sha256": "4F...", "size_bytes": 3215360,
      "source_type": "evtx_upload", "status": "ready", "events_total": 2816, "error": null,
      "created_at": "2026-09-21T10:16:00.000Z", "ingested_at": "2026-09-21T10:17:10.000Z"
    }
  ],
  "event_breakdown": [ { "event_id": 1, "event_type": "process_creation", "count": 930 } ]
}
```

`status` is `uploaded`, `processing`, `ready` or `failed` (`error` says why). `events_total` is the number of raw
records read from the file. `event_breakdown` counts the stored events by Sysmon event ID, unsupported IDs included
(`event_type` is `unsupported` for those); it is empty until an analysis has run.

### POST /api/investigations/{id}/evidence

`multipart/form-data` with one field `file`. The name must end in `.evtx` (the name is only a label: files are
stored as `<evidence id>.evtx` inside the workspace), the file must start with the EVTX signature, must not be larger
than `RAVEN_MAX_UPLOAD_MB`, and its SHA-256 must not already be in the investigation. Response `201`: the evidence
item (status `uploaded`). Errors: `422 invalid_file_type | invalid_filename | invalid_evtx`, `413 file_too_large |
payload_too_large`, `409 duplicate_evidence`, `404 investigation_not_found`.

### POST /api/investigations/{id}/analysis

Starts an analysis run in a background worker and returns at once: `202` with the run. One run per investigation at
a time. Errors: `409 no_evidence`, `409 analysis_already_running`, `404 investigation_not_found`.

### GET /api/investigations/{id}/analysis

The latest run, or `null` when there has been none. Meant for polling every 2 to 3 seconds (`Cache-Control: no-store`).

```json
{
  "id": 1, "investigation_id": 1, "status": "running", "stage": "normalize", "error": null,
  "started_at": "2026-09-21T10:16:05.000Z", "finished_at": null,
  "stages": [
    { "name": "collect", "status": "completed", "started_at": "...", "finished_at": "...",
      "summary": { "evidence": [ { "evidence_id": 1, "records": 2816, "reused": false } ], "records": 2816 }, "error": null },
    { "name": "normalize", "status": "running", "started_at": "...", "finished_at": null, "summary": null, "error": null }
  ]
}
```

`status` is `queued`, `running`, `completed` or `failed`. The stages, in order: `collect`, `normalize`,
`deduplicate`, `ingest`, `correlate`, `reconstruct`, `timeline`, `impact`, `rarf`, `report`; each is `pending`,
`running`, `completed` or `failed` and carries the numbers of that stage in `summary` once it is done. A file that
makes a run fail is marked `failed` and left out of later runs. A run that was interrupted by a server restart is
marked `failed` (`Interrupted by a server restart.`) when the server starts.

## Endpoints (stage S13): read APIs

All of these need a signed-in user and only read what the pipeline stored. Before an analysis has run, the list
endpoints answer with empty lists (`200`); RARF and report answer `404 not_analysed`. Responses carry
`Cache-Control: no-store`. Text that the pages call "derived" is generated by the API in controlled wording and
carries `"basis": "derived"`; recorded facts carry `"basis": "observed"`. The frontend shows what it receives and
never computes findings.

IDs: `event_id` in evidence lists and timeline items is the database ID of the event (the same as in the RARF);
`sysmon_event_id` is the Sysmon event ID (1, 3, 11, ...). `raw_event_ref` is `<evidence id>:<record id>`.

### GET /api/dashboard

```json
{
  "totals": { "investigations": 1, "active_investigations": 0, "open_cases": 1, "evidence_items": 1, "sessions": 1, "high_severity_findings": 73 },
  "cases_by_severity": { "HIGH": 1, "MEDIUM": 0, "LOW": 0, "INFO": 0, "none": 0 },
  "cases_by_status": { "open": 1, "active": 0, "closed": 0 },
  "findings_by_severity": { "HIGH": 73, "MEDIUM": 14, "LOW": 0, "INFO": 0 },
  "evidence_by_status": { "uploaded": 0, "processing": 0, "ready": 1, "failed": 0 },
  "recent_investigations": [ "<investigation object>, at most 5, newest first" ],
  "latest_session": {
    "investigation_id": 1, "code": "INV-2026-001", "session_id": "RAVEN-SESSION-...", "start_time": "...", "end_time": "...", "severity": "HIGH",
    "chain": [ { "rule_id": "RAVEN-R003", "rule_name": "...", "severity": "HIGH", "groups": 54, "first_start": "..." } ]
  },
  "alerts": [ { "investigation_id": 1, "code": "INV-2026-001", "group_id": "...", "rule_id": "...", "rule_name": "...", "severity": "HIGH", "window_start": "...", "event_count": 10 } ],
  "recent_activity": [ { "time": "...", "kind": "investigation_created", "investigation_id": 1, "code": "INV-2026-001", "text": "..." } ],
  "evidence_queue": [ { "id": 1, "investigation_id": 1, "code": "INV-2026-001", "filename": "x.evtx", "status": "uploaded", "size_bytes": 1, "error": null, "created_at": "..." } ]
}
```

Findings are correlation groups counted over all workspaces; `severity` is the severity of the rule. `latest_session` is
`null` until a session exists; its `chain` lists the rules of the session in the order of their first group.
`alerts` are the latest HIGH groups (at most 5). `recent_activity` (at most 10) has the kinds `investigation_created`,
`evidence_uploaded`, `analysis_completed` and `analysis_failed`. `evidence_queue` lists files that are not `ready`.

### GET /api/rules

`{ "rules": [ { "rule_id", "rule_name", "description", "steps": [ { "event_type", "min_count" } ], "match_key", "time_window_seconds", "severity", "confidence" } ] }`:
the shipped rule definitions.

### GET /api/investigations/{id}/detections

Query: `rule` (a rule ID), `severity` (`HIGH|MEDIUM|LOW|INFO`), `page` (from 1), `page_size` (1 to 200, default 50).

```json
{
  "analysed": true,
  "rules": [ { "rule_id": "RAVEN-R001", "rule_name": "...", "description": "...", "severity": "HIGH", "confidence": 85, "match_key": "process_id",
               "time_window_seconds": 60, "steps": [ { "event_type": "process_creation", "min_count": 1 } ], "enabled": true, "groups": 19 } ],
  "counts": { "total_groups": 87, "by_rule": { "RAVEN-R001": 19 }, "by_severity": { "HIGH": 73, "MEDIUM": 14 } },
  "groups": [ {
    "group_id": "RAVEN-R001:1224:2026-09-13T08:39:49.695Z", "rule_id": "RAVEN-R001", "rule_name": "...", "severity": "HIGH", "confidence": 85,
    "match_key": "process_id", "match_value": "1224", "time_window_seconds": 60,
    "window_start": "...", "window_end": "...", "event_count": 6,
    "why": { "basis": "derived", "text": "For process ID 1224, the recorded events satisfy rule ...", "steps": [ { "event_type": "process_creation", "required": 1, "found": 1 } ] },
    "interpretation": { "basis": "derived", "text": "..." },
    "evidence": { "event_ids": [1403], "raw_event_refs": ["1:1543"] }
  } ],
  "total": 87, "page": 1, "page_size": 50
}
```

`groups` are in time order, filtered and paged; `total` is the number after filtering. `counts` and `rules` are not filtered.
`confidence` is the confidence of the rule.

### GET /api/investigations/{id}/reconstruction

`{ "sessions": [ session ] }`. A session:

```json
{
  "session_id": "RAVEN-SESSION-...", "computer": "Dharani", "start_time": "...", "end_time": "...", "duration_ms": 199943,
  "severity": "HIGH", "confidence": null, "description": "...", "group_count": 87, "rule_ids": ["RAVEN-R001"],
  "chain": [ {
    "group_id": "...", "rule_id": "...", "rule_name": "...", "severity": "HIGH", "match_value": "1224", "start_time": "...", "end_time": "...", "event_count": 6,
    "events": [ { "event_id": 1403, "raw_event_ref": "1:1543", "timestamp": "...", "event_type": "process_creation", "description": "Process created: ..." } ],
    "interpretation": { "basis": "derived", "text": "..." }
  } ],
  "process_tree": {
    "nodes": [ { "process_guid": "{...}", "process_id": 1224, "image": "C:\\Windows\\System32\\svchost.exe", "user": "NT AUTHORITY\\SYSTEM",
                 "parent_process_guid": "{...}", "parent_process_id": 700, "parent_image": "...", "first_seen": "...", "last_seen": "...",
                 "event_counts": { "file_create": 5 }, "group_ids": ["..."], "in_session": true, "basis": "observed", "child_guids": [] } ],
    "roots": ["{...}"]
  }
}
```

`chain` is the correlation groups of the session in time order; there are no invented stages. `events` of a group are
the recorded (observed) evidence in time order. The process tree is built from `process_guid` and `parent_process_guid`
of the session's events; a parent that has no event in the session appears as a node with `in_session: false`.
Nodes are ordered by first appearance; `roots` are the nodes without a parent node.

### GET /api/investigations/{id}/timeline

Query: `session` (an attack session ID), `event_type` (`process_creation|network_connection|file_create`), `rule` (only events
of groups of this rule), `q` (text in the description), `page` (from 1), `page_size` (1 to 200, default 100).
Response: `{ "items": [ item ], "total": n, "page": 1, "page_size": 100 }`, in session and sequence order. An item:

```json
{
  "timeline_event_id": 1, "session_id": "RAVEN-SESSION-...", "sequence_number": 1, "timestamp": "2026-09-13T08:39:49.545Z",
  "description": "File created: ...", "computer": "Dharani", "event_type": "file_create", "event_id": 1403, "sysmon_event_id": 11,
  "raw_event_ref": "1:1475", "basis": "observed",
  "groups": [ { "group_id": "RAVEN-R003:4:2026-09-13T08:39:49.545Z", "rule_id": "RAVEN-R003", "basis": "derived" } ]
}
```

### GET /api/investigations/{id}/events/{event_ref}

`event_ref` is `<evidence id>:<record id>` (otherwise `422`). The evidence file must belong to the investigation.

```json
{
  "raw_event_ref": "1:1475",
  "event": { "id": 1403, "raw_event_ref": "1:1475", "event_id": 11, "event_type": "file_create", "timestamp": "...", "...": "the 27 normalized fields plus id" },
  "raw": { "event_id": 11, "time_created": "2026-09-13 08:39:49.545000+00:00", "computer": "Dharani", "record_id": 1475, "event_data": { "UtcTime": "...", "Image": "..." } },
  "raw_xml": "<Event xmlns=...>...</Event>",
  "groups": [ { "group_id": "...", "rule_id": "...", "basis": "derived" } ],
  "timeline": { "session_id": "...", "sequence_number": 1, "description": "..." }
}
```

`timeline` is `null` for an event that is not part of a session. Errors: `404 event_not_found` (no stored event; events that
were removed as duplicates are not stored), `404 raw_record_not_found`.

### GET /api/investigations/{id}/impact

`{ "sessions": [ { "session_id", "categories": [ category ], "activity": {...} } ] }`. The categories are always
`files_affected`, `network_activity`, `process_activity`, `unsupported_events`, in this order:

```json
{
  "category": "files_affected", "impact_analysis_id": 1,
  "observed": { "basis": "observed", "event_count": 558, "affected_assets": ["C:\\a.txt"], "top_assets": [ { "asset": "C:\\a.txt", "events": 3 } ],
                "details": { "distinct_computers": 1, "distinct_users": 3, "distinct_processes": 16 } },
  "derived": { "basis": "derived", "impact_score": 475, "definition": "The number of distinct affected assets. A calculated count; it does not measure damage." },
  "evidence": { "event_ids": [1403], "raw_event_refs": ["1:1475"] }
}
```

`top_assets` are the (at most 5) assets with the most events. `activity` is the derived number of events over time:
`{ "basis": "derived", "bucket_seconds": 10, "buckets": [ { "start": "...", "file_create": 3, "network_connection": 0, "process_creation": 1, "total": 4 } ] }`
(10 s buckets; longer buckets when the session is long, so there are at most 400).

### GET /api/investigations/{id}/rarf

Query: `session` (attack session ID, default the first session), `download=true` (as a file download).
Response: the RARF v1.0 document of the session exactly as written by the pipeline. Errors: `404 not_analysed`,
`404 session_not_found`, `404 rarf_not_found`.

### GET /api/investigations/{id}/report

Query: `session` (default the first session). Response: the report document (see the report generator). Its content is
deterministic; only `generated_at` is set at the time of the request. Errors as for the RARF.

## Endpoints (stage S14): inbox and collector

The VM collector appends raw records (one JSON object per line, spec 6.1) to a file in the inbox folder
(`RAVEN_INBOX_DIR`, default `data\inbox`, the shared folder of the VM). An analyst links such a file to an investigation.
The inbox watcher then reads the new complete lines every `RAVEN_INBOX_POLL_SECONDS` seconds (0 switches it off), adds
the new records to the raw file of the evidence source, and starts an analysis run for the investigation. Records that
are already known (same record ID and time) are never added twice. While an analysis run of the investigation is
active, new data waits in the inbox file; the next look after the run picks it up.

All of these need a signed-in user.

### GET /api/inbox

`{ "items": [ { "source_name": "sysmon-Dharani.jsonl", "size_bytes": 1234, "modified_at": "...", "investigation_id": 1, "investigation_code": "INV-2026-001" } ] }`.
The files of the inbox folder whose names are plain `.jsonl` names; `investigation_id` and `investigation_code` are `null`
for a file that is not linked.

### POST /api/inbox/poll

Looks at the inbox now. Response `200`:

```json
{
  "results": [ { "source_name": "sysmon-Dharani.jsonl", "investigation_id": 1, "records_added": 250, "rejected": 0, "offset": 190345, "error": null, "skipped": null } ],
  "analyses_started": [1]
}
```

`records_added` counts records that were new; `rejected` counts lines that were not valid raw records; `offset` is the read
position; `error` says why a file could not be read; `skipped` says why a file was left for the next look (an analysis run
was active). `analyses_started` lists the investigations for which a run was started.

### GET /api/investigations/{id}/collector

`{ "items": [ { "source_name", "evidence_id", "last_offset", "last_record_id", "updated_at", "status", "events_total", "error" } ] }`:
the inbox files linked to the investigation with their read position. `status` is the status of the evidence source
(`uploaded` means that there is data that has not been analysed yet).

### POST /api/investigations/{id}/collector

Request (unknown fields are rejected): `{ "source_name": "sysmon-Dharani.jsonl" }`. Response `201`: the evidence item
(see the evidence list) with `source_type` `vm_collector`, `filename` the source name, `size_bytes` the bytes read so far,
`sha256` the hash of the bytes read so far, `events_total` the number of records taken over. Errors:
`422 invalid_source_name`, `404 inbox_file_not_found`, `409 source_already_linked`, `404 investigation_not_found`.
