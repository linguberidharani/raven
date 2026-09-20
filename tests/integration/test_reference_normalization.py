"""S3 acceptance on the reference EVTX (spec sections 6.3 and 12): 2816 normalized events,
1984 with status OK, the unsupported ones retained.

The reference file is real telemetry and is never committed (*.evtx is ignored). Put it at
tests/fixtures/sysmon_export.evtx to run this test; without it the test is skipped.
Everything is written to a temporary directory, never to the real data folder.

The timestamp comes from the record time (TimeCreated), not from the Sysmon UtcTime: on this data
132 events have a UtcTime about 3.5 hours after their record time. The spec's time range (6.5b) and
its example correlation group ID (6.6, RAVEN-R001:1224:2026-09-13T08:39:49.695Z) follow the record time.
"""

from pathlib import Path

import pytest

from raven.collectors.evtx_loader import load_evtx
from raven.collectors.raw_jsonl import sha256_file
from raven.parsers.normalized_jsonl import read_normalized_jsonl
from raven.parsers.normalizer import normalize_all

pytestmark = pytest.mark.slow

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sysmon_export.evtx"
REFERENCE_SIZE = 3_215_360


@pytest.fixture(scope="module")
def normalized(tmp_path_factory):
    if not FIXTURE.is_file():
        pytest.skip(f"reference file not present: {FIXTURE}")
    if FIXTURE.stat().st_size != REFERENCE_SIZE:
        pytest.skip(f"{FIXTURE.name} is not the {REFERENCE_SIZE}-byte reference file")
    directory = tmp_path_factory.mktemp("reference_s3")
    raw = directory / "raw.jsonl"
    load_evtx(FIXTURE, raw)
    first, second = directory / "first.jsonl", directory / "second.jsonl"
    summary_first = normalize_all(raw, first, 1)
    summary_second = normalize_all(raw, second, 1)
    return first, second, summary_first, summary_second


def test_reference_counts(normalized):
    _, _, summary, _ = normalized
    assert summary["total"] == 2816
    assert summary["status_counts"] == {"OK": 1984, "UNSUPPORTED_EVENT_ID": 832}
    assert summary["event_type_counts"] == {
        "file_create": 842,
        "network_connection": 212,
        "process_creation": 930,
        "unsupported": 832,
    }
    assert summary["invalid_examples"] == []


def test_every_event_is_valid_and_references_are_unique(normalized):
    first, _, summary, _ = normalized
    events = list(read_normalized_jsonl(first))
    assert len(events) == summary["total"]
    assert len({event["raw_event_ref"] for event in events}) == summary["total"]
    assert all(event["raw_event_ref"].startswith("1:") for event in events)


def test_normalizing_twice_gives_identical_output(normalized):
    first, second, summary_first, summary_second = normalized
    assert summary_first == summary_second
    assert sha256_file(first) == sha256_file(second)


def test_time_range_and_example_timestamp_follow_the_spec(normalized):
    first, _, _, _ = normalized
    events = list(read_normalized_jsonl(first))
    stamps = [event["timestamp"] for event in events]
    assert min(stamps).startswith("2026-09-12T18:04:54.")
    assert max(stamps).startswith("2026-09-13T08:43:27.")
    by_reference = {event["raw_event_ref"]: event for event in events}
    assert by_reference["1:1542"]["event_id"] == 1
    assert by_reference["1:1542"]["timestamp"] == "2026-09-13T08:39:49.695Z"
