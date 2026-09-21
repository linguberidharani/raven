# RAVEN API contract

Written from the real code. Contract tests in `tests\api` enforce the shapes below. The endpoints of later stages
(S12 investigations and evidence, S13 read APIs) are added here at the start of the stage that builds them.

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
| 409 | `email_already_registered` | registration with an email that already has an account |
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
