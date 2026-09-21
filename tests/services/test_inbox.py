"""Unit tests for the inbox service and watcher. Temporary directories and SYNTHETIC records only."""

import hashlib
import json
import threading
import time

import pytest
from sqlalchemy import insert, select

from raven.config import Settings
from raven.database.registry_models import AnalysisRun, CollectorCursor, EvidenceSource, User
from raven.database.session import open_registry_database
from raven.services.analysis_runs import AnalysisRunManager, run_view
from raven.services.errors import ServiceError
from raven.services.inbox import EMPTY_SHA256, InboxWatcher, collector_sources, inbox_file, link_source, list_inbox
from raven.services.investigations import create_investigation, latest_run, workspace_facts
from raven.services.workspace import Workspace
from tests.synthetic import fake_loader, raw_lines, synthetic_raw_records

RECORDS = synthetic_raw_records(1)  # 13 records: a process creation and 12 file creations of process 1001


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, env="test", data_dir=tmp_path / "data", inbox_dir=tmp_path / "inbox", inbox_poll_seconds=0)


@pytest.fixture
def factory(tmp_path):
    factory = open_registry_database(tmp_path / "registry.db")
    with factory.kw["bind"].begin() as connection:
        connection.execute(insert(User).values(name="Ada", email="ada@example.com", password_hash="h", created_at="2026-09-13T08:39:49.545Z"))
    yield factory
    factory.kw["bind"].dispose()


@pytest.fixture
def investigation_id(factory, settings):
    settings.resolved_inbox_dir.mkdir(parents=True, exist_ok=True)
    with factory() as registry:
        return create_investigation(registry, settings, analyst_id=1, title="Live case").id


@pytest.fixture
def runs(factory, settings):
    return AnalysisRunManager(factory, settings, loader=fake_loader())


@pytest.fixture
def watcher(factory, settings, runs):
    return InboxWatcher(factory, settings, runs)


def source_path(settings, name="sysmon-LAB.jsonl"):
    return settings.resolved_inbox_dir / name


def append(settings, records, name="sysmon-LAB.jsonl", raw=None):
    with open(source_path(settings, name), "a", encoding="utf-8", newline="") as handle:
        handle.write(raw_lines(records) if raw is None else raw)


def link(factory, settings, investigation_id, name="sysmon-LAB.jsonl"):
    with factory() as registry:
        return link_source(registry, settings, investigation_id, name).id


def evidence_row(factory, evidence_id):
    with factory() as registry:
        row = registry.get(EvidenceSource, evidence_id)
        return {"status": row.status, "events_total": row.events_total, "size_bytes": row.size_bytes, "sha256": row.sha256, "error": row.error}


def cursor_row(factory, name="sysmon-LAB.jsonl"):
    with factory() as registry:
        row = registry.scalars(select(CollectorCursor).where(CollectorCursor.source_name == name)).one()
        return {"offset": row.last_offset, "record": row.last_record_id, "updated_at": row.updated_at}


def raw_file(settings, investigation_id, evidence_id):
    return settings.resolved_data_dir / "investigations" / str(investigation_id) / "raw" / f"evidence-{evidence_id}.jsonl"


def finish_runs(factory, runs, investigation_id):
    with factory() as registry:
        run = latest_run(registry, investigation_id)
    assert run is not None and runs.wait(run.id, 60)
    with factory() as registry:
        return run_view(registry.get(AnalysisRun, run.id))


def poll_and_wait(watcher, factory, runs, investigation_id):
    """One look at the inbox, then wait for the analysis run it started (if any); returns the poll outcome."""
    outcome = watcher.poll_once()
    if investigation_id in outcome.analyses_started:
        finish_runs(factory, runs, investigation_id)
    return outcome


# ---------------------------------------------------------------- names and paths


@pytest.mark.parametrize("name", ["../x.jsonl", "a b.jsonl", "x.txt", "a/b.jsonl", "a\\b.jsonl", "", ".jsonl"])
def test_only_plain_jsonl_names_give_a_path(settings, name):
    with pytest.raises(ServiceError) as caught:
        inbox_file(settings, name)
    assert (caught.value.status_code, caught.value.code) == (422, "invalid_source_name")


def test_a_valid_name_gives_a_path_inside_the_inbox(settings):
    assert inbox_file(settings, "sysmon-LAB.jsonl") == settings.resolved_inbox_dir.resolve() / "sysmon-LAB.jsonl"


# ---------------------------------------------------------------- listing and linking


def test_the_inbox_lists_plain_jsonl_files_and_their_links(factory, settings, investigation_id):
    append(settings, RECORDS[:2], "a.jsonl")
    append(settings, RECORDS[:1], "b.jsonl")
    (settings.resolved_inbox_dir / "notes.txt").write_text("x", encoding="utf-8")
    (settings.resolved_inbox_dir / "bad name.jsonl").write_text("x", encoding="utf-8")
    (settings.resolved_inbox_dir / "folder.jsonl").mkdir()
    link(factory, settings, investigation_id, "b.jsonl")
    with factory() as registry:
        items = list_inbox(registry, settings)
    assert [i["source_name"] for i in items] == ["a.jsonl", "b.jsonl"]
    assert items[0]["investigation_id"] is None and items[0]["investigation_code"] is None
    assert items[1]["investigation_id"] == investigation_id and items[1]["investigation_code"].startswith("INV-")
    assert items[0]["size_bytes"] == len(raw_lines(RECORDS[:2]).encode()) and items[0]["modified_at"].endswith("Z")


def test_the_inbox_of_a_missing_folder_is_empty(factory, tmp_path):
    settings = Settings(_env_file=None, env="test", data_dir=tmp_path / "data", inbox_dir=tmp_path / "nowhere", inbox_poll_seconds=0)
    with factory() as registry:
        assert list_inbox(registry, settings) == []


def test_linking_creates_an_evidence_source_and_a_cursor(factory, settings, investigation_id):
    append(settings, RECORDS[:2])
    evidence_id = link(factory, settings, investigation_id)
    assert evidence_row(factory, evidence_id) == {"status": "uploaded", "events_total": 0, "size_bytes": 0, "sha256": EMPTY_SHA256, "error": None}
    assert cursor_row(factory)["offset"] == 0 and cursor_row(factory)["record"] is None
    with factory() as registry:
        row = registry.get(EvidenceSource, evidence_id)
        assert (row.source_type, row.filename, row.investigation_id) == ("vm_collector", "sysmon-LAB.jsonl", investigation_id)
        (source,) = collector_sources(registry, investigation_id)
    assert source == {"source_name": "sysmon-LAB.jsonl", "evidence_id": evidence_id, "last_offset": 0, "last_record_id": None,
                      "updated_at": source["updated_at"], "status": "uploaded", "events_total": 0, "error": None}


def test_linking_needs_a_file_an_investigation_and_a_free_name(factory, settings, investigation_id):
    with factory() as registry:
        with pytest.raises(ServiceError) as caught:
            link_source(registry, settings, investigation_id, "missing.jsonl")
        assert (caught.value.status_code, caught.value.code) == (404, "inbox_file_not_found")
        with pytest.raises(ServiceError) as caught:
            link_source(registry, settings, 999, "missing.jsonl")
        assert caught.value.code == "investigation_not_found"
        with pytest.raises(ServiceError) as caught:
            link_source(registry, settings, investigation_id, "../x.jsonl")
        assert caught.value.code == "invalid_source_name"
    append(settings, RECORDS[:1])
    link(factory, settings, investigation_id)
    with factory() as registry:
        other = create_investigation(registry, settings, analyst_id=1, title="Other").id
        with pytest.raises(ServiceError) as caught:
            link_source(registry, settings, other, "sysmon-LAB.jsonl")
    assert (caught.value.status_code, caught.value.code) == (409, "source_already_linked")


# ---------------------------------------------------------------- new data appears without a manual rebuild


def test_new_records_are_taken_over_and_an_analysis_run_is_started(factory, settings, investigation_id, watcher, runs):
    append(settings, RECORDS[:4])
    evidence_id = link(factory, settings, investigation_id)
    outcome = watcher.poll_once()
    (result,) = outcome.results
    assert (result.records_added, result.rejected, result.error, result.skipped) == (4, 0, None, None)
    assert outcome.analyses_started == [investigation_id]
    size = len(raw_lines(RECORDS[:4]).encode())
    assert result.offset == size and cursor_row(factory) == {"offset": size, "record": 4, "updated_at": cursor_row(factory)["updated_at"]}
    raw = raw_file(settings, investigation_id, evidence_id).read_text(encoding="utf-8")
    assert raw == raw_lines(RECORDS[:4])
    view = finish_runs(factory, runs, investigation_id)
    assert view["status"] == "completed" and view["stages"][0]["summary"]["records"] == 4
    assert evidence_row(factory, evidence_id) == {"status": "ready", "events_total": 4, "size_bytes": size, "sha256": hashlib.sha256(source_path(settings).read_bytes()).hexdigest().upper(), "error": None}
    assert workspace_facts(Workspace(settings.resolved_data_dir / "investigations" / str(investigation_id))).detections == 0


def test_later_records_appear_in_the_investigation_without_any_manual_step(factory, settings, investigation_id, watcher, runs):
    append(settings, RECORDS[:4])
    evidence_id = link(factory, settings, investigation_id)
    watcher.poll_once()
    finish_runs(factory, runs, investigation_id)
    workspace = Workspace(settings.resolved_data_dir / "investigations" / str(investigation_id))
    assert workspace_facts(workspace).timeline_events == 0

    append(settings, RECORDS[4:])
    outcome = watcher.poll_once()
    assert outcome.results[0].records_added == 9 and outcome.analyses_started == [investigation_id]
    view = finish_runs(factory, runs, investigation_id)
    assert view["status"] == "completed"
    facts = workspace_facts(workspace)
    assert (facts.severity, facts.detections, facts.sessions, facts.timeline_events) == ("HIGH", 2, 1, 11)
    assert raw_file(settings, investigation_id, evidence_id).read_text(encoding="utf-8") == raw_lines(RECORDS)
    assert evidence_row(factory, evidence_id)["status"] == "ready" and evidence_row(factory, evidence_id)["events_total"] == 13


def test_a_look_without_new_data_changes_nothing_and_starts_no_run(factory, settings, investigation_id, watcher, runs):
    append(settings, RECORDS)
    link(factory, settings, investigation_id)
    watcher.poll_once()
    finish_runs(factory, runs, investigation_id)
    before = cursor_row(factory)
    outcome = watcher.poll_once()
    assert outcome.results[0].records_added == 0 and outcome.analyses_started == []
    assert cursor_row(factory) == before


def test_a_line_that_is_still_being_written_is_left_for_the_next_look(factory, settings, investigation_id, watcher, runs):
    text = raw_lines(RECORDS[:3])
    partial = raw_lines(RECORDS[3:4]).rstrip("\n")[:30]
    append(settings, [], raw=text + partial)
    link(factory, settings, investigation_id)
    assert poll_and_wait(watcher, factory, runs, investigation_id).results[0].records_added == 3
    assert cursor_row(factory)["offset"] == len(text.encode())
    append(settings, [], raw=raw_lines(RECORDS[3:4]).rstrip("\n")[30:] + "\n")
    assert poll_and_wait(watcher, factory, runs, investigation_id).results[0].records_added == 1


def test_invalid_lines_are_skipped_and_reported(factory, settings, investigation_id, watcher):
    append(settings, [], raw=raw_lines(RECORDS[:2]) + "{oops\n" + json.dumps({"event_id": 1}) + "\n" + raw_lines(RECORDS[2:3]))
    evidence_id = link(factory, settings, investigation_id)
    result = watcher.poll_once().results[0]
    assert (result.records_added, result.rejected) == (3, 2)
    error = evidence_row(factory, evidence_id)["error"]
    assert error.startswith("2 invalid line(s) were skipped; first: line at byte") and "not valid JSON" in error


# ---------------------------------------------------------------- duplicate-safe


def test_records_that_are_written_again_are_not_added_twice(factory, settings, investigation_id, watcher, runs):
    append(settings, RECORDS[:6])
    evidence_id = link(factory, settings, investigation_id)
    poll_and_wait(watcher, factory, runs, investigation_id)
    append(settings, RECORDS[:6])  # the collector started over
    result = poll_and_wait(watcher, factory, runs, investigation_id).results[0]
    assert result.records_added == 0
    assert raw_file(settings, investigation_id, evidence_id).read_text(encoding="utf-8") == raw_lines(RECORDS[:6])
    assert cursor_row(factory)["offset"] == len(raw_lines(RECORDS[:6] + RECORDS[:6]).encode())


def test_a_lost_cursor_does_not_duplicate_records(factory, settings, investigation_id, watcher, runs):
    append(settings, RECORDS[:6])
    evidence_id = link(factory, settings, investigation_id)
    poll_and_wait(watcher, factory, runs, investigation_id)
    with factory() as registry:  # a crash between writing the records and saving the cursor
        cursor = registry.scalars(select(CollectorCursor)).one()
        cursor.last_offset = 0
        registry.commit()
    result = poll_and_wait(watcher, factory, runs, investigation_id).results[0]
    assert result.records_added == 0
    assert raw_file(settings, investigation_id, evidence_id).read_text(encoding="utf-8") == raw_lines(RECORDS[:6])


def test_a_repeated_record_inside_one_batch_is_added_once(factory, settings, investigation_id, watcher):
    append(settings, RECORDS[:3] + RECORDS[:3])
    link(factory, settings, investigation_id)
    assert watcher.poll_once().results[0].records_added == 3


def test_records_with_a_smaller_record_id_but_another_time_are_new(factory, settings, investigation_id, watcher, runs):
    append(settings, RECORDS[:6])
    link(factory, settings, investigation_id)
    poll_and_wait(watcher, factory, runs, investigation_id)
    restored = [{**record, "time_created": record["time_created"].replace("2026-09-13", "2026-09-14")} for record in RECORDS[:3]]  # e.g. after a snapshot restore
    append(settings, restored)
    assert poll_and_wait(watcher, factory, runs, investigation_id).results[0].records_added == 3


# ---------------------------------------------------------------- problems with the file


def test_a_missing_file_is_reported_and_the_error_clears_when_it_comes_back(factory, settings, investigation_id, watcher, runs):
    append(settings, RECORDS[:2])
    evidence_id = link(factory, settings, investigation_id)
    source_path(settings).unlink()
    result = watcher.poll_once().results[0]
    assert result.error == "The inbox file is missing." and evidence_row(factory, evidence_id)["error"] == "The inbox file is missing."
    append(settings, RECORDS[:2])
    assert poll_and_wait(watcher, factory, runs, investigation_id).results[0].records_added == 2
    assert evidence_row(factory, evidence_id)["error"] is None


def test_a_file_that_was_replaced_by_a_shorter_one_is_reported_and_nothing_changes(factory, settings, investigation_id, watcher, runs):
    append(settings, RECORDS[:6])
    evidence_id = link(factory, settings, investigation_id)
    poll_and_wait(watcher, factory, runs, investigation_id)
    before = raw_file(settings, investigation_id, evidence_id).read_text(encoding="utf-8")
    source_path(settings).write_text(raw_lines(RECORDS[:1]), encoding="utf-8")
    result = poll_and_wait(watcher, factory, runs, investigation_id).results[0]
    assert result.error.startswith("The file is smaller than the saved position") and result.records_added == 0
    assert evidence_row(factory, evidence_id)["error"].startswith("The file is smaller")
    assert raw_file(settings, investigation_id, evidence_id).read_text(encoding="utf-8") == before


def test_unlinked_files_are_ignored(factory, settings, investigation_id, watcher):
    append(settings, RECORDS, "stranger.jsonl")
    assert watcher.poll_once().results == []
    assert not (settings.resolved_data_dir / "investigations" / str(investigation_id) / "raw").exists() or not list((settings.resolved_data_dir / "investigations" / str(investigation_id) / "raw").iterdir())


# ---------------------------------------------------------------- analysis runs and the watcher


def test_data_waits_while_an_analysis_run_is_active(factory, settings, investigation_id, watcher, runs):
    append(settings, RECORDS[:4])
    evidence_id = link(factory, settings, investigation_id)
    with factory() as registry:
        registry.add(AnalysisRun(investigation_id=investigation_id, status="running", stages_json="[]"))
        registry.commit()
    append(settings, RECORDS[4:])
    result = watcher.poll_once().results[0]
    assert result.skipped and "analysis run is active" in result.skipped and result.records_added == 0
    assert cursor_row(factory)["offset"] == 0 and not raw_file(settings, investigation_id, evidence_id).exists()
    with factory() as registry:
        registry.execute(AnalysisRun.__table__.update().values(status="completed"))
        registry.commit()
    outcome = watcher.poll_once()
    assert outcome.results[0].records_added == 13 and outcome.analyses_started == [investigation_id]


def test_data_that_arrives_during_a_run_keeps_the_source_uploaded_until_the_next_run(factory, settings, investigation_id, watcher, runs, monkeypatch):
    append(settings, RECORDS[:4])
    evidence_id = link(factory, settings, investigation_id)
    entered, release = threading.Event(), threading.Event()
    import raven.services.pipeline as pipeline

    original = pipeline.run_correlation

    def slow(*args, **kwargs):
        entered.set()
        assert release.wait(30)
        return original(*args, **kwargs)

    monkeypatch.setattr(pipeline, "run_correlation", slow)
    assert watcher.poll_once().analyses_started == [investigation_id]
    assert entered.wait(30)
    with factory() as registry:  # what the watcher would have done for data that arrived just now
        registry.get(EvidenceSource, evidence_id).events_total += 5
        registry.commit()
    release.set()
    finish_runs(factory, runs, investigation_id)
    assert evidence_row(factory, evidence_id)["status"] == "uploaded"
    monkeypatch.setattr(pipeline, "run_correlation", original)
    assert watcher.poll_once().analyses_started == [investigation_id]
    finish_runs(factory, runs, investigation_id)
    assert evidence_row(factory, evidence_id)["status"] == "ready"


def test_a_failed_run_is_not_retried_in_a_loop_but_new_data_starts_a_new_one(factory, settings, investigation_id, watcher, runs, monkeypatch):
    import raven.services.pipeline as pipeline

    original = pipeline.run_correlation

    def broken(*_args, **_kwargs):
        raise RuntimeError("the engine broke")

    monkeypatch.setattr(pipeline, "run_correlation", broken)
    append(settings, RECORDS[:4])
    link(factory, settings, investigation_id)
    assert watcher.poll_once().analyses_started == [investigation_id]
    assert finish_runs(factory, runs, investigation_id)["status"] == "failed"
    assert watcher.poll_once().analyses_started == []
    assert watcher.poll_once().analyses_started == []
    monkeypatch.setattr(pipeline, "run_correlation", original)
    append(settings, RECORDS[4:])
    assert watcher.poll_once().analyses_started == [investigation_id]
    assert finish_runs(factory, runs, investigation_id)["status"] == "completed"


def test_uploaded_evtx_evidence_never_starts_a_run_by_itself(factory, settings, investigation_id, watcher):
    with factory() as registry:
        registry.add(EvidenceSource(investigation_id=investigation_id, filename="x.evtx", sha256="A" * 64, size_bytes=5, source_type="evtx_upload", status="uploaded", events_total=9, created_at="t"))
        registry.commit()
    assert watcher.poll_once().analyses_started == []


def test_a_source_linked_but_still_empty_starts_nothing(factory, settings, investigation_id, watcher):
    append(settings, [], raw="")
    link(factory, settings, investigation_id)
    outcome = watcher.poll_once()
    assert outcome.results[0].records_added == 0 and outcome.analyses_started == []


def test_two_investigations_take_over_their_own_files(factory, settings, investigation_id, watcher, runs):
    with factory() as registry:
        other = create_investigation(registry, settings, analyst_id=1, title="Other").id
    append(settings, RECORDS[:7], "one.jsonl")
    append(settings, synthetic_raw_records(2)[:7], "two.jsonl")
    link(factory, settings, investigation_id, "one.jsonl")
    link(factory, settings, other, "two.jsonl")
    outcome = watcher.poll_once()
    assert {(r.source_name, r.records_added) for r in outcome.results} == {("one.jsonl", 7), ("two.jsonl", 7)}
    assert sorted(outcome.analyses_started) == sorted([investigation_id, other])
    for number in (investigation_id, other):
        finish_runs(factory, runs, number)
    assert workspace_facts(Workspace(settings.resolved_data_dir / "investigations" / str(investigation_id))).detections == 1
    assert workspace_facts(Workspace(settings.resolved_data_dir / "investigations" / str(other))).detections == 1


def test_the_watcher_thread_takes_over_new_data_by_itself(factory, tmp_path, runs):
    settings = Settings(_env_file=None, env="test", data_dir=tmp_path / "data", inbox_dir=tmp_path / "inbox", inbox_poll_seconds=1)
    settings.resolved_inbox_dir.mkdir(parents=True, exist_ok=True)
    with factory() as registry:
        investigation = create_investigation(registry, settings, analyst_id=1, title="Threaded").id
    watcher = InboxWatcher(factory, settings, AnalysisRunManager(factory, settings, loader=fake_loader()))
    append(settings, RECORDS)
    evidence_id = link(factory, settings, investigation)
    watcher.start()
    try:
        deadline = time.time() + 40
        while time.time() < deadline and evidence_row(factory, evidence_id)["status"] != "ready":
            time.sleep(0.2)
        assert evidence_row(factory, evidence_id)["status"] == "ready" and evidence_row(factory, evidence_id)["events_total"] == 13
        assert workspace_facts(Workspace(settings.resolved_data_dir / "investigations" / str(investigation))).timeline_events == 11
    finally:
        watcher.stop()
    assert watcher._thread is None


def test_the_watcher_does_not_start_a_thread_when_the_interval_is_zero(factory, settings, runs):
    watcher = InboxWatcher(factory, settings, runs)
    watcher.start()
    assert watcher._thread is None
    watcher.stop()
