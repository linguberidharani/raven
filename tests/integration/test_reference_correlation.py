"""S5 acceptance on the reference EVTX (spec sections 6.5b, 6.6 and 12): 87 correlation groups,
R001 19, R002 14 and R003 54, together holding 597 distinct events (558 file creation, 14 network
connection and 25 process creation), and the spec example group RAVEN-R001:1224:2026-09-13T08:39:49.695Z.

The reference file is real telemetry and is never committed (*.evtx is ignored). Put it at
tests/fixtures/sysmon_export.evtx to run this test; without it the test is skipped.
Everything is written to a temporary directory, never to the real data folder.
"""

import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from raven.collectors.evtx_loader import load_evtx
from raven.correlation.runner import run_correlation
from raven.database.ingest import ingest_events
from raven.database.models import CorrelatedEvent, CorrelationRule
from raven.database.session import open_workspace_database
from raven.parsers.deduplicate import deduplicate
from raven.parsers.normalizer import normalize_all

pytestmark = pytest.mark.slow

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sysmon_export.evtx"
REFERENCE_SIZE = 3_215_360
EXAMPLE_GROUP_ID = "RAVEN-R001:1224:2026-09-13T08:39:49.695Z"


@pytest.fixture(scope="module")
def correlated(tmp_path_factory):
    if not FIXTURE.is_file():
        pytest.skip(f"reference file not present: {FIXTURE}")
    if FIXTURE.stat().st_size != REFERENCE_SIZE:
        pytest.skip(f"{FIXTURE.name} is not the {REFERENCE_SIZE}-byte reference file")
    directory = tmp_path_factory.mktemp("reference_s5")
    load_evtx(FIXTURE, directory / "raw.jsonl")
    normalize_all(directory / "raw.jsonl", directory / "normalized.jsonl", 1)
    deduplicate(directory / "normalized.jsonl", directory / "deduplicated.jsonl")
    factory = open_workspace_database(directory / "workspace" / "raven.db")
    ingest_events(directory / "deduplicated.jsonl", None, factory)
    first_path, second_path = directory / "first_summary.json", directory / "second_summary.json"
    first = run_correlation(factory, first_path)
    with factory() as session:
        rows_first = session.scalar(select(func.count()).select_from(CorrelatedEvent))
    second = run_correlation(factory, second_path)
    with factory() as session:
        rows_second = session.scalar(select(func.count()).select_from(CorrelatedEvent))
        rules_stored = session.scalar(select(func.count()).select_from(CorrelationRule))
    factory.kw["bind"].dispose()
    yield {
        "first": first,
        "second": second,
        "first_path": first_path,
        "second_path": second_path,
        "rows_first": rows_first,
        "rows_second": rows_second,
        "rules_stored": rules_stored,
    }


def test_reference_group_counts(correlated):
    summary = correlated["first"]
    by_rule = {rule["rule_id"]: rule["groups"] for rule in summary["rules"]}
    assert by_rule == {"RAVEN-R001": 19, "RAVEN-R002": 14, "RAVEN-R003": 54}
    assert summary["totals"]["groups"] == 87
    assert correlated["rules_stored"] == 3


def test_reference_events_in_groups(correlated):
    totals = correlated["first"]["totals"]
    assert totals["distinct_events"] == 597
    assert totals["distinct_events_by_type"] == {"file_create": 558, "network_connection": 14, "process_creation": 25}
    # every group holds exactly the events its steps need: 19 x 6 + 14 x 3 + 54 x 10
    assert totals["correlated_event_rows"] == 19 * 6 + 14 * 3 + 54 * 10 == correlated["rows_first"]


def test_the_spec_example_group_and_why_it_matched(correlated):
    groups = {group["group_id"]: group for group in correlated["first"]["groups"]}
    example = groups[EXAMPLE_GROUP_ID]
    assert example["rule_name"] == "Mass File Modification Burst"
    assert example["match_value"] == "1224"
    assert example["steps"] == [
        {"event_type": "process_creation", "required": 1, "found": 1},
        {"event_type": "file_create", "required": 5, "found": 5},
    ]
    assert example["event_count"] == 6
    assert example["event_refs"][0] == "1:1543"


def test_every_group_is_explained_and_ids_are_unique(correlated):
    groups = correlated["first"]["groups"]
    assert len({group["group_id"] for group in groups}) == 87
    for group in groups:
        assert group["event_count"] == len(group["event_refs"]) == sum(step["found"] for step in group["steps"])
        assert all(step["found"] >= step["required"] for step in group["steps"])


def test_running_again_gives_identical_results(correlated):
    assert correlated["first"] == correlated["second"]
    assert correlated["rows_first"] == correlated["rows_second"]
    assert correlated["first_path"].read_bytes() == correlated["second_path"].read_bytes()
    json.loads(correlated["first_path"].read_text(encoding="utf-8"))
