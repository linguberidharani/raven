"""Unit tests for the exploration tool. Synthetic events, temporary directories only."""

import pytest
from sqlalchemy import insert

from raven.correlation.engine import EngineOptions, EventPoint
from raven.correlation.explore import DEFAULT_TARGET, explore, format_result, load_events, main
from raven.correlation.rule_schema import Rule, Step
from raven.database.models import Event
from raven.database.session import open_workspace_database
from raven.parsers.schema import NORMALIZED_FIELDS

R003 = Rule("RAVEN-R003", "Sustained", "d", (Step("file_create", 10),), "process_id", 120, "HIGH", 90)
R001 = Rule("RAVEN-R001", "Burst", "d", (Step("process_creation", 1), Step("file_create", 5)), "process_id", 60, "HIGH", 85)


def ts(seconds):
    minutes, sec = divmod(int(seconds), 60)
    return f"2026-09-13T08:{39 + minutes:02d}:{sec:02d}.000Z"


def synthetic_events():
    events = []
    row = 0
    for i in range(25):  # one process, a burst of 25 file creations
        row += 1
        events.append(EventPoint.create(row, f"1:{row}", "file_create", ts(i), 7))
    row += 1
    events.append(EventPoint.create(row, f"1:{row}", "process_creation", ts(300), 8))
    for i in range(6):
        row += 1
        events.append(EventPoint.create(row, f"1:{row}", "file_create", ts(301 + i), 8))
    return events


def test_every_option_combination_is_tried_and_ranked():
    results = explore([R001, R003], synthetic_events())
    assert len(results) == 2 * 4 * 2 * 2
    assert [r.distance for r in results] == sorted(r.distance for r in results)
    assert len({r.options for r in results}) == len(results)


def test_the_numbers_of_one_variant_are_correct():
    results = {r.options: r for r in explore([R001, R003], synthetic_events())}
    default = results[EngineOptions("strict", "skip_window", "minimal", True)]
    assert default.groups_by_rule == {"RAVEN-R001": 1, "RAVEN-R003": 1}
    assert default.union_by_type == {"file_create": 15, "process_creation": 1}
    assert default.union_total == 16
    skip_matched = results[EngineOptions("strict", "skip_matched", "minimal", True)]
    assert skip_matched.groups_by_rule["RAVEN-R003"] == 2
    # 20 file creations of the burst (two groups of 10) and the 5 matched by the burst rule of the other process
    assert skip_matched.union_by_type["file_create"] == 25


def test_distance_and_the_example_group_flag():
    target = {"groups": {"RAVEN-R001": 1, "RAVEN-R003": 1}, "union": {"file_create": 15, "process_creation": 1}}
    results = explore([R001, R003], synthetic_events(), target=target, example_group_id="RAVEN-R001:8:" + ts(300))
    best = results[0]
    assert best.distance == 0
    assert best.has_example_group is True
    other = explore([R001, R003], synthetic_events(), target=target, example_group_id="RAVEN-R001:9:x")
    assert not any(r.has_example_group for r in other)


def test_the_default_target_is_the_spec_reference():
    assert DEFAULT_TARGET == {
        "groups": {"RAVEN-R001": 19, "RAVEN-R002": 14, "RAVEN-R003": 54},
        "union": {"file_create": 558, "network_connection": 14, "process_creation": 25},
    }


def test_format_result_is_one_readable_line():
    result = explore([R001, R003], synthetic_events())[0]
    line = format_result(1, result, ["RAVEN-R001", "RAVEN-R003"])
    assert line.startswith(" 1. distance")
    assert "\n" not in line and "R001" in line and "R003" in line and "spec example group" in line


def make_database(tmp_path):
    factory = open_workspace_database(tmp_path / "raven.db")
    rows = []
    for number, event in enumerate(synthetic_events(), start=1):
        row = {name: None for name in NORMALIZED_FIELDS}
        row.update(
            raw_event_ref=event.raw_event_ref,
            event_id=11,
            event_type=event.event_type,
            timestamp=event.timestamp,
            computer="SYNTHETIC-LAB-HOST",
            process_id=event.process_id,
            normalization_status="OK",
        )
        rows.append(row)
    rows.append(
        {**{name: None for name in NORMALIZED_FIELDS}, "raw_event_ref": "1:999", "event_id": 5, "event_type": "unsupported",
         "timestamp": ts(1), "computer": "SYNTHETIC-LAB-HOST", "normalization_status": "UNSUPPORTED_EVENT_ID"}
    )
    with factory.kw["bind"].begin() as connection:
        connection.execute(insert(Event), rows)
    factory.kw["bind"].dispose()
    return tmp_path / "raven.db"


def test_events_are_loaded_from_the_database_without_the_unsupported_ones(tmp_path):
    events = load_events(str(make_database(tmp_path)))
    assert len(events) == len(synthetic_events())
    assert all(e.event_type != "unsupported" for e in events)
    assert events[0].raw_event_ref == "1:1" and events[0].process_id == 7


def test_loading_a_missing_database_fails(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_events(str(tmp_path / "missing.db"))


def test_main_prints_the_ranking(tmp_path, capsys):
    assert main([str(make_database(tmp_path)), "--top", "3"]) == 0
    printed = capsys.readouterr().out
    assert "events used: 32" in printed
    assert "combinations tried: 32" in printed
    assert printed.count("distance") == 3
    assert "spec numbers:" in printed


def test_main_reports_a_missing_database(tmp_path, capsys):
    assert main([str(tmp_path / "missing.db")]) == 1
    assert "ERROR" in capsys.readouterr().err
