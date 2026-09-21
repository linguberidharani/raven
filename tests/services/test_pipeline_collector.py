"""Unit tests for the pipeline with vm_collector evidence (no EVTX reader is used). SYNTHETIC records only."""

import pytest

from raven.collectors.raw_jsonl import write_raw_jsonl
from raven.services.pipeline import EvidenceInfo, run_full_pipeline
from raven.services.workspace import Workspace
from tests.synthetic import fake_loader, synthetic_raw_records


@pytest.fixture
def workspace(tmp_path):
    return Workspace(tmp_path / "data" / "investigations" / "1").ensure()


def collector(evidence_id=1, ready=False, total=0):
    return EvidenceInfo(evidence_id, ready, total, "vm_collector")


def test_a_collector_source_is_counted_not_read(workspace):
    write_raw_jsonl(synthetic_raw_records(1), workspace.raw_path(1))
    loader = fake_loader()
    results = run_full_pipeline(workspace, [collector()], loader=loader)
    assert loader.calls == []
    assert results["collect"] == {"evidence": [{"evidence_id": 1, "records": 13, "reused": True}], "records": 13}
    assert results["correlate"]["groups"] == 2 and results["timeline"]["timeline_events"] == 11


def test_a_collector_source_without_data_gives_an_empty_but_complete_run(workspace):
    results = run_full_pipeline(workspace, [collector()], loader=fake_loader())
    assert results["collect"]["records"] == 0 and results["normalize"]["events"] == 0
    assert results["deduplicate"] == {"input": 0, "unique": 0, "removed": 0}
    assert results["reconstruct"]["sessions"] == 0 and results["rarf"]["files"] == [] and results["report"]["files"] == []


def test_a_collector_source_and_an_uploaded_file_are_processed_together(workspace):
    write_raw_jsonl(synthetic_raw_records(1), workspace.raw_path(1))
    results = run_full_pipeline(workspace, [collector(1), EvidenceInfo(2)], loader=fake_loader())
    assert [(e["evidence_id"], e["reused"]) for e in results["collect"]["evidence"]] == [(1, True), (2, False)]
    assert results["collect"]["records"] == 26 and results["reconstruct"]["sessions"] == 2


def test_the_same_result_whether_the_data_came_at_once_or_in_pieces(tmp_path):
    whole = Workspace(tmp_path / "a").ensure()
    pieces = Workspace(tmp_path / "b").ensure()
    records = synthetic_raw_records(1)
    write_raw_jsonl(records, whole.raw_path(1))
    first = run_full_pipeline(whole, [collector()], loader=fake_loader())
    write_raw_jsonl(records[:5], pieces.raw_path(1))
    run_full_pipeline(pieces, [collector()], loader=fake_loader())
    write_raw_jsonl(records[:9], pieces.raw_path(1))
    run_full_pipeline(pieces, [collector()], loader=fake_loader())
    write_raw_jsonl(records, pieces.raw_path(1))
    last = run_full_pipeline(pieces, [collector()], loader=fake_loader())
    for stage in ("collect", "normalize", "deduplicate", "correlate", "reconstruct", "timeline", "impact", "rarf", "report"):
        assert last[stage] == first[stage], stage
    assert last["ingest"] == {"read": 13, "inserted": 4, "skipped_existing": 9}
    name = first["rarf"]["files"][0]
    assert (pieces.rarf_dir / name).read_bytes() == (whole.rarf_dir / name).read_bytes()
