"""S6 acceptance on the reference EVTX (spec sections 6.5b, 6.7 and 12): one attack session for the
computer Dharani with a deterministic session ID, made of the 87 correlation groups, severity HIGH,
confidence null (decision D5).

The pipeline up to correlation comes from the shared fixture in conftest.py (reference file needed,
otherwise these tests are skipped). Everything is written to temporary directories.
"""

import json

import pytest
from sqlalchemy import func, select, text

from raven.database.models import AttackSession
from raven.database.session import open_workspace_database
from raven.reconstruction.persist import run_reconstruction
from raven.reconstruction.sequencer import sanitize_id_part

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def reconstructed(reference_db, tmp_path_factory):
    directory = tmp_path_factory.mktemp("reference_s6")
    factory = open_workspace_database(reference_db)
    try:
        first = run_reconstruction(factory, directory / "first.json")
        second = run_reconstruction(factory, directory / "second.json")
        with factory() as session:
            rows = session.execute(select(AttackSession)).scalars().all()
            foreign_key_problems = session.execute(text("PRAGMA foreign_key_check")).fetchall()
            count = session.scalar(select(func.count()).select_from(AttackSession))
    finally:
        factory.kw["bind"].dispose()
    return {
        "first": first,
        "second": second,
        "rows": rows,
        "count": count,
        "foreign_key_problems": foreign_key_problems,
        "first_path": directory / "first.json",
        "second_path": directory / "second.json",
    }


def test_one_session_from_87_groups(reconstructed):
    assert reconstructed["first"]["totals"] == {"groups": 87, "sessions": 1}
    assert reconstructed["count"] == 1


def test_the_session_fields(reconstructed):
    (row,) = reconstructed["rows"]
    (item,) = reconstructed["first"]["sessions"]
    assert item["computer"] == "Dharani"
    assert row.severity == "HIGH"
    assert row.confidence is None
    assert row.description == (
        "Reconstructed attack session containing 87 correlation group(s) from rule(s): RAVEN-R001, RAVEN-R002, RAVEN-R003."
    )
    assert item["group_count"] == 87
    assert item["rule_ids"] == ["RAVEN-R001", "RAVEN-R002", "RAVEN-R003"]


def test_the_session_id_and_times_follow_the_first_group(reconstructed):
    (row,) = reconstructed["rows"]
    (item,) = reconstructed["first"]["sessions"]
    first_group = item["groups"][0]
    assert row.session_id == "RAVEN-SESSION-Dharani-" + sanitize_id_part(first_group["group_id"])
    assert row.start_time == first_group["start_time"] == min(g["start_time"] for g in item["groups"])
    assert row.end_time == max(g["end_time"] for g in item["groups"])
    assert row.start_time < row.end_time


def test_running_again_gives_the_same_session_and_the_same_mapping_file(reconstructed):
    assert reconstructed["first"] == reconstructed["second"]
    assert reconstructed["first_path"].read_bytes() == reconstructed["second_path"].read_bytes()
    assert json.loads(reconstructed["first_path"].read_text(encoding="utf-8"))["totals"]["sessions"] == 1
    assert reconstructed["foreign_key_problems"] == []
