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