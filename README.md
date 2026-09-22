# RAVEN

**Ransomware Attack Visualization and Event Navigator.** RAVEN turns Sysmon telemetry (Windows event logs) into an
investigation an analyst can follow from the final report back to the raw record: it reads the events, finds
patterns with explainable rules, rebuilds the attack session, draws the timeline and the impact, and writes a
report in which every statement is marked as **observed** (recorded in the logs) or **derived** (what RAVEN
concludes from them).

RAVEN describes behaviour. It does not block, stop or remediate anything, and it does not say who did it or why.

## What you need

| | |
|---|---|
| Windows 10 or 11 with PowerShell | every command below is PowerShell |
| Python 3.11 | one virtual environment, `venv\`, for the whole backend |
| Node.js 20 or newer (24 is what it was built on) | for the web interface |
| Git | |
| VirtualBox with the lab VM | only for the live collector (see `lab\COLLECTOR.md`); EVTX upload works without it |

## First-time setup

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force   # this window only
Set-Location D:\Projects\RAVEN
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt -r requirements-dev.txt
Copy-Item .env.example .env
Set-Location frontend
npm ci
Set-Location ..
```

## Run

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
Set-Location D:\Projects\RAVEN
.\scripts\run_all.ps1
```

This starts the backend (`http://127.0.0.1:8000`) and the interface (`http://localhost:5173`), each in its own
window, waits until both answer and opens the browser. Add `-CheckOnly` to only check that everything is in place,
`-NoBrowser` to not open the browser.

Stop it with `.\scripts\stop_all.ps1` (or Ctrl+C in the two windows).

To run the two parts by hand, use two windows: `.\venv\Scripts\Activate.ps1` then `.\scripts\run_backend.ps1` in the
first, and `.\scripts\run_frontend.ps1` in the second. The backend must be up when the interface is used.

## Use

1. Open `http://localhost:5173`, choose **Create an account** (accounts live on this installation only) and sign in.
2. **Investigations** > **New investigation**, then open it.
3. **Evidence & Log Upload**: add an `.evtx` file (Sysmon operational log), or link a file that the VM collector writes
   into the inbox folder. Then **Run analysis**. It runs in the background and shows its ten stages.
4. Follow the steps in the tabs: **Detection & Correlation**, **Attack Reconstruction**, **Attack Timeline**,
   **Impact Analysis**, **RARF** (the formal record, as a tree or JSON, with copy and download) and
   **Investigation Report** (with print or save as PDF).
5. Every evidence reference such as `2:24459` is a button: it opens the normalized event, the original Sysmon
   record and its XML. That is how a statement in the report is traced back to the raw record.

Only Sysmon events 1 (process created), 3 (network connection) and 11 (file created) are used for detection.
Other events are stored and counted, and shown as unsupported, never hidden.

## Test

```powershell
.\scripts\run_tests.ps1              # backend (pytest) and frontend (lint, unit tests, build)
.\scripts\run_tests.ps1 -Backend     # only the backend
.\scripts\run_tests.ps1 -Frontend    # only the frontend
.\scripts\check_clean_clone.ps1 -WithReference   # clones the repository and runs everything in the clone
```

The reference EVTX file (`tests\fixtures\sysmon_export.evtx`) is not committed. The tests that need it are skipped when
it is missing; `-WithReference` copies it into the clone so the whole suite runs.

## Configuration

Copy `.env.example` to `.env` and change what you need. The backend reads it at start.

| Setting | Default | Meaning |
|---|---|---|
| `RAVEN_ENV` | `development` | `development` also serves the interactive API documentation at `/docs` |
| `RAVEN_HOST`, `RAVEN_PORT` | `127.0.0.1`, `8000` | keep the loopback address: RAVEN is a local tool |
| `RAVEN_DATA_DIR` | `data` | registry, investigations, uploaded evidence, RARF and report files |
| `RAVEN_MAX_UPLOAD_MB` | `200` | largest accepted `.evtx` file |
| `RAVEN_SESSION_HOURS` | `12` | how long a sign-in lasts |
| `RAVEN_COOKIE_SECURE` | `false` | `true` only when served over https |
| `RAVEN_INBOX_DIR` | `data/inbox` | where the VM collector drops JSONL files (the VirtualBox shared folder) |
| `RAVEN_INBOX_POLL_SECONDS` | `5` | how often new collector data is looked for; `0` switches it off |

The interface reads `VITE_DATA_SOURCE` from `frontend\.env.local`: `api` (default) is the real backend, `demo` shows
clearly labelled invented data for design work and is never the default.

## Folders

| Folder | Content |
|---|---|
| `raven\` | the Python package: collectors, parsers, database, correlation, reconstruction, timeline, impact, RARF, report, services, API |
| `frontend\` | the web interface (React, Vite); see `frontend\README.md` |
| `scripts\` | `run_all`, `run_backend`, `run_frontend`, `stop_all`, `run_tests`, `check_clean_clone` |
| `lab\` | scripts for the Windows lab VM: safe test activity, the Sysmon collector |
| `tests\` | unit, service, API, contract and integration tests |
| `docs\` | the specification, `api-contract.md`, `evidence-log.md`, `final-checklist.md` |
| `data\` | generated (not committed): registry, investigations, inbox |

## Data and privacy

- Passwords are stored as Argon2 hashes; the session is a random token in an HttpOnly cookie, kept as a hash on the
  server. There are no secrets in the code.
- The server listens on the loopback address only. Do not expose it to a network without adding transport security
  and reviewing the access rules: every signed-in analyst can see every investigation.
- Evidence and results are real telemetry. Paths in Windows events contain user names; treat exported RARF and
  report files, and screenshots, accordingly.
- `data\` and `.env` are never committed.

## If something does not work

| Problem | What to do |
|---|---|
| "running scripts is disabled" | run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force` in that window |
| Port 8000 or 5173 is in use | `.\scripts\stop_all.ps1`, or close the window that uses it |
| The interface says the server cannot be reached | the backend is not running: start it (`run_backend.ps1`) and reload the page |
| `npm ci` fails with EPERM | a dev server still runs: stop it (Ctrl+C), then run `npm ci` again |
| Tests are slow the first time after `npm ci` | antivirus scanning `node_modules`; wait, or exclude `frontend\node_modules` |
| An analysis fails | the Evidence page shows the reason for the stage that failed; fix the file and run again |

More: `docs\api-contract.md` (every endpoint), `lab\COLLECTOR.md` (the VM collector), `docs\evidence-log.md` (what was
verified in each stage), `docs\final-checklist.md` (the definition of done).
