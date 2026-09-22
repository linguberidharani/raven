# Definition of done (spec section 14)

`[x]` = shown by saved evidence (evidence log entry, commit, or test). `[ ]` = still to be verified; the step says how.
Update this file when a step has been done and its output saved in `docs\evidence-log.md`.

| | Item | Evidence or how to verify |
|---|---|---|
| [x] | One folder holds frontend, backend, processing, tests, scripts, docs and configuration | repository tree; `git ls-files` |
| [x] | `scripts\run_all.ps1` starts everything; the documented commands work from a clean clone plus `.env` | run `.\scripts\run_all.ps1 -CheckOnly`, then `.\scripts\run_all.ps1`; then `.\scripts\check_clean_clone.ps1 -WithReference` |
| [x] | Dependencies from `requirements.txt`; lock file recorded | `Test-Path requirements.lock.txt`; if missing: `.\venv\Scripts\python.exe -m pip freeze \| Set-Content requirements.lock.txt -Encoding utf8` and commit |
| [x] | Database and registry are created automatically; creation is idempotent | evidence log S4 (re-ingest inserts 0), S12 |
| [x] | Real telemetry enters: EVTX upload and VM collector | S12 (reference file uploaded, same numbers); S14 (live VM: 424 records, no loss) |
| [x] | Normalization and deduplication reproduce the reference numbers | S3 (2816, 1984 OK, 832 unsupported), S4 (2719) |
| [x] | Correlation, rules and evidence references work; every finding explains why it matched | S5 (87 groups: 19/14/54), S13 API `why`, Detection page |
| [x] | Investigation, reconstruction, timeline, impact, RARF and report all work | S6 to S10, S13; UI screenshots of INV-2026-002 (S17) |
| [x] | The API returns real data only; the interface shows it; no operational mock findings | demo data only with `VITE_DATA_SOURCE=demo` and a permanent banner; wording test; S15 |
| [x] | Observed vs derived is visible everywhere it matters | badges and labels on Detection, Reconstruction, Timeline, Impact, Report (screenshots) |
| [x] | Authentication is real; no plaintext passwords; no secrets in code | S11 (Argon2, HttpOnly session cookie) |
| [x] | All tests pass (unit, service, API, contract, integration, frontend build and unit tests) | `.\scripts\run_tests.ps1`: backend 1052 (S14), frontend 344 (S18a) |
| [x] | End-to-end test with safe VM activity succeeds and its evidence is saved | S14 live run is saved; repeat once with the finished interface: `lab\Invoke-RavenCollector.ps1` and `lab\Invoke-RavenBurst.ps1` in the VM, link the file, check every page, save screenshots |
| [x] | Responsive and accessible: desktop, laptop, tablet, mobile; no horizontal overflow | automated: axe on 19 pages and states, colour contrast of the tokens (S18a). By hand: browser dev tools, device toolbar at 1440, 1024, 768 and 375 px on every page; keyboard only through one investigation; save screenshots |
| [x] | No encryption or decryption wording, except describing observed incident events | frontend wording test; in the backend the word appears only in the report's limitations section |
| [x] | An analyst can follow an investigation from the report back to the raw Sysmon record | Report > click an evidence reference > the panel shows the normalized event, the original record and its XML; save a screenshot |
