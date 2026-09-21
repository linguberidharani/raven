"""API tests: analysis runs on SYNTHETIC evidence (a fake loader replaces the EVTX reader)."""

import json
import threading

import pytest
from fastapi.testclient import TestClient

from raven.database.registry_models import AnalysisRun, EvidenceSource
from raven.services.pipeline import STAGES
from tests.api.conftest import make_investigation, register_and_login, run_analysis, upload_evtx
from tests.synthetic import fake_loader

RUN_KEYS = {"id", "investigation_id", "status", "stage", "stages", "error", "started_at", "finished_at"}


@pytest.fixture
def signed_in(app, client):
    app.state.runs.loader = fake_loader()
    register_and_login(client)
    return client


@pytest.fixture
def investigation(signed_in):
    return make_investigation(signed_in)


def test_the_latest_run_is_null_before_any_run(signed_in, investigation):
    response = signed_in.get(f"/api/investigations/{investigation['id']}/analysis")
    assert response.status_code == 200 and response.json() is None
    assert response.headers["Cache-Control"] == "no-store"


def test_a_run_needs_evidence(signed_in, investigation):
    response = signed_in.post(f"/api/investigations/{investigation['id']}/analysis")
    assert response.status_code == 409 and response.json()["code"] == "no_evidence"


def test_an_unknown_investigation_is_not_found(signed_in):
    assert signed_in.post("/api/investigations/999/analysis").status_code == 404
    assert signed_in.get("/api/investigations/999/analysis").status_code == 404


def test_starting_a_run_returns_at_once_with_the_run(app, signed_in, investigation):
    upload_evtx(signed_in, investigation["id"])
    response = signed_in.post(f"/api/investigations/{investigation['id']}/analysis")
    assert response.status_code == 202
    body = response.json()
    assert set(body) == RUN_KEYS and body["investigation_id"] == investigation["id"]
    assert body["status"] in ("queued", "running", "completed")
    assert [s["name"] for s in body["stages"]] == list(STAGES)
    app.state.runs.wait(body["id"], 60)


def test_a_finished_run_shows_every_stage_with_its_numbers(app, signed_in, investigation):
    upload_evtx(signed_in, investigation["id"])
    run = run_analysis(app, signed_in, investigation["id"])
    assert set(run) == RUN_KEYS and run["status"] == "completed" and run["stage"] == "report" and run["error"] is None
    assert all(set(stage) == {"name", "status", "started_at", "finished_at", "summary", "error"} for stage in run["stages"])
    assert [s["status"] for s in run["stages"]] == ["completed"] * len(STAGES)
    summaries = {s["name"]: s["summary"] for s in run["stages"]}
    assert summaries["collect"]["records"] == 13 and summaries["deduplicate"] == {"input": 13, "unique": 13, "removed": 0}
    assert summaries["correlate"]["groups"] == 2 and summaries["reconstruct"]["sessions"] == 1 and summaries["timeline"]["timeline_events"] == 11


def test_the_investigation_header_shows_the_derived_results(app, signed_in, investigation):
    upload_evtx(signed_in, investigation["id"])
    run_analysis(app, signed_in, investigation["id"])
    body = signed_in.get(f"/api/investigations/{investigation['id']}").json()
    assert (body["severity"], body["stage"], body["analysis_status"]) == ("HIGH", "report", "completed")
    assert body["counts"] == {"evidence": 1, "detections": 2, "sessions": 1, "timeline_events": 11}
    listed = signed_in.get("/api/investigations", params={"severity": "HIGH"}).json()
    assert listed["total"] == 1 and listed["items"][0]["id"] == investigation["id"]
    assert signed_in.get("/api/investigations", params={"severity": "LOW"}).json()["total"] == 0


def test_the_evidence_list_shows_ready_files_and_the_event_breakdown(app, signed_in, investigation):
    upload_evtx(signed_in, investigation["id"])
    run_analysis(app, signed_in, investigation["id"])
    body = signed_in.get(f"/api/investigations/{investigation['id']}/evidence").json()
    (item,) = body["items"]
    assert (item["status"], item["events_total"], item["error"]) == ("ready", 13, None) and item["ingested_at"]
    assert body["event_breakdown"] == [
        {"event_id": 1, "event_type": "process_creation", "count": 1},
        {"event_id": 11, "event_type": "file_create", "count": 12},
    ]


def test_a_second_run_is_allowed_after_the_first_and_gives_the_same_numbers(app, signed_in, investigation):
    upload_evtx(signed_in, investigation["id"])
    first = run_analysis(app, signed_in, investigation["id"])
    second = run_analysis(app, signed_in, investigation["id"])
    assert second["id"] != first["id"] and second["status"] == "completed"
    for a, b in zip(first["stages"], second["stages"]):
        if a["name"] not in ("collect", "ingest"):
            assert a["summary"] == b["summary"], a["name"]
    assert second["stages"][3]["summary"]["inserted"] == 0


def test_a_run_cannot_start_while_another_is_active(app, signed_in, investigation):
    upload_evtx(signed_in, investigation["id"])
    entered, release = threading.Event(), threading.Event()
    inner = fake_loader()

    def slow(evtx, raw):
        entered.set()
        release.wait(30)
        return inner(evtx, raw)

    app.state.runs.loader = slow
    first = signed_in.post(f"/api/investigations/{investigation['id']}/analysis")
    assert first.status_code == 202 and entered.wait(30)
    polled = signed_in.get(f"/api/investigations/{investigation['id']}/analysis").json()
    assert polled["status"] == "running" and polled["stage"] == "collect"
    again = signed_in.post(f"/api/investigations/{investigation['id']}/analysis")
    assert again.status_code == 409 and again.json()["code"] == "analysis_already_running"
    header = signed_in.get(f"/api/investigations/{investigation['id']}").json()
    assert (header["analysis_status"], header["stage"]) == ("running", "collect")
    release.set()
    app.state.runs.wait(first.json()["id"], 60)


def test_a_failed_run_shows_the_error_and_marks_the_file(app, signed_in, investigation):
    evidence = upload_evtx(signed_in, investigation["id"]).json()
    app.state.runs.loader = fake_loader(failing_ids=(evidence["id"],))
    run = run_analysis(app, signed_in, investigation["id"])
    assert run["status"] == "failed" and run["error"].startswith("Stage collect failed:") and run["stages"][0]["status"] == "failed"
    listed = signed_in.get(f"/api/investigations/{investigation['id']}/evidence").json()["items"][0]
    assert listed["status"] == "failed" and "synthetic failure" in listed["error"]
    header = signed_in.get(f"/api/investigations/{investigation['id']}").json()
    assert header["analysis_status"] == "failed" and header["severity"] is None
    retry = signed_in.post(f"/api/investigations/{investigation['id']}/analysis")
    assert retry.status_code == 409 and retry.json()["code"] == "no_evidence"


def test_investigations_are_analysed_separately(app, signed_in, investigation):
    other = make_investigation(signed_in, "Other case")
    upload_evtx(signed_in, investigation["id"], 1)
    upload_evtx(signed_in, other["id"], 2)
    run_analysis(app, signed_in, investigation["id"])
    assert signed_in.get(f"/api/investigations/{other['id']}").json()["counts"]["timeline_events"] == 0
    assert signed_in.get(f"/api/investigations/{other['id']}/analysis").json() is None
    run_analysis(app, signed_in, other["id"])
    assert signed_in.get(f"/api/investigations/{other['id']}").json()["counts"]["timeline_events"] == 11


def test_runs_interrupted_by_a_restart_are_failed_when_the_server_starts(app):
    with app.state.registry_factory() as registry:
        from sqlalchemy import insert

        from raven.database.registry_models import Investigation, User

        registry.execute(insert(User).values(name="A", email="a@example.com", password_hash="h", created_at="2026-09-13T08:39:49.545Z"))
        registry.execute(insert(Investigation).values(code="INV-2026-001", title="t", analyst_id=1, created_at="a", updated_at="a", workspace_dir="investigations/1", status="open"))
        registry.add(AnalysisRun(investigation_id=1, status="running", stage="ingest", stages_json=json.dumps([])))
        registry.commit()
    with TestClient(app):
        pass
    with app.state.registry_factory() as registry:
        run = registry.get(AnalysisRun, 1)
        assert run.status == "failed" and run.error == "Interrupted by a server restart."
