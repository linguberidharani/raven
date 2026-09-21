"""Unit tests for running correlation on a database. Synthetic events, temporary directories only."""

import json

import pytest
from sqlalchemy import func, insert, select, text

from raven.correlation.engine import EngineOptions
from raven.correlation.rule_schema import Rule, Step, load_rules
from raven.correlation.runner import main, run_correlation
from raven.database.models import CorrelatedEvent, CorrelationRule, Event
from raven.database.session import open_workspace_database
from raven.parsers.schema import NORMALIZED_FIELDS


def ts(seconds, millis=0):
    minutes, sec = divmod(int(seconds), 60)
    return f"2026-09-13T08:{39 + minutes:02d}:{sec:02d}.{millis:03d}Z"


def event_row(number, event_type, seconds, pid, event_id=None, status="OK"):
    row = {name: None for name in NORMALIZED_FIELDS}
    row.update(
        raw_event_ref=f"1:{number}",
        event_id=event_id or {"process_creation": 1, "network_connection": 3, "file_create": 11, "unsupported": 5}[event_type],
        event_type=event_type,
        timestamp=ts(seconds),
        computer="SYNTHETIC-LAB-HOST",
        process_id=pid,
        normalization_status="UNSUPPORTED_EVENT_ID" if event_type == "unsupported" else status,
    )
    return row


def sample_rows():
    rows, n = [], 0

    def add(kind, seconds, pid):
        nonlocal n
        n += 1
        rows.append(event_row(n, kind, seconds, pid))

    # process 10: a process creation and 6 file creations in 10 s, then a network connection and 12 more file creations
    add("process_creation", 0, 10)
    for i in range(6):
        add("file_create", 1 + i, 10)
    # process 20: creation, network, file creation: the three-step rule
    add("process_creation", 100, 20)
    add("network_connection", 103, 20)
    add("file_create", 106, 20)
    # process 30: only 3 file creations: no group
    for i in range(3):
        add("file_create", 200 + i, 30)
    # unsupported events without a process ID
    for i in range(4):
        n += 1
        rows.append(event_row(n, "unsupported", 5 + i, None))
    return rows


@pytest.fixture
def factory(tmp_path):
    factory = open_workspace_database(tmp_path / "workspace" / "raven.db")
    with factory.kw["bind"].begin() as connection:
        connection.execute(insert(Event), sample_rows())
    yield factory
    factory.kw["bind"].dispose()


def counts(factory):
    with factory() as session:
        return (
            session.scalar(select(func.count()).select_from(CorrelatedEvent)),
            session.scalar(select(func.count()).select_from(CorrelationRule)),
        )


def test_groups_are_found_and_stored(tmp_path, factory):
    summary = run_correlation(factory, tmp_path / "summary.json")
    by_rule = {rule["rule_id"]: rule["groups"] for rule in summary["rules"]}
    assert by_rule == {"RAVEN-R001": 1, "RAVEN-R002": 1, "RAVEN-R003": 0}
    assert summary["totals"]["groups"] == 2
    assert summary["totals"]["correlated_event_rows"] == 6 + 3
    assert summary["totals"]["distinct_events"] == 6 + 3
    assert summary["totals"]["distinct_events_by_type"] == {"file_create": 6, "network_connection": 1, "process_creation": 2}
    assert counts(factory) == (9, 3)


def test_the_supported_events_examined_exclude_unsupported_ones(tmp_path, factory):
    summary = run_correlation(factory, None)
    assert summary["events_examined"] == 7 + 3 + 3


def test_correlated_event_rows_point_to_the_right_rule_group_and_event(tmp_path, factory):
    run_correlation(factory, None)
    with factory() as session:
        rules = {row.rule_name: row for row in session.scalars(select(CorrelationRule))}
        rows = session.execute(
            select(CorrelatedEvent.correlation_group_id, CorrelatedEvent.correlation_type, CorrelatedEvent.rule_id, Event.raw_event_ref)
            .join(Event, Event.id == CorrelatedEvent.event_id)
            .order_by(CorrelatedEvent.id)
        ).all()
    burst = rules["Mass File Modification Burst"].id
    stager = rules["Process Network File Stager Pattern"].id
    assert [r.correlation_group_id for r in rows[:6]] == ["RAVEN-R001:10:" + ts(0)] * 6
    assert [r.correlation_type for r in rows[:6]] == ["RAVEN-R001"] * 6
    assert {r.rule_id for r in rows[:6]} == {burst}
    assert [r.raw_event_ref for r in rows[:6]] == ["1:1", "1:2", "1:3", "1:4", "1:5", "1:6"]
    assert [r.correlation_group_id for r in rows[6:]] == ["RAVEN-R002:20:" + ts(100)] * 3
    assert {r.rule_id for r in rows[6:]} == {stager}
    assert [r.raw_event_ref for r in rows[6:]] == ["1:8", "1:9", "1:10"]


def test_the_rules_are_stored_with_their_definition(factory):
    run_correlation(factory, None)
    shipped = {rule.rule_name: rule for rule in load_rules()}
    with factory() as session:
        for row in session.scalars(select(CorrelationRule)):
            rule = shipped[row.rule_name]
            assert json.loads(row.rule_definition) == rule.to_definition()
            assert row.description == rule.description
            assert row.enabled is True


def test_the_summary_says_why_each_group_matched(tmp_path, factory):
    path = tmp_path / "out" / "summary.json"
    run_correlation(factory, path)
    summary = json.loads(path.read_text(encoding="utf-8"))
    assert summary["engine_options"] == {"step_order": "strict", "group_policy": "skip_matched", "membership": "minimal", "inclusive_window": True}
    first, second = summary["groups"]
    assert first["group_id"] == "RAVEN-R001:10:" + ts(0)
    assert first["rule_name"] == "Mass File Modification Burst" and first["severity"] == "HIGH" and first["confidence"] == 85
    assert first["match_key"] == "process_id" and first["match_value"] == "10" and first["time_window_seconds"] == 60
    assert first["steps"] == [
        {"event_type": "process_creation", "required": 1, "found": 1},
        {"event_type": "file_create", "required": 5, "found": 5},
    ]
    assert first["window_start"] == ts(0) and first["window_end"] == ts(5)
    assert first["event_count"] == 6 and len(first["event_refs"]) == 6
    assert second["group_id"] == "RAVEN-R002:20:" + ts(100)
    assert second["steps"] == [
        {"event_type": "process_creation", "required": 1, "found": 1},
        {"event_type": "network_connection", "required": 1, "found": 1},
        {"event_type": "file_create", "required": 1, "found": 1},
    ]


def test_running_twice_gives_the_same_rows_and_the_same_summary_file(tmp_path, factory):
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    run_correlation(factory, first)
    before = counts(factory)
    with factory() as session:
        ids_before = list(session.scalars(select(CorrelatedEvent.id).order_by(CorrelatedEvent.id)))
    run_correlation(factory, second)
    assert counts(factory) == before
    with factory() as session:
        assert list(session.scalars(select(CorrelatedEvent.id).order_by(CorrelatedEvent.id))) == ids_before
    assert first.read_bytes() == second.read_bytes()


def test_results_of_an_earlier_run_are_replaced(tmp_path, factory):
    run_correlation(factory, None)
    only_r003 = [rule for rule in load_rules() if rule.rule_id == "RAVEN-R003"]
    summary = run_correlation(factory, None, rules=only_r003)
    assert summary["totals"]["groups"] == 0
    assert counts(factory)[0] == 0
    with factory() as session:
        enabled = {row.rule_name: row.enabled for row in session.scalars(select(CorrelationRule))}
    assert enabled == {
        "Mass File Modification Burst": False,
        "Process Network File Stager Pattern": False,
        "Sustained File Creation Burst": True,
    }


def test_a_changed_rule_definition_is_updated_in_place(factory):
    run_correlation(factory, None)
    changed = [
        Rule("RAVEN-R001", "Mass File Modification Burst", "new description", (Step("process_creation", 1), Step("file_create", 2)), "process_id", 30, "LOW", 40)
    ]
    run_correlation(factory, None, rules=changed)
    with factory() as session:
        row = session.scalars(select(CorrelationRule).where(CorrelationRule.rule_name == "Mass File Modification Burst")).one()
        assert row.description == "new description"
        assert json.loads(row.rule_definition)["time_window_seconds"] == 30
        assert session.scalar(select(func.count()).select_from(CorrelationRule)) == 3


def test_other_options_change_the_result(tmp_path, factory):
    summary = run_correlation(factory, None, options=EngineOptions(step_order="loose", membership="window"))
    assert summary["engine_options"]["membership"] == "window"
    assert summary["totals"]["groups"] == 2


def test_no_supported_events_gives_no_groups_and_still_a_summary(tmp_path):
    factory = open_workspace_database(tmp_path / "empty.db")
    try:
        summary = run_correlation(factory, tmp_path / "s.json")
        assert summary["totals"] == {"groups": 0, "correlated_event_rows": 0, "distinct_events": 0, "distinct_events_by_type": {}}
        assert (tmp_path / "s.json").is_file()
        assert counts(factory) == (0, 3)
    finally:
        factory.kw["bind"].dispose()


def test_foreign_keys_hold_after_a_run(tmp_path, factory):
    run_correlation(factory, None)
    with factory() as session:
        assert session.execute(text("PRAGMA foreign_key_check")).fetchall() == []


def test_main_runs_and_prints_the_counts(tmp_path, factory, capsys):
    database = tmp_path / "workspace" / "raven.db"
    assert main([str(database), "--summary", str(tmp_path / "s.json")]) == 0
    printed = capsys.readouterr().out
    assert "engine options: strict / skip_matched / minimal / inclusive=True" in printed
    assert "RAVEN-R001 (Mass File Modification Burst, HIGH, confidence 85): 1 groups" in printed
    assert "groups: 2" in printed
    assert "correlated_events rows: 9" in printed
    assert "distinct events in groups: 9" in printed
    assert "summary sha256:" in printed


def test_main_reports_a_missing_database(tmp_path, capsys):
    assert main([str(tmp_path / "missing.db")]) == 1
    assert "ERROR" in capsys.readouterr().err
