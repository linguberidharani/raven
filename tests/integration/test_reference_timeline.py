"""S7 acceptance on the reference EVTX (spec sections 6.5b, 6.8 and 12): the timeline of the one attack
session holds 597 events (558 file creation, 14 network connection, 25 process creation), ordered by
timestamp then event ID, numbered 1 to 597, each with a meaningful generated description.

The database with the correlation groups comes from the shared fixture in conftest.py (reference file
needed, otherwise these tests are skipped). Everything is written to temporary directories.
"""

import re

import pytest
from sqlalchemy import func, select, text

from raven.database.models import Event, TimelineEvent
from raven.database.session import open_workspace_database
from raven.reconstruction.persist import run_reconstruction
from raven.timeline.persist import run_timeline

pytestmark = pytest.mark.slow

PATTERNS = {
    "process_creation": re.compile(r"^Process created: .+ \(PID \d+\)( by .+?)?(; parent .+)?$"),
    "file_create": re.compile(r"^File created: .+ by .+ \(PID \d+\)$"),
    "network_connection": re.compile(r"^Network connection( \(incoming\))?: .+ (to|on) .+/\w+"),
}


@pytest.fixture(scope="module")
def built(reference_db, tmp_path_factory):
    directory = tmp_path_factory.mktemp("reference_s7")
    factory = open_workspace_database(reference_db)
    try:
        run_reconstruction(factory, None)
        first = run_timeline(factory, directory / "first.json")
        with factory() as session:
            rows = session.execute(
                select(TimelineEvent.sequence_number, TimelineEvent.timeline_timestamp, TimelineEvent.description, TimelineEvent.event_id, Event.event_type)
                .join(Event, Event.id == TimelineEvent.event_id)
                .order_by(TimelineEvent.sequence_number)
            ).all()
            first_dump = session.execute(
                select(TimelineEvent.id, TimelineEvent.attack_session_id, TimelineEvent.event_id, TimelineEvent.sequence_number, TimelineEvent.description)
                .order_by(TimelineEvent.id)
            ).all()
        second = run_timeline(factory, directory / "second.json")
        with factory() as session:
            second_dump = session.execute(
                select(TimelineEvent.id, TimelineEvent.attack_session_id, TimelineEvent.event_id, TimelineEvent.sequence_number, TimelineEvent.description)
                .order_by(TimelineEvent.id)
            ).all()
            foreign_key_problems = session.execute(text("PRAGMA foreign_key_check")).fetchall()
            total = session.scalar(select(func.count()).select_from(TimelineEvent))
    finally:
        factory.kw["bind"].dispose()
    return {
        "first": first,
        "second": second,
        "rows": rows,
        "first_dump": first_dump,
        "second_dump": second_dump,
        "first_path": directory / "first.json",
        "second_path": directory / "second.json",
        "foreign_key_problems": foreign_key_problems,
        "total": total,
    }


def test_597_events_by_type(built):
    (item,) = built["first"]["sessions"]
    assert built["total"] == 597 == item["timeline_events"]
    assert item["groups"] == 87
    assert item["events_by_type"] == {"file_create": 558, "network_connection": 14, "process_creation": 25}


def test_sequence_and_order(built):
    rows = built["rows"]
    assert [r.sequence_number for r in rows] == list(range(1, 598))
    stamps = [r.timeline_timestamp for r in rows]
    assert stamps == sorted(stamps)
    ties = [(a, b) for a, b in zip(rows, rows[1:]) if a.timeline_timestamp == b.timeline_timestamp]
    assert all(a.event_id < b.event_id for a, b in ties)
    assert len({r.event_id for r in rows}) == 597


def test_descriptions_are_meaningful(built):
    for row in built["rows"]:
        assert PATTERNS[row.event_type].match(row.description), (row.event_type, row.description)
        assert not row.description.startswith("Event ")


def test_rebuilding_gives_identical_rows_and_summary(built):
    assert built["first_dump"] == built["second_dump"]
    assert built["first"] == built["second"]
    assert built["first_path"].read_bytes() == built["second_path"].read_bytes()
    assert built["foreign_key_problems"] == []
