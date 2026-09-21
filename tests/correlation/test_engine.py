"""Unit tests for the correlation engine. All events are SYNTHETIC test data built in this file."""

import pytest

from raven.correlation.engine import (
    EngineOptions,
    EventPoint,
    explain_group,
    find_all_groups,
    find_groups,
    timestamp_to_ms,
)
from raven.correlation.rule_schema import Rule, Step

BASE = "2026-09-13T08:39:"


def ts(seconds, millis=0):
    total = int(seconds)
    minutes, sec = divmod(total, 60)
    return f"2026-09-13T08:{39 + minutes:02d}:{sec:02d}.{millis:03d}Z"


def make_events(spec, pid=1224):
    """spec: list of (event_type, seconds after 08:39:00) -> EventPoint list with row ids from 1."""
    events = []
    for number, (event_type, seconds) in enumerate(spec, start=1):
        events.append(EventPoint.create(number, f"1:{number}", event_type, ts(seconds), pid))
    return events


R001 = Rule("RAVEN-R001", "Burst", "d", (Step("process_creation", 1), Step("file_create", 5)), "process_id", 60, "HIGH", 85)
R002 = Rule("RAVEN-R002", "Stager", "d", (Step("process_creation", 1), Step("network_connection", 1), Step("file_create", 1)), "process_id", 120, "MEDIUM", 75)
R003 = Rule("RAVEN-R003", "Sustained", "d", (Step("file_create", 10),), "process_id", 120, "HIGH", 90)

DEFAULT = EngineOptions()


def test_timestamp_to_ms():
    assert timestamp_to_ms("1970-01-01T00:00:00.000Z") == 0
    assert timestamp_to_ms("1970-01-01T00:00:01.250Z") == 1250
    assert timestamp_to_ms("2026-09-13T08:39:49.695Z") - timestamp_to_ms("2026-09-13T08:39:49.000Z") == 695


def test_a_process_creation_followed_by_enough_file_creations_is_a_group():
    events = make_events([("process_creation", 10)] + [("file_create", 20 + i) for i in range(5)])
    (group,) = find_groups(R001, events, DEFAULT)
    assert group.group_id == "RAVEN-R001:1224:" + ts(10)
    assert group.rule_id == "RAVEN-R001"
    assert group.match_key == "process_id" and group.match_value == "1224"
    assert group.window_start == ts(10) and group.window_end == ts(24)
    assert group.event_row_ids == (1, 2, 3, 4, 5, 6)
    assert group.step_counts == (1, 5)


def test_too_few_file_creations_is_no_group():
    events = make_events([("process_creation", 10)] + [("file_create", 20 + i) for i in range(4)])
    assert find_groups(R001, events, DEFAULT) == []


def test_file_creations_outside_the_window_do_not_count():
    events = make_events([("process_creation", 0)] + [("file_create", 58 + i) for i in range(5)])  # 58..62 s
    assert find_groups(R001, events, DEFAULT) == []


def test_the_window_edge_is_inclusive_or_exclusive_as_configured():
    events = make_events([("process_creation", 0)] + [("file_create", 56 + i) for i in range(4)] + [("file_create", 60)])
    assert len(find_groups(R001, events, EngineOptions(inclusive_window=True))) == 1
    assert find_groups(R001, events, EngineOptions(inclusive_window=False)) == []


def test_file_creations_before_the_process_creation_do_not_count():
    events = make_events([("file_create", 1 + i) for i in range(5)] + [("process_creation", 10)])
    assert find_groups(R001, events, DEFAULT) == []


def test_different_keys_are_matched_separately():
    a = make_events([("process_creation", 0)] + [("file_create", 1 + i) for i in range(5)], pid=1)
    b = [EventPoint.create(100 + n, f"1:{100 + n}", t, ts(s), 2) for n, (t, s) in enumerate([("process_creation", 0)] + [("file_create", 1 + i) for i in range(3)])]
    groups = find_groups(R001, a + b, DEFAULT)
    assert [g.match_value for g in groups] == ["1"]


def test_events_of_other_processes_do_not_help():
    a = make_events([("process_creation", 0)] + [("file_create", 1 + i) for i in range(3)], pid=1)
    b = [EventPoint.create(50 + i, f"1:{50 + i}", "file_create", ts(5 + i), 2) for i in range(3)]
    assert find_groups(R001, a + b, DEFAULT) == []


def test_events_without_the_match_key_are_ignored():
    events = [EventPoint.create(1, "1:1", "process_creation", ts(0), None)] + [EventPoint.create(2 + i, f"1:{2 + i}", "file_create", ts(1 + i), None) for i in range(5)]
    assert find_groups(R001, events, DEFAULT) == []


def test_the_match_key_can_be_the_process_guid():
    rule = Rule("RAVEN-G", "G", "d", (Step("file_create", 2),), "process_guid", 60, "LOW", 50)
    events = [
        EventPoint.create(1, "1:1", "file_create", ts(0), 1, "{a}"),
        EventPoint.create(2, "1:2", "file_create", ts(1), 2, "{a}"),
        EventPoint.create(3, "1:3", "file_create", ts(2), 1, "{b}"),
    ]
    (group,) = find_groups(rule, events, DEFAULT)
    assert group.match_value == "{a}" and group.event_row_ids == (1, 2)


def test_strict_order_needs_each_step_after_the_previous_one():
    events = make_events([("process_creation", 0), ("file_create", 5), ("network_connection", 10)])
    assert find_groups(R002, events, EngineOptions(step_order="strict")) == []
    (group,) = find_groups(R002, events, EngineOptions(step_order="loose"))
    assert group.event_row_ids == (1, 2, 3)


def test_a_three_step_sequence_in_order():
    events = make_events([("process_creation", 0), ("network_connection", 5), ("file_create", 10)])
    (group,) = find_groups(R002, events, DEFAULT)
    assert group.group_id == "RAVEN-R002:1224:" + ts(0)
    assert group.step_counts == (1, 1, 1)


def test_min_count_of_a_later_step_needs_that_many_events():
    rule = Rule("RAVEN-X", "X", "d", (Step("process_creation", 1), Step("file_create", 3)), "process_id", 60, "LOW", 50)
    assert find_groups(rule, make_events([("process_creation", 0), ("file_create", 1), ("file_create", 2)]), DEFAULT) == []
    assert len(find_groups(rule, make_events([("process_creation", 0), ("file_create", 1), ("file_create", 2), ("file_create", 3)]), DEFAULT)) == 1


# ---------------------------------------------------------------- group policies


def burst_of_25():
    return make_events([("file_create", i) for i in range(25)])  # one per second, 0..24 s


@pytest.mark.parametrize(
    "policy, expected_groups, expected_first_sizes",
    [
        ("first", 1, [10]),
        ("skip_window", 1, [10]),
        ("skip_matched", 2, [10, 10]),
        ("all", 16, [10] + [10] * 15),
    ],
)
def test_group_policies_on_a_burst_of_25_events(policy, expected_groups, expected_first_sizes):
    groups = find_groups(R003, burst_of_25(), EngineOptions(group_policy=policy))
    assert len(groups) == expected_groups
    assert [len(g.event_row_ids) for g in groups] == expected_first_sizes


def test_skip_window_starts_a_new_group_after_the_window_ends():
    events = make_events([("file_create", i) for i in range(10)] + [("file_create", 200 + i) for i in range(10)])
    groups = find_groups(R003, events, EngineOptions(group_policy="skip_window"))
    assert [g.window_start for g in groups] == [ts(0), ts(200)]


def test_first_policy_finds_a_later_match_when_the_first_start_fails():
    events = make_events([("file_create", 0), ("file_create", 130)] + [("file_create", 131 + i) for i in range(9)])
    (group,) = find_groups(R003, events, EngineOptions(group_policy="first"))
    assert group.window_start == ts(130)


# ---------------------------------------------------------------- membership


def test_window_membership_holds_every_event_of_the_step_types_in_the_window():
    spec = [("process_creation", 0)] + [("file_create", 1 + i) for i in range(8)] + [("network_connection", 5)]
    events = make_events(spec)
    (minimal,) = find_groups(R001, events, EngineOptions(membership="minimal"))
    (window,) = find_groups(R001, events, EngineOptions(membership="window"))
    assert len(minimal.event_row_ids) == 6
    assert len(window.event_row_ids) == 9  # process creation and 8 file creations, not the network event
    assert window.step_counts == (1, 8)


def test_window_membership_leaves_out_events_after_the_window():
    events = make_events([("process_creation", 0)] + [("file_create", 1 + i) for i in range(5)] + [("file_create", 90)])
    (group,) = find_groups(R001, events, EngineOptions(membership="window"))
    assert group.event_row_ids == (1, 2, 3, 4, 5, 6)


# ---------------------------------------------------------------- determinism and ordering


def test_same_millisecond_events_are_ordered_by_row_id():
    events = [EventPoint.create(n, f"1:{n}", "file_create", ts(0), 1) for n in range(1, 11)]
    (group,) = find_groups(R003, list(reversed(events)), DEFAULT)
    assert group.event_row_ids == tuple(range(1, 11))


def test_input_order_does_not_change_the_result():
    events = make_events([("process_creation", 0)] + [("file_create", 1 + i) for i in range(12)])
    forward = find_all_groups([R001, R003], events, DEFAULT)
    backward = find_all_groups([R001, R003], list(reversed(events)), DEFAULT)
    assert forward == backward


def test_groups_come_in_rule_order_then_time_order_and_have_unique_ids():
    a = make_events([("process_creation", 0)] + [("file_create", 1 + i) for i in range(12)], pid=1)
    b = [EventPoint.create(100 + n, f"1:{100 + n}", t, ts(s), 2) for n, (t, s) in enumerate([("process_creation", 5)] + [("file_create", 6 + i) for i in range(12)])]
    groups = find_all_groups([R001, R003], a + b, DEFAULT)
    assert [g.rule_id for g in groups] == ["RAVEN-R001", "RAVEN-R001", "RAVEN-R003", "RAVEN-R003"]
    assert [g.match_value for g in groups] == ["1", "2", "1", "2"]
    assert len({g.group_id for g in groups}) == 4


def test_two_groups_with_the_same_id_are_kept_only_once():
    events = [EventPoint.create(n, f"1:{n}", "file_create", ts(0), 1) for n in range(1, 31)]  # 30 events in one millisecond
    groups = find_groups(R003, events, EngineOptions(group_policy="all"))
    assert len(groups) == 1


def test_options_are_validated():
    with pytest.raises(ValueError, match="step_order"):
        EngineOptions(step_order="x")
    with pytest.raises(ValueError, match="group_policy"):
        EngineOptions(group_policy="x")
    with pytest.raises(ValueError, match="membership"):
        EngineOptions(membership="x")
    assert EngineOptions().label() == "strict/skip_window/minimal/inclusive"


# ---------------------------------------------------------------- explanation


def test_explain_group_says_why_it_matched():
    events = make_events([("process_creation", 10)] + [("file_create", 20 + i) for i in range(5)])
    (group,) = find_groups(R001, events, DEFAULT)
    explanation = explain_group(R001, group, {e.row_id: e for e in events})
    assert explanation == {
        "group_id": "RAVEN-R001:1224:" + ts(10),
        "rule_id": "RAVEN-R001",
        "rule_name": "Burst",
        "severity": "HIGH",
        "confidence": 85,
        "match_key": "process_id",
        "match_value": "1224",
        "time_window_seconds": 60,
        "window_start": ts(10),
        "window_end": ts(24),
        "steps": [
            {"event_type": "process_creation", "required": 1, "found": 1},
            {"event_type": "file_create", "required": 5, "found": 5},
        ],
        "event_count": 6,
        "event_refs": ["1:1", "1:2", "1:3", "1:4", "1:5", "1:6"],
    }
