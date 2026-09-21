"""Unit tests for analysis runs. Temporary directories, SYNTHETIC evidence and fake loaders (no EVTX reader)."""

import io
import json
import threading

import pytest
from sqlalchemy import insert, select

from raven.config import Settings
from raven.database.registry_models import AnalysisRun, EvidenceSource, User
from raven.database.session import open_registry_database
from raven.services.analysis_runs import AnalysisRunManager, run_view
from raven.services.errors import ServiceError
from raven.services.evidence import save_upload
from raven.services.investigations import create_investigation, latest_run, workspace_facts
from raven.services.pipeline import STAGES
from raven.services.workspace import Workspace
from tests.synthetic import evtx_bytes, fake_loader


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, env="test", data_dir=tmp_path / "data")


@pytest.fixture
def factory(tmp_path):
    factory = open_registry_database(tmp_path / "registry.db")
    with factory.kw["bind"].begin() as connection:
        connection.execute(insert(User).values(name="Ada", email="ada@example.com", password_hash="h", created_at="2026-09-13T08:39:49.545Z"))
    yield factory
    factory.kw["bind"].dispose()


@pytest.fixture
def investigation_id(factory, settings):
    with factory() as registry:
        return create_investigation(registry, settings, analyst_id=1, title="Case").id


def add_evidence(factory, settings, investigation_id, salt=0):
    with factory() as registry:
        return save_upload(registry, settings, investigation_id, f"log{salt}.evtx", io.BytesIO(evtx_bytes(salt))).id


def manager(factory, settings, loader=None):
    return AnalysisRunManager(factory, settings, loader=loader or fake_loader())


def fetch_run(factory, run_id):
    with factory() as registry:
        return run_view(registry.get(AnalysisRun, run_id))


def evidence_rows(factory, investigation_id):
    with factory() as registry:
        rows = registry.scalars(select(EvidenceSource).where(EvidenceSource.investigation_id == investigation_id).order_by(EvidenceSource.id)).all()
        return [(r.id, r.status, r.events_total, r.error, r.ingested_at) for r in rows]


def test_a_run_needs_an_existing_investigation_and_some_evidence(factory, settings, investigation_id):
    runs = manager(factory, settings)
    with pytest.raises(ServiceError) as caught:
        runs.start(999)
    assert (caught.value.status_code, caught.value.code) == (404, "investigation_not_found")
    with pytest.raises(ServiceError) as caught:
        runs.start(investigation_id)
    assert (caught.value.status_code, caught.value.code) == (409, "no_evidence")


def test_a_run_completes_and_records_every_stage(factory, settings, investigation_id):
    add_evidence(factory, settings, investigation_id)
    runs = manager(factory, settings)
    run_id = runs.start(investigation_id)
    assert runs.wait(run_id, timeout=60)
    view = fetch_run(factory, run_id)
    assert view["status"] == "completed" and view["error"] is None and view["stage"] == "report"
    assert view["started_at"] and view["finished_at"] and view["started_at"] <= view["finished_at"]
    assert [s["name"] for s in view["stages"]] == list(STAGES)
    for stage in view["stages"]:
        assert stage["status"] == "completed" and stage["error"] is None and stage["summary"] is not None
        assert stage["started_at"] and stage["finished_at"]
    assert view["stages"][0]["summary"]["records"] == 13
    assert view["stages"][4]["summary"]["groups"] == 2


def test_the_workspace_holds_the_results_and_the_evidence_becomes_ready(factory, settings, investigation_id):
    evidence_id = add_evidence(factory, settings, investigation_id)
    runs = manager(factory, settings)
    runs.wait(runs.start(investigation_id), timeout=60)
    (row,) = evidence_rows(factory, investigation_id)
    assert row[:3] == (evidence_id, "ready", 13) and row[3] is None and row[4]
    facts = workspace_facts(Workspace(settings.resolved_data_dir / "investigations" / str(investigation_id)))
    assert (facts.severity, facts.detections, facts.sessions, facts.timeline_events) == ("HIGH", 2, 1, 11)


def test_the_run_shows_progress_while_it_is_running(factory, settings, investigation_id):
    add_evidence(factory, settings, investigation_id)
    entered, release = threading.Event(), threading.Event()
    inner = fake_loader()

    def slow_loader(evtx, raw):
        entered.set()
        assert release.wait(30)
        return inner(evtx, raw)

    runs = manager(factory, settings, slow_loader)
    run_id = runs.start(investigation_id)
    assert entered.wait(30)
    view = fetch_run(factory, run_id)
    assert view["status"] == "running" and view["stage"] == "collect" and view["started_at"]
    assert view["stages"][0]["status"] == "running" and all(s["status"] == "pending" for s in view["stages"][1:])
    assert evidence_rows(factory, investigation_id)[0][1] == "processing"
    release.set()
    assert runs.wait(run_id, timeout=60)
    assert fetch_run(factory, run_id)["status"] == "completed"


def test_only_one_run_per_investigation_at_a_time(factory, settings, investigation_id):
    add_evidence(factory, settings, investigation_id)
    entered, release = threading.Event(), threading.Event()
    inner = fake_loader()

    def slow_loader(evtx, raw):
        entered.set()
        release.wait(30)
        return inner(evtx, raw)

    runs = manager(factory, settings, slow_loader)
    first = runs.start(investigation_id)
    assert entered.wait(30)
    with pytest.raises(ServiceError) as caught:
        runs.start(investigation_id)
    assert (caught.value.status_code, caught.value.code) == (409, "analysis_already_running")
    release.set()
    runs.wait(first, timeout=60)
    second = runs.start(investigation_id)
    assert second != first and runs.wait(second, timeout=60)


def test_different_investigations_can_run_at_the_same_time(factory, settings, investigation_id):
    with factory() as registry:
        other = create_investigation(registry, settings, analyst_id=1, title="Other").id
    add_evidence(factory, settings, investigation_id, 1)
    add_evidence(factory, settings, other, 2)
    runs = manager(factory, settings)
    a, b = runs.start(investigation_id), runs.start(other)
    assert runs.wait(a, 60) and runs.wait(b, 60)
    assert fetch_run(factory, a)["status"] == fetch_run(factory, b)["status"] == "completed"


def test_a_failing_evidence_file_fails_the_run_and_is_marked_failed(factory, settings, investigation_id):
    good = add_evidence(factory, settings, investigation_id, 1)
    bad = add_evidence(factory, settings, investigation_id, 2)
    runs = manager(factory, settings, fake_loader(failing_ids=(bad,)))
    run_id = runs.start(investigation_id)
    runs.wait(run_id, timeout=60)
    view = fetch_run(factory, run_id)
    assert view["status"] == "failed" and view["error"].startswith("Stage collect failed:") and "synthetic failure" in view["error"]
    assert view["stages"][0]["status"] == "failed" and "synthetic failure" in view["stages"][0]["error"]
    assert all(s["status"] == "pending" for s in view["stages"][1:])
    rows = {r[0]: r for r in evidence_rows(factory, investigation_id)}
    assert rows[bad][1] == "failed" and "synthetic failure" in rows[bad][3]
    assert rows[good][1] == "uploaded" and rows[good][3] is None


def test_a_failed_evidence_file_is_left_out_of_the_next_run(factory, settings, investigation_id):
    good = add_evidence(factory, settings, investigation_id, 1)
    bad = add_evidence(factory, settings, investigation_id, 2)
    loader = fake_loader(failing_ids=(bad,))
    runs = manager(factory, settings, loader)
    runs.wait(runs.start(investigation_id), 60)
    loader.calls.clear()
    second = runs.start(investigation_id)
    runs.wait(second, 60)
    assert fetch_run(factory, second)["status"] == "completed"
    assert bad not in loader.calls and good in loader.calls


def test_a_run_with_only_failed_evidence_cannot_start(factory, settings, investigation_id):
    bad = add_evidence(factory, settings, investigation_id)
    runs = manager(factory, settings, fake_loader(failing_ids=(bad,)))
    runs.wait(runs.start(investigation_id), 60)
    with pytest.raises(ServiceError) as caught:
        runs.start(investigation_id)
    assert caught.value.code == "no_evidence"


def test_a_failure_in_a_later_stage_restores_the_evidence_and_names_the_stage(factory, settings, investigation_id, monkeypatch):
    evidence_id = add_evidence(factory, settings, investigation_id)

    def broken(*_args, **_kwargs):
        raise RuntimeError("the timeline broke")

    monkeypatch.setattr("raven.services.pipeline.run_timeline", broken)
    runs = manager(factory, settings)
    run_id = runs.start(investigation_id)
    runs.wait(run_id, 60)
    view = fetch_run(factory, run_id)
    assert view["status"] == "failed" and view["error"] == "Stage timeline failed: the timeline broke"
    stages = {s["name"]: s["status"] for s in view["stages"]}
    assert stages["timeline"] == "failed" and stages["impact"] == "pending" and stages["reconstruct"] == "completed"
    assert evidence_rows(factory, investigation_id)[0][:2] == (evidence_id, "uploaded")


def test_an_unexpected_worker_failure_is_recorded_without_details(factory, settings, investigation_id, monkeypatch):
    add_evidence(factory, settings, investigation_id)
    runs = manager(factory, settings)

    def explode(self, run_id):
        raise ValueError("internal secret detail")

    monkeypatch.setattr(AnalysisRunManager, "_run", explode)
    run_id = runs.start(investigation_id)
    runs.wait(run_id, 30)
    view = fetch_run(factory, run_id)
    assert view["status"] == "failed" and view["error"] == "Unexpected error. See the server log." and "secret" not in json.dumps(view)


def test_a_second_run_reuses_the_collected_evidence(factory, settings, investigation_id):
    add_evidence(factory, settings, investigation_id)
    loader = fake_loader()
    runs = manager(factory, settings, loader)
    runs.wait(runs.start(investigation_id), 60)
    second = runs.start(investigation_id)
    runs.wait(second, 60)
    assert loader.calls == [1]
    view = fetch_run(factory, second)
    assert view["stages"][0]["summary"]["evidence"][0]["reused"] is True
    assert view["stages"][3]["summary"] == {"read": 13, "inserted": 0, "skipped_existing": 13}


def test_new_evidence_after_a_run_is_processed_by_the_next_run(factory, settings, investigation_id):
    add_evidence(factory, settings, investigation_id, 1)
    loader = fake_loader()
    runs = manager(factory, settings, loader)
    runs.wait(runs.start(investigation_id), 60)
    add_evidence(factory, settings, investigation_id, 2)
    second = runs.start(investigation_id)
    runs.wait(second, 60)
    view = fetch_run(factory, second)
    assert view["stages"][3]["summary"] == {"read": 26, "inserted": 13, "skipped_existing": 13}
    assert view["stages"][5]["summary"]["sessions"] == 2
    assert [r[1] for r in evidence_rows(factory, investigation_id)] == ["ready", "ready"]


def test_runs_interrupted_by_a_restart_are_marked_failed(factory, settings, investigation_id):
    evidence_id = add_evidence(factory, settings, investigation_id)
    with factory() as registry:
        evidence = registry.get(EvidenceSource, evidence_id)
        evidence.status = "processing"
        registry.add(AnalysisRun(investigation_id=investigation_id, status="running", stage="normalize", stages_json=json.dumps([
            {"name": "collect", "status": "completed", "started_at": "a", "finished_at": "b", "summary": {}, "error": None},
            {"name": "normalize", "status": "running", "started_at": "a", "finished_at": None, "summary": None, "error": None},
            {"name": "deduplicate", "status": "pending", "started_at": None, "finished_at": None, "summary": None, "error": None},
        ])))
        registry.add(AnalysisRun(investigation_id=investigation_id, status="queued", stages_json=None))
        registry.commit()
    runs = manager(factory, settings)
    assert runs.recover_interrupted() == 2
    with factory() as registry:
        latest = latest_run(registry, investigation_id)
        assert latest.status == "failed" and latest.error == "Interrupted by a server restart." and latest.finished_at
    assert evidence_rows(factory, investigation_id)[0][1] == "uploaded"
    running = fetch_run(factory, 1)
    assert [s["status"] for s in running["stages"]] == ["completed", "failed", "pending"]
    assert runs.recover_interrupted() == 0
    add_more = runs.start(investigation_id)
    assert runs.wait(add_more, 60)


def test_waiting_for_an_unknown_run_returns_at_once(factory, settings):
    assert manager(factory, settings).wait(12345, timeout=0.1) is True


def test_the_run_view_of_a_run_without_stages_is_empty(factory, settings, investigation_id):
    with factory() as registry:
        run = AnalysisRun(investigation_id=investigation_id, status="queued")
        registry.add(run)
        registry.commit()
        assert run_view(run)["stages"] == []
