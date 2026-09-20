"""Unit tests for the database validation script. Synthetic events, temporary directories only."""

import sqlite3

import pytest

from raven.database.ingest import ingest_events
from raven.database.session import open_workspace_database
from raven.database.validate import main, validate_database
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
    )
    event.update(changes)
    return event


@pytest.fixture
def database(tmp_path):
    factory = open_workspace_database(tmp_path / "raven.db")
    source = tmp_path / "in.jsonl"
    write_normalized_jsonl(
        [
            make_event(1),
            make_event(2),
            make_event(3, event_id=5, event_type="unsupported", normalization_status="UNSUPPORTED_EVENT_ID"),
        ],
        source,
    )
    ingest_events(source, None, factory)
    factory.kw["bind"].dispose()
    return tmp_path / "raven.db"


def test_a_good_database_is_valid(database):
    result = validate_database(str(database))
    assert result["problems"] == []
    assert result["tables_missing"] == []
    assert result["row_counts"]["events"] == 3
    assert result["row_counts"]["reports"] == 0
    assert result["events_by_status"] == {"OK": 2, "UNSUPPORTED_EVENT_ID": 1}
    assert result["events_by_type"] == {"file_create": 2, "unsupported": 1}
    assert result["repeated_raw_event_refs"] == 0
    assert result["integrity_check"] == ["ok"]


def test_validation_does_not_change_the_database(database):
    before = database.read_bytes()
    validate_database(str(database))
    assert database.read_bytes() == before


def test_a_missing_table_is_reported(database):
    connection = sqlite3.connect(database)
    connection.execute("DROP TABLE reports")
    connection.commit()
    connection.close()
    result = validate_database(str(database))
    assert result["tables_missing"] == ["reports"]
    assert any("missing tables" in problem for problem in result["problems"])


def test_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        validate_database(str(tmp_path / "missing.db"))


def test_main_prints_the_findings_and_returns_zero(database, capsys):
    assert main([str(database)]) == 0
    printed = capsys.readouterr().out
    assert "rows in events: 3" in printed
    assert "events with status OK: 2" in printed
    assert "repeated raw_event_ref values: 0" in printed
    assert "integrity_check: ok" in printed
    assert "database is valid" in printed


def test_main_returns_one_for_a_bad_database(database, capsys):
    connection = sqlite3.connect(database)
    connection.execute("DROP TABLE timeline_events")
    connection.commit()
    connection.close()
    assert main([str(database)]) == 1
    assert "PROBLEM: missing tables: timeline_events" in capsys.readouterr().out


def test_main_reports_a_missing_file(tmp_path, capsys):
    assert main([str(tmp_path / "missing.db")]) == 1
    assert "ERROR" in capsys.readouterr().err
