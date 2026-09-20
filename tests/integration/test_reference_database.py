"""S4 acceptance on the reference EVTX (spec sections 6.3, 6.5b and 12): 2816 events, 97 duplicates
removed, 2719 unique events, 0 duplicate fingerprints left, a database with 2719 events, and a second
ingest that inserts 0.

The spec also states how the 2719 split: 1962 events with status OK and 757 unsupported.

The reference file is real telemetry and is never committed (*.evtx is ignored). Put it at
tests/fixtures/sysmon_export.evtx to run this test; without it the test is skipped.
Everything is written to a temporary directory, never to the real data folder.
"""

from pathlib import Path

import pytest

from raven.collectors.evtx_loader import load_evtx
from raven.database.ingest import ingest_events
from raven.database.models import Event
from raven.database.session import open_workspace_database
from raven.database.validate import validate_database
from raven.parsers.deduplicate import count_duplicate_fingerprints, deduplicate
from raven.parsers.normalized_jsonl import read_normalized_jsonl
from raven.parsers.normalizer import normalize_all

pytestmark = pytest.mark.slow

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sysmon_export.evtx"
REFERENCE_SIZE = 3_215_360


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory):
    if not FIXTURE.is_file():
        pytest.skip(f"reference file not present: {FIXTURE}")
    if FIXTURE.stat().st_size != REFERENCE_SIZE:
        pytest.skip(f"{FIXTURE.name} is not the {REFERENCE_SIZE}-byte reference file")
    directory = tmp_path_factory.mktemp("reference_s4")
    raw = directory / "raw.jsonl"
    normalized = directory / "normalized.jsonl"
    deduplicated = directory / "deduplicated.jsonl"
    duplicates = directory / "duplicates.jsonl"
    load_evtx(FIXTURE, raw)
    normalize_all(raw, normalized, 1)
    result = deduplicate(normalized, deduplicated, duplicates)
    factory = open_workspace_database(directory / "workspace" / "raven.db")
    first = ingest_events(deduplicated, directory / "first_summary.json", factory)
    second = ingest_events(deduplicated, directory / "second_summary.json", factory)
    with factory() as session:
        stored = session.query(Event).count()
    factory.kw["bind"].dispose()
    yield {
        "directory": directory,
        "normalized": normalized,
        "deduplicated": deduplicated,
        "duplicates": duplicates,
        "result": result,
        "first": first,
        "second": second,
        "stored": stored,
    }


def test_reference_deduplication_counts(pipeline):
    assert tuple(pipeline["result"]) == (2816, 2719, 97)
    assert count_duplicate_fingerprints(pipeline["deduplicated"]) == 0


def test_reference_status_split_after_deduplication(pipeline):
    statuses = {}
    for event in read_normalized_jsonl(pipeline["deduplicated"]):
        statuses[event["normalization_status"]] = statuses.get(event["normalization_status"], 0) + 1
    assert statuses == {"OK": 1962, "UNSUPPORTED_EVENT_ID": 757}


def test_every_removed_event_is_recorded(pipeline):
    lines = pipeline["duplicates"].read_text(encoding="utf-8").splitlines()
    assert len(lines) == 97


def test_reference_ingest_and_re_ingest(pipeline):
    assert pipeline["first"] == {"read": 2719, "inserted": 2719, "skipped_existing": 0}
    assert pipeline["second"] == {"read": 2719, "inserted": 0, "skipped_existing": 2719}
    assert pipeline["stored"] == 2719


def test_reference_database_validates(pipeline):
    result = validate_database(str(pipeline["directory"] / "workspace" / "raven.db"))
    assert result["problems"] == []
    assert result["row_counts"]["events"] == 2719
    assert result["events_by_status"] == {"OK": 1962, "UNSUPPORTED_EVENT_ID": 757}
