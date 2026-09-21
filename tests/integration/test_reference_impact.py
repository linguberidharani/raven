"""S8 acceptance on the reference EVTX (spec sections 6.5b, 6.9 and 12): four impact categories with the
scores (distinct assets) 475, 12, 14 and 0, over 558, 14, 25 and 0 events.

The database with the correlation groups comes from the shared fixture in conftest.py (reference file
needed, otherwise these tests are skipped). Everything is written to temporary directories.
"""

import json

import pytest
from sqlalchemy import select, text

from raven.database.models import ImpactAnalysis
from raven.database.session import open_workspace_database
from raven.impact.persist import run_impact
from raven.reconstruction.persist import run_reconstruction
from raven.timeline.persist import run_timeline

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def analyzed(reference_db, tmp_path_factory):
    directory = tmp_path_factory.mktemp("reference_s8")
    factory = open_workspace_database(reference_db)
    try:
        run_reconstruction(factory, None)
        run_timeline(factory)
        first = run_impact(factory, directory / "first.json")
        with factory() as session:
            first_rows = session.execute(select(ImpactAnalysis).order_by(ImpactAnalysis.id)).scalars().all()
            first_dump = [(r.id, r.attack_session_id, r.impact_category, r.impact_score, r.affected_assets, r.analysis) for r in first_rows]
        second = run_impact(factory, directory / "second.json")
        with factory() as session:
            second_dump = [
                (r.id, r.attack_session_id, r.impact_category, r.impact_score, r.affected_assets, r.analysis)
                for r in session.execute(select(ImpactAnalysis).order_by(ImpactAnalysis.id)).scalars()
            ]
            foreign_key_problems = session.execute(text("PRAGMA foreign_key_check")).fetchall()
    finally:
        factory.kw["bind"].dispose()
    return {
        "first": first,
        "second": second,
        "rows": first_rows,
        "first_dump": first_dump,
        "second_dump": second_dump,
        "first_path": directory / "first.json",
        "second_path": directory / "second.json",
        "foreign_key_problems": foreign_key_problems,
    }


def test_the_four_categories_and_their_scores(analyzed):
    scores = {row.impact_category: row.impact_score for row in analyzed["rows"]}
    assert [row.impact_category for row in analyzed["rows"]] == ["files_affected", "network_activity", "process_activity", "unsupported_events"]
    assert scores == {"files_affected": 475, "network_activity": 12, "process_activity": 14, "unsupported_events": 0}


def test_the_event_counts(analyzed):
    counts = {row.impact_category: json.loads(row.analysis)["event_count"] for row in analyzed["rows"]}
    assert counts == {"files_affected": 558, "network_activity": 14, "process_activity": 25, "unsupported_events": 0}


def test_assets_are_distinct_sorted_and_match_the_scores(analyzed):
    for row in analyzed["rows"]:
        assets = json.loads(row.affected_assets)
        assert assets == sorted(set(assets))
        assert len(assets) == row.impact_score


def test_details(analyzed):
    by_category = {row.impact_category: json.loads(row.analysis) for row in analyzed["rows"]}
    assert all(item["details"]["distinct_computers"] == 1 for item in by_category.values() if item["event_count"])
    protocols = by_category["network_activity"]["details"]["protocols_seen"]
    assert protocols and set(protocols) <= {"tcp", "udp"}


def test_rebuilding_gives_identical_rows_and_summary(analyzed):
    assert analyzed["first_dump"] == analyzed["second_dump"] and len(analyzed["first_dump"]) == 4
    assert analyzed["first"] == analyzed["second"]
    assert analyzed["first_path"].read_bytes() == analyzed["second_path"].read_bytes()
    assert analyzed["foreign_key_problems"] == []
