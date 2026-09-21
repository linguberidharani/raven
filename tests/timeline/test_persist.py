"""Unit tests for storing timelines. Synthetic events, temporary directories only."""

import json

import pytest
from sqlalchemy import func, insert, select, text

from raven.correlation.runner import run_correlation
from raven.database.models import AttackSession, Event, TimelineEvent
from raven.database.session import open_workspace_database
from raven.parsers.schema import NORMALIZED_FIELDS
from raven.reconstruction.persist import load_groups, run_reconstruction
from raven.timeline.persist import TimelineError, main, run_timeline, session_groups


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
        file_path=f"C:\\Test\\{number}.txt" if event_type == "file_create" else None,
        normalization_status="OK",
    )
    return row


def rows_for(pid, start, computer="Dharani", first_number=1):
    """A process creation and 12 file creations: one R001 group (6 events) and one R003 group (10 events)."""
    rows = [event_row(first_number, "process_creation", start, pid, computer)]
    for i in range(12):
        rows.append(event_row(first_number + 1 + i, "file_create", start + 1 + i, pid, computer))
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


def timeline(factory):
    with factory() as session:
        return session.execute(select(TimelineEvent).order_by(TimelineEvent.id)).scalars().all()


def test_the_timeline_holds_the_events_of_the_groups_once(factory):
    prepare(factory, rows_for(10, 0))
    summary = run_timeline(factory)
    rows = timeline(factory)
    # R001 uses the process creation and file creations 1 to 5 of the burst, R003 uses file creations 1 to 10: 11 distinct events
    assert len(rows) == 11
    assert summary["totals"] == {"sessions": 1, "timeline_events": 11}
    assert [r.sequence_number for r in rows] == list(range(1, 12))
    assert [r.timeline_timestamp for r in rows] == sorted(r.timeline_timestamp for r in rows)
    assert len({r.event_id for r in rows}) == 11


def test_rows_point_to_the_session_and_carry_descriptions(factory):
    prepare(factory, rows_for(10, 0))
    run_timeline(factory)
    with factory() as session:
        session_row = session.scalars(select(AttackSession)).one()
        rows = timeline(factory)
        first = session.get(Event, rows[0].event_id)
    assert {r.attack_session_id for r in rows} == {session_row.id}
    assert rows[0].description == "Process created: C:\\Test\\p10.exe (PID 10)"
    assert first.event_type == "process_creation"
    assert rows[1].description == "File created: C:\\Test\\2.txt by C:\\Test\\p10.exe (PID 10)"


def test_the_summary_counts_by_type(factory, tmp_path):
    prepare(factory, rows_for(10, 0))
    path = tmp_path / "out" / "summary.json"
    run_timeline(factory, path)
    data = json.loads(path.read_text(encoding="utf-8"))
    (item,) = data["sessions"]
    assert item["groups"] == 2 and item["timeline_events"] == 11
    assert item["events_by_type"] == {"file_create": 10, "process_creation": 1}
    assert item["first_timestamp"] == stamp(0) and item["last_timestamp"] == stamp(10)
    assert item["first_descriptions"][0].startswith("Process created:")
    assert item["last_description"].startswith("File created:")


def test_running_twice_gives_identical_rows_and_summary_file(factory, tmp_path):
    prepare(factory, rows_for(10, 0))
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    run_timeline(factory, first)
    before = [(r.id, r.attack_session_id, r.event_id, r.sequence_number, r.timeline_timestamp, r.description) for r in timeline(factory)]
    run_timeline(factory, second)
    after = [(r.id, r.attack_session_id, r.event_id, r.sequence_number, r.timeline_timestamp, r.description) for r in timeline(factory)]
    assert before == after
    assert first.read_bytes() == second.read_bytes()


def test_every_session_gets_only_its_own_events(factory):
    prepare(factory, rows_for(10, 0) + rows_for(20, 5000, first_number=100))
    summary = run_timeline(factory)
    assert summary["totals"] == {"sessions": 2, "timeline_events": 22}
    with factory() as session:
        sessions = session.scalars(select(AttackSession).order_by(AttackSession.start_time)).all()
        for row, expected_pid in zip(sessions, (10, 20)):
            descriptions = [r.description for r in timeline(factory) if r.attack_session_id == row.id]
            assert len(descriptions) == 11
            assert all(f"p{expected_pid}.exe" in d for d in descriptions)


def test_rebuilding_replaces_old_rows(factory):
    prepare(factory, rows_for(10, 0))
    run_timeline(factory)
    with factory.kw["bind"].begin() as connection:
        connection.execute(text("UPDATE timeline_events SET description = 'stale'"))
    run_timeline(factory)
    assert all(r.description != "stale" for r in timeline(factory))
    assert len(timeline(factory)) == 11


def test_no_sessions_gives_an_empty_timeline(factory):
    summary = run_timeline(factory)
    assert summary["totals"] == {"sessions": 0, "timeline_events": 0}
    assert timeline(factory) == []


def test_session_groups_finds_the_groups_by_computer_and_time(factory):
    prepare(factory, rows_for(10, 0))
    with factory() as session:
        groups = load_groups(session)
        row = session.scalars(select(AttackSession)).one()
    found = session_groups(row.session_id, row.start_time, row.end_time, groups)
    assert [g.group_id for g in found] == [g.group_id for g in groups]


def test_a_session_whose_first_group_is_missing_is_an_error(factory):
    prepare(factory, rows_for(10, 0))
    with factory() as session:
        groups = load_groups(session)
        row = session.scalars(select(AttackSession)).one()
    with pytest.raises(TimelineError, match="run the reconstruction again"):
        session_groups(row.session_id + "X", row.start_time, row.end_time, groups)


def test_foreign_keys_hold_after_a_run(factory):
    prepare(factory, rows_for(10, 0))
    run_timeline(factory)
    with factory() as session:
        assert session.execute(text("PRAGMA foreign_key_check")).fetchall() == []
        assert session.scalar(select(func.count()).select_from(TimelineEvent)) == 11


def test_main_prints_the_timeline_summary(factory, tmp_path, capsys):
    prepare(factory, rows_for(10, 0))
    assert main([str(tmp_path / "workspace" / "raven.db"), "--summary", str(tmp_path / "s.json")]) == 0
    printed = capsys.readouterr().out
    assert "attack sessions: 1" in printed
    assert "timeline events: 11" in printed
    assert "    file_create: 10" in printed
    assert "  description 1: Process created: C:\\Test\\p10.exe (PID 10)" in printed
    assert "summary sha256:" in printed


def test_main_reports_errors(tmp_path, capsys):
    assert main([str(tmp_path / "missing.db")]) == 1
    assert "ERROR" in capsys.readouterr().err
