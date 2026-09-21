# RAVEN API contract

Written from the real code. Contract tests in `tests\api` enforce the shapes below. The endpoints of later stages
(S13 read APIs) are added here at the start of the stage that builds them.

## Conventions

- Base URL `http://127.0.0.1:8000`. The server listens on the loopback address only. All routes are under `/api`
  (plus the legacy `GET /health` for tooling).
- JSON bodies, `snake_case` field names, timestamps ISO-8601 UTC with milliseconds and a trailing `Z`
  (for example `2026-09-13T08:39:49.545Z`).
- Every response has an `X-Request-ID` header. A client may send its own `X-Request-ID` (1 to 64 characters from
  `A-Z a-z 0-9 . _ -`); otherwise the server makes one. The same ID is in the body of error responses.
- Every route except `GET /api/health`, `GET /health`, `POST /api/auth/register` and `POST /api/auth/login`
  requires a signed-in user (session cookie). Without one the answer is `401` with the code `not_authenticated`.
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
