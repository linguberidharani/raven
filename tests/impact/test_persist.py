"""Unit tests for storing impact analysis. Synthetic events, temporary directories only."""

import json

import pytest
from sqlalchemy import func, insert, select, text

from raven.correlation.runner import run_correlation
from raven.database.models import AttackSession, Event, ImpactAnalysis
from raven.database.session import open_workspace_database
from raven.impact.persist import main, run_impact
from raven.parsers.schema import NORMALIZED_FIELDS
from raven.reconstruction.persist import run_reconstruction
from raven.timeline.persist import run_timeline


def stamp(seconds):
    minutes, sec = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"2026-09-13T{8 + hours:02d}:{minutes:02d}:{sec:02d}.000Z"


def event_row(number, event_type, seconds, pid, computer="Dharani"):
    row = {name: None for name in NORMALIZED_FIELDS}
    row.update(
        raw_event_ref=f"1:{number}",
        event_id={"process_creation": 1, "network_connection": 3, "file_create": 11}[event_type],
        event_type=event_type,
        timestamp=stamp(seconds),
        computer=computer,
        process_id=pid,
        process_name=f"C:\\Test\\p{pid}.exe",
        file_path=f"C:\\Test\\{pid}_{number % 3}.txt" if event_type == "file_create" else None,
        user="SYNTHETIC\\tester",
        normalization_status="OK",
    )
    return row


def rows_for(pid, start, first_number=1):
    """A process creation and 12 file creations (file paths repeat: 3 distinct per process)."""
    rows = [event_row(first_number, "process_creation", start, pid)]
    for i in range(12):
        rows.append(event_row(first_number + 1 + i, "file_create", start + 1 + i, pid))
    return rows


@pytest.fixture
def factory(tmp_path):
    factory = open_workspace_database(tmp_path / "workspace" / "raven.db")
    yield factory
    factory.kw["bind"].dispose()


def prepare(factory, rows):
    with factory.kw["bind"].begin() as connection:
        connection.execute(insert(Event), rows)
    run_correlation(factory, None)
    run_reconstruction(factory, None)
    run_timeline(factory)


def impact(factory):
    with factory() as session:
        return session.execute(select(ImpactAnalysis).order_by(ImpactAnalysis.id)).scalars().all()


def test_four_rows_per_session_in_category_order(factory):
    prepare(factory, rows_for(10, 0))
    summary = run_impact(factory)
    rows = impact(factory)
    assert [r.impact_category for r in rows] == ["files_affected", "network_activity", "process_activity", "unsupported_events"]
    assert summary["totals"] == {"sessions": 1, "impact_rows": 4}
    assert {r.attack_session_id for r in rows} == {1}


def test_scores_are_the_numbers_of_distinct_assets(factory):
    prepare(factory, rows_for(10, 0))
    run_impact(factory)
    scores = {r.impact_category: r.impact_score for r in impact(factory)}
    # the timeline holds the process creation and file creations 1 to 10 of the burst; file paths repeat in 3 variants
    assert scores == {"files_affected": 3, "network_activity": 0, "process_activity": 1, "unsupported_events": 0}


def test_assets_and_analysis_are_stored_as_json(factory):
    prepare(factory, rows_for(10, 0))
    run_impact(factory)
    files = impact(factory)[0]
    assets = json.loads(files.affected_assets)
    assert assets == sorted(assets) and len(assets) == files.impact_score == 3
    analysis = json.loads(files.analysis)
    assert analysis["event_count"] == 10 == len(analysis["event_ids"]) == len(analysis["raw_event_refs"])
    assert analysis["details"]["distinct_computers"] == 1
    assert json.loads(impact(factory)[3].affected_assets) == []


def test_running_twice_gives_identical_rows_and_summary_file(factory, tmp_path):
    prepare(factory, rows_for(10, 0))
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    run_impact(factory, first)
    before = [(r.id, r.attack_session_id, r.impact_category, r.impact_score, r.affected_assets, r.analysis) for r in impact(factory)]
    run_impact(factory, second)
    after = [(r.id, r.attack_session_id, r.impact_category, r.impact_score, r.affected_assets, r.analysis) for r in impact(factory)]
    assert before == after and len(after) == 4
    assert first.read_bytes() == second.read_bytes()


def test_old_rows_are_replaced(factory):
    prepare(factory, rows_for(10, 0))
    run_impact(factory)
    with factory.kw["bind"].begin() as connection:
        connection.execute(text("UPDATE impact_analysis SET impact_score = 999"))
    run_impact(factory)
    assert all(r.impact_score != 999 for r in impact(factory))
    assert len(impact(factory)) == 4


def test_every_session_gets_its_own_four_rows(factory):
    prepare(factory, rows_for(10, 0) + rows_for(20, 5000, first_number=100))
    summary = run_impact(factory)
    assert summary["totals"] == {"sessions": 2, "impact_rows": 8}
    with factory() as session:
        counts = dict(session.execute(select(ImpactAnalysis.attack_session_id, func.count()).group_by(ImpactAnalysis.attack_session_id)).all())
    assert counts == {1: 4, 2: 4}


def test_no_sessions_gives_no_rows(factory):
    summary = run_impact(factory)
    assert summary["totals"] == {"sessions": 0, "impact_rows": 0}
    assert impact(factory) == []


def test_foreign_keys_hold_after_a_run(factory):
    prepare(factory, rows_for(10, 0))
    run_impact(factory)
    with factory() as session:
        assert session.execute(text("PRAGMA foreign_key_check")).fetchall() == []
        assert session.scalar(select(func.count()).select_from(AttackSession)) == 1


def test_main_prints_the_categories(factory, tmp_path, capsys):
    prepare(factory, rows_for(10, 0))
    assert main([str(tmp_path / "workspace" / "raven.db"), "--summary", str(tmp_path / "s.json")]) == 0
    printed = capsys.readouterr().out
    assert "impact rows: 4" in printed
    assert "  files_affected: score 3 distinct assets, 10 events" in printed
    assert "  unsupported_events: score 0 distinct assets, 0 events" in printed
    assert "summary sha256:" in printed


def test_main_reports_errors(tmp_path, capsys):
    assert main([str(tmp_path / "missing.db")]) == 1
    assert "ERROR" in capsys.readouterr().err
