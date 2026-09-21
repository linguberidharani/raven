# RAVEN

**Ransomware Attack Visualization and Event Navigator.** *Trace the Attack. Measure the Impact.*

RAVEN is a defensive cybersecurity investigation platform. It takes real Sysmon telemetry from an isolated Windows 11 lab VM, processes it deterministically, and lets an analyst reconstruct a ransomware-style incident, with every conclusion traceable back to the raw Sysmon record.

RAVEN is not an encryption or decryption tool, not antivirus or EDR, and it uses no generative AI in the analysis path.

The source of truth is `docs\RAVEN_MASTER_SPEC.md`. Decisions taken so far are in `docs\decisions.md`. Real evidence from each stage is logged in `docs\evidence-log.md`.

## Status

Built one stage at a time (S0 to S17). The processing pipeline (S2 to S10) is finished and reproduces the reference numbers of the specification. The API, the investigation workspaces and the frontend follow (S11 to S17). The evidence of every stage is in `docs\evidence-log.md`.

## Processing pipeline (stages S2 to S10)

Each step is a command line tool. Run them from the project root with the venv active. The files can go to any folder (the examples in the evidence log use `data\scratch`).

    python -m raven.collectors.evtx_loader <input.evtx> <raw.jsonl>
    python -m raven.parsers.normalizer <raw.jsonl> <normalized.jsonl> --evidence-id 1
    python -m raven.parsers.deduplicate <normalized.jsonl> <deduplicated.jsonl> --duplicates <duplicates.jsonl>
    python -m raven.database.ingest <deduplicated.jsonl> <raven.db> --summary <summary.json>
    python -m raven.correlation.runner <raven.db> --summary <summary.json>
    python -m raven.reconstruction.persist <raven.db> --mapping <mapping.json>
    python -m raven.timeline.persist <raven.db> --summary <summary.json>
    python -m raven.impact.persist <raven.db> --summary <summary.json>
    python -m raven.rarf.exporter <raven.db> <output folder>
    python -m raven.report.generator <RARF-....json> <output folder> --print
    python -m raven.database.validate <raven.db>

Every step gives the same result when it is run again.
## Prerequisites (Windows host)

Python 3.11, Node.js LTS, Git, PowerShell. From S1: VirtualBox with a Windows 11 VM running Sysmon.

## Setup (from a clean clone)

    Set-Location D:\Projects\RAVEN
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
    python -m venv venv
    .\venv\Scripts\Activate.ps1
    python -m pip install -r requirements-dev.txt
    Copy-Item .env.example .env

## Tests

    .\scripts\run_tests.ps1

or, with the venv active:

    python -m pytest

## Running (available once the stages are built)

    .\scripts\run_backend.ps1     # from S11, http://127.0.0.1:8000
    .\scripts\run_frontend.ps1    # from S15, http://127.0.0.1:5173
    .\scripts\run_all.ps1         # both, in separate windows

## Layout

- `raven\` the Python package (collectors, parsers, database, correlation, reconstruction, timeline, impact, rarf, report, services, api)
- `tests\` mirrors `raven\`, plus `api\`, `integration\`, `e2e\`, `fixtures\`
- `frontend\` the React and Vite app (from S15)
- `lab\` safe VM test-activity scripts and the Sysmon config (from S1)
- `scripts\` PowerShell run scripts
- `docs\` specification, decisions, evidence log
- `data\` generated at run time, never committed
- `venv\` the one virtual environment, never committed

## Conventions

- PowerShell only. No hard-coded drive letters in code.
- `.env`, `data\`, `venv\` and `*.evtx` are never committed.
- Lab activity is harmless only. No real ransomware, no attacks on external systems.