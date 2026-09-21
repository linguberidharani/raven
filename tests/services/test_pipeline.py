"""Unit tests for the pipeline orchestration on SYNTHETIC evidence (a fake loader replaces the EVTX reader)."""

import json

import pytest

from raven.services.pipeline import STAGES, EvidenceInfo, PipelineError, run_full_pipeline
from raven.services.workspace import Workspace
from tests.synthetic import fake_loader


@pytest.fixture
def workspace(tmp_path):
    return Workspace(tmp_path / "data" / "investigations" / "1").ensure()


def run(workspace, evidence, loader, events=None):
    def on_stage(name, status, summary=None, error=None):
        if events is not None:
            events.append((name, status))

    return run_full_pipeline(workspace, evidence, loader=loader, on_stage=on_stage)


def test_the_stages_run_in_order_and_report_running_then_completed(workspace):
    events = []
    results = run(workspace, [EvidenceInfo(1)], fake_loader(), events)
    assert list(results) == list(STAGES)
    assert events == [(name, status) for name in STAGES for status in ("running", "completed")]


def test_every_stage_reports_its_numbers(workspace):
    results = run(workspace, [EvidenceInfo(1)], fake_loader())
    assert results["collect"] == {"evidence": [{"evidence_id": 1, "records": 13, "reused": False}], "records": 13}
    assert results["normalize"]["events"] == 13 and results["normalize"]["status_counts"] == {"OK": 13}
    assert results["normalize"]["event_type_counts"] == {"file_create": 12, "process_creation": 1}
    assert results["deduplicate"] == {"input": 13, "unique": 13, "removed": 0}
    assert results["ingest"] == {"read": 13, "inserted": 13, "skipped_existing": 0}
    assert results["correlate"]["groups"] == 2 and results["correlate"]["groups_by_rule"] == {"RAVEN-R001": 1, "RAVEN-R002": 0, "RAVEN-R003": 1}
    assert results["correlate"]["distinct_events"] == 11
    assert results["reconstruct"] == {"sessions": 1, "groups": 2}
    assert results["timeline"] == {"timeline_events": 11}
    (session,) = results["impact"]["sessions"]
    assert session["scores"] == {"files_affected": 10, "network_activity": 0, "process_activity": 1, "unsupported_events": 0}
    assert session["events"] == {"files_affected": 10, "network_activity": 0, "process_activity": 1, "unsupported_events": 0}
    assert len(results["rarf"]["files"]) == 1 and results["rarf"]["traceability"][0]["event_ids"] == 11
    assert len(results["report"]["files"]) == 1
    assert results["report"]["observed_findings"] > 0 and results["report"]["derived_findings"] > 0


def test_the_files_of_a_run_are_in_the_workspace(workspace):
    run(workspace, [EvidenceInfo(1)], fake_loader())
    names = {p.relative_to(workspace.root).as_posix() for p in workspace.root.rglob("*") if p.is_file()}
    assert {"raw/evidence-1.jsonl", "processed/evidence-1.normalized.jsonl", "processed/normalized.jsonl", "processed/deduplicated.jsonl", "raven.db"} <= names
    assert any(n.startswith("processed/rarf/RARF-RAVEN-SESSION-") for n in names)
    assert any(n.startswith("processed/report/REPORT-RAVEN-SESSION-") for n in names)
    for summary in ("ingest", "correlation", "sessions_mapping", "timeline", "impact"):
        assert f"processed/{summary}.json" in names


def test_raw_event_references_carry_the_evidence_id(workspace):
    run(workspace, [EvidenceInfo(7)], fake_loader(seed_of=lambda _id: 0))
    first = json.loads(workspace.deduplicated_path.read_text(encoding="utf-8").splitlines()[0])
    assert first["raw_event_ref"] == "7:1"


def test_two_evidence_files_are_processed_together(workspace):
    results = run(workspace, [EvidenceInfo(2), EvidenceInfo(1)], fake_loader())
    assert [e["evidence_id"] for e in results["collect"]["evidence"]] == [1, 2]
    assert results["collect"]["records"] == 26 and results["deduplicate"]["unique"] == 26
    assert results["reconstruct"]["sessions"] == 2 and results["timeline"]["timeline_events"] == 22
    refs = {json.loads(line)["raw_event_ref"] for line in workspace.deduplicated_path.read_text(encoding="utf-8").splitlines()}
    assert len(refs) == 26 and {"1:1", "2:1"} <= refs


def test_identical_events_of_two_evidence_files_are_deduplicated(workspace):
    results = run(workspace, [EvidenceInfo(1), EvidenceInfo(2)], fake_loader(seed_of=lambda _id: 0))
    assert results["deduplicate"] == {"input": 26, "unique": 13, "removed": 13}
    assert results["reconstruct"]["sessions"] == 1


def test_running_again_gives_identical_results_and_files(workspace):
    first = run(workspace, [EvidenceInfo(1)], fake_loader())
    rarf_name = first["rarf"]["files"][0]
    before = (workspace.rarf_dir / rarf_name).read_bytes()
    report_before = next(workspace.report_dir.iterdir()).read_bytes()
    second = run(workspace, [EvidenceInfo(1)], fake_loader())
    assert second["ingest"] == {"read": 13, "inserted": 0, "skipped_existing": 13}
    for stage in ("collect", "normalize", "deduplicate", "correlate", "reconstruct", "timeline", "impact", "rarf", "report"):
        assert second[stage] == first[stage]
    assert (workspace.rarf_dir / rarf_name).read_bytes() == before
    assert next(workspace.report_dir.iterdir()).read_bytes() == report_before


def test_an_evidence_file_that_is_already_collected_is_reused(workspace):
    loader = fake_loader()
    run(workspace, [EvidenceInfo(1)], loader)
    again = fake_loader()
    results = run(workspace, [EvidenceInfo(1, ready=True, events_total=13)], again)
    assert again.calls == [] and results["collect"]["evidence"] == [{"evidence_id": 1, "records": 13, "reused": True}]
    assert results["deduplicate"]["unique"] == 13


def test_a_ready_file_without_its_raw_file_is_read_again(workspace):
    loader = fake_loader()
    results = run(workspace, [EvidenceInfo(1, ready=True, events_total=13)], loader)
    assert loader.calls == [1] and results["collect"]["evidence"][0]["reused"] is False


def test_a_failing_evidence_file_stops_the_run_at_collect_and_names_the_file(workspace):
    events = []
    with pytest.raises(PipelineError) as caught:
        run(workspace, [EvidenceInfo(1), EvidenceInfo(2)], fake_loader(failing_ids=(2,)), events)
    assert (caught.value.stage, caught.value.evidence_id) == ("collect", 2)
    assert "synthetic failure" in caught.value.message
    assert events == [("collect", "running"), ("collect", "failed")]
    assert not workspace.deduplicated_path.exists()


def test_a_failure_in_a_later_stage_names_the_stage(workspace, monkeypatch):
    def broken(*_args, **_kwargs):
        raise RuntimeError("the correlation engine broke")

    monkeypatch.setattr("raven.services.pipeline.run_correlation", broken)
    events = []
    with pytest.raises(PipelineError) as caught:
        run(workspace, [EvidenceInfo(1)], fake_loader(), events)
    assert (caught.value.stage, caught.value.evidence_id) == ("correlate", None)
    assert caught.value.message == "the correlation engine broke"
    assert events[-2:] == [("correlate", "running"), ("correlate", "failed")]


def test_workspaces_are_isolated(tmp_path):
    a = Workspace(tmp_path / "data" / "investigations" / "1").ensure()
    b = Workspace(tmp_path / "data" / "investigations" / "2").ensure()
    run(a, [EvidenceInfo(1)], fake_loader())
    assert not any(b.root.rglob("*.jsonl")) and not b.db_path.exists()
    results_b = run(b, [EvidenceInfo(5)], fake_loader(seed_of=lambda _id: 3))
    assert results_b["ingest"]["inserted"] == 13
    written = {p for p in (tmp_path / "data").rglob("*") if p.is_file()}
    assert all(a.root in p.parents or b.root in p.parents for p in written)
