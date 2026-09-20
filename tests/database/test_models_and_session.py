"""Unit tests for the analysis database schema and the session helpers. Temporary directories only."""

import sqlite3

import pytest
from sqlalchemy import insert, inspect, text
from sqlalchemy.exc import IntegrityError

from raven.database.models import (
    EXPECTED_TABLES,
    AttackSession,
    CorrelatedEvent,
    CorrelationRule,
    Event,
    ImpactAnalysis,
    Report,
    TimelineEvent,
)
from raven.database.session import create_session_factory, create_workspace_engine, initialize_database, open_workspace_database
from raven.parsers.schema import NORMALIZED_FIELDS


@pytest.fixture
def engine(tmp_path):
    engine = create_workspace_engine(tmp_path / "workspace" / "raven.db")
    initialize_database(engine)
    yield engine
    engine.dispose()


def event_row(ref="1:1", **changes):
    row = {name: None for name in NORMALIZED_FIELDS}
    row.update(
        raw_event_ref=ref,
        event_id=11,
        event_type="file_create",
        timestamp="2026-09-13T08:39:49.545Z",
        computer="SYNTHETIC-LAB-HOST",
        normalization_status="OK",
    )
    row.update(changes)
    return row


def test_the_seven_tables_of_the_spec_exist(engine):
    assert set(inspect(engine).get_table_names()) == set(EXPECTED_TABLES)
    assert len(EXPECTED_TABLES) == 7


def test_the_events_table_has_the_27_normalized_fields_and_an_id(engine):
    columns = [column["name"] for column in inspect(engine).get_columns("events")]
    assert columns[0] == "id"
    assert columns[1:] == list(NORMALIZED_FIELDS)


def test_the_other_tables_have_the_columns_of_the_spec(engine):
    expected = {
        "correlation_rules": ["id", "rule_name", "description", "rule_definition", "enabled"],
        "correlated_events": ["id", "rule_id", "event_id", "correlation_group_id", "correlation_type"],
        "attack_sessions": ["id", "session_id", "start_time", "end_time", "description", "severity", "confidence"],
        "timeline_events": ["id", "attack_session_id", "event_id", "sequence_number", "timeline_timestamp", "description"],
        "impact_analysis": ["id", "attack_session_id", "impact_category", "impact_score", "affected_assets", "analysis"],
        "reports": ["id", "attack_session_id", "report_title", "report_text", "generated_at"],
    }
    for table, names in expected.items():
        assert [c["name"] for c in inspect(engine).get_columns(table)] == names


def test_the_database_file_and_its_folder_are_created(tmp_path):
    path = tmp_path / "a" / "b" / "raven.db"
    factory = open_workspace_database(path)
    factory.kw["bind"].dispose()
    assert path.is_file()


def test_raw_event_ref_is_unique_and_indexed(engine):
    with engine.begin() as connection:
        connection.execute(insert(Event), [event_row("1:1")])
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(insert(Event), [event_row("1:1")])
    indexes = inspect(engine).get_indexes("events")
    assert any(index["column_names"] == ["raw_event_ref"] and index["unique"] for index in indexes)


@pytest.mark.parametrize("column", ["event_id", "event_type", "normalization_status", "raw_event_ref", "timestamp", "computer"])
def test_required_columns_are_not_null(engine, column):
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(insert(Event), [event_row(**{column: None})])


def test_optional_columns_accept_null_and_booleans_round_trip(engine):
    with engine.begin() as connection:
        connection.execute(insert(Event), [event_row("1:1", initiated=True, port=443), event_row("1:2", initiated=False), event_row("1:3")])
    factory = create_session_factory(engine)
    with factory() as session:
        rows = {e.raw_event_ref: e for e in session.query(Event).all()}
    assert rows["1:1"].initiated is True and rows["1:1"].port == 443
    assert rows["1:2"].initiated is False
    assert rows["1:3"].initiated is None and rows["1:3"].process_id is None


def test_foreign_keys_are_enforced(engine):
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                insert(CorrelatedEvent),
                [{"rule_id": 99, "event_id": 99, "correlation_group_id": "g", "correlation_type": "R"}],
            )
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_a_related_row_can_be_stored_when_its_parents_exist(engine):
    with engine.begin() as connection:
        connection.execute(insert(Event), [event_row("1:1")])
        connection.execute(insert(CorrelationRule), [{"rule_name": "R001", "rule_definition": "{}", "enabled": True}])
        connection.execute(insert(AttackSession), [{"session_id": "S1", "start_time": "a", "end_time": "b"}])
        connection.execute(insert(CorrelatedEvent), [{"rule_id": 1, "event_id": 1, "correlation_group_id": "g", "correlation_type": "R001"}])
        connection.execute(insert(TimelineEvent), [{"attack_session_id": 1, "event_id": 1, "sequence_number": 1, "timeline_timestamp": "t", "description": "d"}])
        connection.execute(insert(ImpactAnalysis), [{"attack_session_id": 1, "impact_category": "files_affected", "impact_score": 3, "affected_assets": "[]", "analysis": "{}"}])
        connection.execute(insert(Report), [{"attack_session_id": 1, "report_title": "t", "report_text": "x"}])
    with engine.connect() as connection:
        assert connection.execute(text("SELECT confidence FROM attack_sessions")).scalar() is None


def test_rule_names_and_session_ids_are_unique(engine):
    with engine.begin() as connection:
        connection.execute(insert(CorrelationRule), [{"rule_name": "R001", "rule_definition": "{}", "enabled": True}])
        connection.execute(insert(AttackSession), [{"session_id": "S1", "start_time": "a", "end_time": "b"}])
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(insert(CorrelationRule), [{"rule_name": "R001", "rule_definition": "{}", "enabled": True}])
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(insert(AttackSession), [{"session_id": "S1", "start_time": "a", "end_time": "b"}])


def test_creating_the_database_twice_keeps_the_data(tmp_path):
    path = tmp_path / "raven.db"
    first = open_workspace_database(path)
    with first.kw["bind"].begin() as connection:
        connection.execute(insert(Event), [event_row("1:1")])
    first.kw["bind"].dispose()
    second = open_workspace_database(path)
    with second() as session:
        assert session.query(Event).count() == 1
    second.kw["bind"].dispose()
    connection = sqlite3.connect(path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
    finally:
        connection.close()
