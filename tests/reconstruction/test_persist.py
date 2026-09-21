"""Unit tests for storing attack sessions. Synthetic events, temporary directories only."""

import json

import pytest
from sqlalchemy import func, insert, select, text

from raven.correlation.runner import run_correlation
from raven.database.models import AttackSession, ImpactAnalysis, Report, TimelineEvent
from raven.database.models import Event
from raven.database.session import open_workspace_database
from raven.parsers.schema import NORMALIZED_FIELDS
from raven.reconstruction.persist import load_groups, main, run_reconstruction
from raven.reconstruction.sequencer import ReconstructionError


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
        normalization_status="OK",
    )
    return row


def rows_for(pid, start, computer="Dharani", first_number=1):
    """A process creation and 12 file creations: one R001 group and one R003 group."""
    rows = [event_row(first_number, "process_creation", start, pid, computer)]
    for i in range(12):
        rows.append(event_row(first_number + 1 + i, "file_create", start + 1 + i, pid, computer))
    return rows


@pytest.fixture
def factory(tmp_path):
    factory = open_workspace_database(tmp_path / "workspace" / "raven.db")
    yield factory
    factory.kw["bind"].dispose()


def load(factory, rows):
    with factory.kw["bind"].begin() as connection:
        connection.execute(insert(Event), rows)
    run_correlation(factory, None)


def session_rows(factory):
    with factory() as session:
        return session.execute(select(AttackSession).order_by(AttackSession.id)).scalars().all()


def test_groups_are_read_from_the_database(factory):
    load(factory, rows_for(10, 0))
    with factory() as session:
        groups = load_groups(session)
    assert [g.group_id for g in groups] == ["RAVEN-R001:10:" + stamp(0), "RAVEN-R003:10:" + stamp(1)]
    first, second = groups
    assert first.rule_id == "RAVEN-R001" and first.severity == "HIGH" and first.computer == "Dharani"
    assert first.start_time == stamp(0) and first.end_time == stamp(5) and first.event_count == 6
    assert second.start_time == stamp(1) and second.end_time == stamp(10) and second.event_count == 10


def test_one_session_is_stored(factory, tmp_path):
    load(factory, rows_for(10, 0))
    summary = run_reconstruction(factory, tmp_path / "mapping.json")
    (row,) = session_rows(factory)
    assert row.session_id == "RAVEN-SESSION-Dharani-RAVEN-R001-10-" + stamp(0).replace(":", "-").replace(".", "-")
    assert row.start_time == stamp(0) and row.end_time == stamp(10)
    assert row.severity == "HIGH" and row.confidence is None
    assert row.description == "Reconstructed attack session containing 2 correlation group(s) from rule(s): RAVEN-R001, RAVEN-R003."
    assert summary["totals"] == {"groups": 2, "sessions": 1}


def test_the_mapping_file_lists_the_groups_of_each_session(factory, tmp_path):
    load(factory, rows_for(10, 0))
    path = tmp_path / "out" / "mapping.json"
    run_reconstruction(factory, path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["merge_gap_seconds"] == 300
    (item,) = data["sessions"]
    assert item["computer"] == "Dharani" and item["confidence"] is None and item["group_count"] == 2
    assert item["rule_ids"] == ["RAVEN-R001", "RAVEN-R003"]
    assert [g["group_id"] for g in item["groups"]] == ["RAVEN-R001:10:" + stamp(0), "RAVEN-R003:10:" + stamp(1)]
    assert item["groups"][0]["event_count"] == 6 and item["groups"][1]["event_count"] == 10


def test_groups_far_apart_make_several_sessions(factory):
    load(factory, rows_for(10, 0) + rows_for(20, 2000, first_number=100))
    run_reconstruction(factory, None)
    rows = session_rows(factory)
    assert len(rows) == 2
    assert [r.start_time for r in rows] == [stamp(0), stamp(2000)]


def test_the_merge_gap_is_a_parameter(factory):
    load(factory, rows_for(10, 0) + rows_for(20, 100, first_number=100))
    assert run_reconstruction(factory, None, merge_gap_seconds=300)["totals"]["sessions"] == 1
    assert run_reconstruction(factory, None, merge_gap_seconds=30)["totals"]["sessions"] == 2
    assert len(session_rows(factory)) == 2


def test_running_twice_gives_the_same_rows_ids_and_mapping_file(factory, tmp_path):
    load(factory, rows_for(10, 0))
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    run_reconstruction(factory, first)
    before = [(r.id, r.session_id, r.start_time, r.end_time, r.severity, r.confidence, r.description) for r in session_rows(factory)]
    run_reconstruction(factory, second)
    after = [(r.id, r.session_id, r.start_time, r.end_time, r.severity, r.confidence, r.description) for r in session_rows(factory)]
    assert before == after and len(after) == 1
    assert first.read_bytes() == second.read_bytes()


def test_a_session_that_is_still_produced_keeps_its_row_and_its_dependents(factory):
    load(factory, rows_for(10, 0))
    run_reconstruction(factory, None)
    (row,) = session_rows(factory)
    with factory.kw["bind"].begin() as connection:
        first_event = connection.execute(select(Event.id).limit(1)).scalar()
        connection.execute(insert(TimelineEvent), [{"attack_session_id": row.id, "event_id": first_event, "sequence_number": 1, "timeline_timestamp": stamp(0), "description": "d"}])
    run_reconstruction(factory, None)
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(TimelineEvent)) == 1
        assert session.scalar(select(AttackSession.id)) == row.id


def test_a_stale_session_is_removed_with_its_dependents(factory):
    load(factory, rows_for(10, 0))
    run_reconstruction(factory, None)
    (row,) = session_rows(factory)
    with factory.kw["bind"].begin() as connection:
        first_event = connection.execute(select(Event.id).limit(1)).scalar()
        connection.execute(insert(TimelineEvent), [{"attack_session_id": row.id, "event_id": first_event, "sequence_number": 1, "timeline_timestamp": stamp(0), "description": "d"}])
        connection.execute(insert(ImpactAnalysis), [{"attack_session_id": row.id, "impact_category": "files_affected", "impact_score": 1, "affected_assets": "[]", "analysis": "{}"}])
        connection.execute(insert(Report), [{"attack_session_id": row.id, "report_title": "t", "report_text": "x"}])
        connection.execute(text("DELETE FROM correlated_events"))
    summary = run_reconstruction(factory, None)
    assert summary["totals"] == {"groups": 0, "sessions": 0}
    with factory() as session:
        for table in (AttackSession, TimelineEvent, ImpactAnalysis, Report):
            assert session.scalar(select(func.count()).select_from(table)) == 0
        assert session.execute(text("PRAGMA foreign_key_check")).fetchall() == []


def test_a_group_with_events_of_two_computers_is_an_error(factory):
    rows = rows_for(10, 0)
    rows[3]["computer"] = "OTHER-HOST"
    load(factory, rows)
    with pytest.raises(ReconstructionError, match="several computers"):
        run_reconstruction(factory, None)
    assert session_rows(factory) == []


def test_no_groups_gives_no_sessions_and_still_a_mapping_file(factory, tmp_path):
    summary = run_reconstruction(factory, tmp_path / "m.json")
    assert summary["totals"] == {"groups": 0, "sessions": 0}
    assert json.loads((tmp_path / "m.json").read_text(encoding="utf-8"))["sessions"] == []


def test_main_prints_the_session(factory, tmp_path, capsys):
    load(factory, rows_for(10, 0))
    database = tmp_path / "workspace" / "raven.db"
    assert main([str(database), "--mapping", str(tmp_path / "m.json")]) == 0
    printed = capsys.readouterr().out
    assert "attack sessions: 1" in printed
    assert "correlation groups read: 2" in printed
    assert "  computer:   Dharani" in printed
    assert "  severity:   HIGH" in printed
    assert "  confidence: None" in printed
    assert "mapping sha256:" in printed


def test_main_reports_errors(tmp_path, capsys):
    assert main([str(tmp_path / "missing.db")]) == 1
    assert "ERROR" in capsys.readouterr().err
