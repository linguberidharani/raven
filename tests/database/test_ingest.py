"""Unit tests for ingesting events into the database. Synthetic events, temporary directories only."""

import json

import pytest

from raven.database.ingest import ingest_events, main
from raven.database.models import Event
from raven.database.session import open_workspace_database
from raven.parsers.normalized_jsonl import write_normalized_jsonl
from raven.parsers.schema import NORMALIZED_FIELDS


def make_event(record_id, **changes):
    event = {name: None for name in NORMALIZED_FIELDS}
    event.update(
        raw_event_ref=f"1:{record_id}",
        event_id=11,
        event_type="file_create",
        timestamp="2026-09-13T08:39:49.545Z",
        computer="SYNTHETIC-LAB-HOST",
        normalization_status="OK",
        process_id=record_id,
        file_path=f"C:\\Test\\{record_id}.txt",
    )
    event.update(changes)
    return event


@pytest.fixture
def factory(tmp_path):
    factory = open_workspace_database(tmp_path / "workspace" / "raven.db")
    yield factory
    factory.kw["bind"].dispose()


def write(tmp_path, events, name="dedup.jsonl"):
    path = tmp_path / name
    write_normalized_jsonl(events, path)
    return path


def count(factory):
    with factory() as session:
        return session.query(Event).count()


def test_events_are_inserted_with_all_fields(tmp_path, factory):
    events = [make_event(1, initiated=True, port=443), make_event(2, user="SYNTHETIC\\tester")]
    summary = ingest_events(write(tmp_path, events), None, factory)
    assert summary == {"read": 2, "inserted": 2, "skipped_existing": 0}
    with factory() as session:
        rows = session.query(Event).order_by(Event.id).all()
    assert [row.raw_event_ref for row in rows] == ["1:1", "1:2"]
    for row, event in zip(rows, events):
        for name in NORMALIZED_FIELDS:
            assert getattr(row, name) == event[name]


def test_ingesting_the_same_file_again_inserts_nothing(tmp_path, factory):
    source = write(tmp_path, [make_event(i) for i in range(1, 6)])
    assert ingest_events(source, None, factory)["inserted"] == 5
    again = ingest_events(source, None, factory)
    assert again == {"read": 5, "inserted": 0, "skipped_existing": 5}
    assert count(factory) == 5


def test_only_the_new_events_of_a_larger_file_are_inserted(tmp_path, factory):
    ingest_events(write(tmp_path, [make_event(i) for i in range(1, 4)], "a.jsonl"), None, factory)
    summary = ingest_events(write(tmp_path, [make_event(i) for i in range(1, 8)], "b.jsonl"), None, factory)
    assert summary == {"read": 7, "inserted": 4, "skipped_existing": 3}
    assert count(factory) == 7


def test_an_event_twice_in_the_input_is_inserted_once(tmp_path, factory):
    source = write(tmp_path, [make_event(1), make_event(2), make_event(1)])
    assert ingest_events(source, None, factory) == {"read": 3, "inserted": 2, "skipped_existing": 1}


def test_batches_smaller_than_the_input_work(tmp_path, factory):
    source = write(tmp_path, [make_event(i) for i in range(1, 11)])
    assert ingest_events(source, None, factory, batch_size=3)["inserted"] == 10
    assert count(factory) == 10


def test_a_bad_line_in_the_input_inserts_nothing(tmp_path, factory):
    path = tmp_path / "bad.jsonl"
    good = write(tmp_path, [make_event(1), make_event(2)], "good.jsonl").read_text(encoding="utf-8")
    path.write_text(good + "{oops}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="line 3"):
        ingest_events(path, None, factory, batch_size=1)
    assert count(factory) == 0


def test_the_summary_file_is_written(tmp_path, factory):
    summary_path = tmp_path / "out" / "summary.json"
    ingest_events(write(tmp_path, [make_event(1), make_event(2)]), summary_path, factory)
    assert json.loads(summary_path.read_text(encoding="utf-8")) == {"inserted": 2, "read": 2, "skipped_existing": 0}


def test_a_batch_size_below_one_is_rejected(tmp_path, factory):
    with pytest.raises(ValueError, match="batch_size"):
        ingest_events(write(tmp_path, [make_event(1)]), None, factory, batch_size=0)


def test_main_creates_the_database_and_is_idempotent(tmp_path, capsys):
    source = write(tmp_path, [make_event(1), make_event(2)])
    database = tmp_path / "ws" / "raven.db"
    assert main([str(source), str(database), "--summary", str(tmp_path / "s.json")]) == 0
    assert "inserted:         2" in capsys.readouterr().out
    assert main([str(source), str(database)]) == 0
    printed = capsys.readouterr().out
    assert "inserted:         0" in printed
    assert "skipped existing: 2" in printed


def test_main_reports_errors(tmp_path, capsys):
    assert main([str(tmp_path / "missing.jsonl"), str(tmp_path / "raven.db")]) == 1
    assert "ERROR" in capsys.readouterr().err
