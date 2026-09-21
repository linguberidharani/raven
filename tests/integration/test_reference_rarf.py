"""S9 acceptance on the reference EVTX (spec sections 6.5b, 6.10 and 12): the RARF JSON of the one attack
session is valid and its traceability counts are 597 event IDs, 597 raw event references, 87 correlation
group IDs and 4 impact analysis IDs (and 597 timeline event IDs).

The database with the correlation groups comes from the shared fixture in conftest.py (reference file
needed, otherwise these tests are skipped). Everything is written to temporary directories.
"""

import json

import pytest

from raven.database.session import open_workspace_database
from raven.impact.persist import run_impact
from raven.rarf.exporter import export_rarf
from raven.rarf.schema import validate_rarf
from raven.reconstruction.persist import run_reconstruction
from raven.timeline.persist import run_timeline

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def exported(reference_db, tmp_path_factory):
    directory = tmp_path_factory.mktemp("reference_s9")
    factory = open_workspace_database(reference_db)
    try:
        run_reconstruction(factory, None)
        run_timeline(factory)
        run_impact(factory)
        first = export_rarf(factory, directory / "first")
        second = export_rarf(factory, directory / "second")
    finally:
        factory.kw["bind"].dispose()
    return {"first": first, "second": second}


def test_one_valid_rarf_file(exported):
    (item,) = exported["first"]
    assert item.path.name == "RARF-" + item.session_id + ".json"
    assert item.session_id.startswith("RAVEN-SESSION-Dharani-")
    document = json.loads(item.path.read_text(encoding="utf-8"))
    assert validate_rarf(document) == []
    assert document["rarf_version"] == "1.0" and document["rarf_id"] == "RARF-" + item.session_id


def test_traceability_counts_597_597_87_4(exported):
    (item,) = exported["first"]
    trace = item.document["traceability"]
    assert len(trace["event_ids"]) == 597
    assert len(trace["raw_event_refs"]) == 597
    assert len(trace["correlation_group_ids"]) == 87
    assert len(trace["impact_analysis_ids"]) == 4
    assert len(trace["timeline_event_ids"]) == 597


def test_the_sections_hold_the_reference_numbers(exported):
    (item,) = exported["first"]
    document = item.document
    assert document["attack_session"]["computer"] == "Dharani"
    assert document["attack_session"]["severity"] == "HIGH" and document["attack_session"]["confidence"] is None
    assert len(document["detection"]["correlation_groups"]) == 87
    assert [rule["rule_id"] for rule in document["detection"]["rules"]] == ["RAVEN-R001", "RAVEN-R002", "RAVEN-R003"]
    assert len(document["detection"]["event_ids"]) == 597
    assert len(document["timeline"]["events"]) == 597
    scores = {name: category["impact_score"] for name, category in document["impact"]["categories"].items()}
    assert scores == {"files_affected": 475, "network_activity": 12, "process_activity": 14, "unsupported_events": 0}


def test_exporting_again_gives_byte_identical_files(exported):
    (first,), (second,) = exported["first"], exported["second"]
    assert first.path.read_bytes() == second.path.read_bytes()
    assert first.path.stat().st_size > 0
