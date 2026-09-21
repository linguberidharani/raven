"""Unit tests for merging correlation groups into sessions. All groups are SYNTHETIC test data."""

import pytest

from raven.correlation.engine import timestamp_to_ms
from raven.reconstruction.sequencer import (
    GroupInfo,
    ReconstructionError,
    build_sessions,
    describe,
    highest_severity,
    sanitize_id_part,
)


def ts(seconds, minute_offset=0):
    total = int(seconds)
    minutes, sec = divmod(total, 60)
    hours, minutes = divmod(39 + minute_offset + minutes, 60)
    return f"2026-09-13T{8 + hours:02d}:{minutes:02d}:{sec:02d}.000Z"


def group(group_id, start, end, computer="Dharani", rule="RAVEN-R001", severity="HIGH", events=6):
    return GroupInfo(group_id, rule, severity, computer, ts(start), ts(end), timestamp_to_ms(ts(start)), timestamp_to_ms(ts(end)), events)


def test_sanitize_replaces_every_non_alphanumeric_character_with_a_dash():
    assert sanitize_id_part("RAVEN-R001:1224:2026-09-13T08:39:49.695Z") == "RAVEN-R001-1224-2026-09-13T08-39-49-695Z"
    assert sanitize_id_part("my pc_1") == "my-pc-1"
    assert sanitize_id_part("Dharani") == "Dharani"
    assert sanitize_id_part("a..b") == "a--b"


def test_highest_severity_and_unknown_values():
    assert highest_severity(["LOW", "HIGH", "MEDIUM"]) == "HIGH"
    assert highest_severity(["INFO", "LOW"]) == "LOW"
    assert highest_severity(["MEDIUM"]) == "MEDIUM"
    with pytest.raises(ReconstructionError, match="unknown severity: CRITICAL"):
        highest_severity(["HIGH", "CRITICAL"])


def test_one_group_makes_one_session():
    g = group("RAVEN-R001:1:" + ts(0), 0, 30)
    (plan,) = build_sessions([g])
    assert plan.session_id == "RAVEN-SESSION-Dharani-RAVEN-R001-1-2026-09-13T08-39-00-000Z"
    assert plan.computer == "Dharani"
    assert plan.start_time == ts(0) and plan.end_time == ts(30)
    assert plan.severity == "HIGH"
    assert plan.confidence is None
    assert plan.groups == (g,)
    assert plan.description == "Reconstructed attack session containing 1 correlation group(s) from rule(s): RAVEN-R001."


def test_groups_within_the_gap_join_and_the_session_end_grows():
    a = group("A", 0, 100)
    b = group("B", 350, 400)  # starts 250 s after the end of A: joins
    c = group("C", 690, 700)  # starts 290 s after the end of B: joins
    (plan,) = build_sessions([c, a, b])
    assert [g.group_id for g in plan.groups] == ["A", "B", "C"]
    assert plan.start_time == ts(0) and plan.end_time == ts(700)


def test_a_group_after_a_longer_gap_starts_a_new_session():
    a = group("A", 0, 100)
    b = group("B", 401, 450)  # 301 s after the end of A
    plans = build_sessions([a, b])
    assert [p.groups[0].group_id for p in plans] == ["A", "B"]


def test_the_gap_limit_itself_is_inclusive():
    a = group("A", 0, 100)
    assert len(build_sessions([a, group("B", 400, 410)])) == 1  # exactly 300 s
    assert len(build_sessions([a, group("B", 401, 410)])) == 2


def test_an_overlapping_group_joins_even_when_it_ends_earlier():
    a = group("A", 0, 500)
    b = group("B", 100, 150)
    c = group("C", 700, 710)  # 200 s after the end of A (500), joins; B did not shorten the end
    (plan,) = build_sessions([a, b, c])
    assert plan.end_time == ts(710)


def test_the_merge_gap_can_be_changed():
    a, b = group("A", 0, 100), group("B", 200, 210)
    assert len(build_sessions([a, b], merge_gap_seconds=50)) == 2
    assert len(build_sessions([a, b], merge_gap_seconds=100)) == 1
    assert len(build_sessions([a, b], merge_gap_seconds=0)) == 2


@pytest.mark.parametrize("value", [-1, 1.5, "300", None, True])
def test_a_bad_merge_gap_is_rejected(value):
    with pytest.raises(ReconstructionError, match="merge_gap_seconds"):
        build_sessions([group("A", 0, 1)], merge_gap_seconds=value)


def test_computers_are_never_merged_together():
    a = group("A", 0, 100, computer="HOST-A")
    b = group("B", 10, 50, computer="HOST-B")
    plans = build_sessions([b, a])
    assert [p.computer for p in plans] == ["HOST-A", "HOST-B"]
    assert plans[0].session_id.startswith("RAVEN-SESSION-HOST-A-")
    assert plans[1].session_id.startswith("RAVEN-SESSION-HOST-B-")


def test_the_session_severity_is_the_highest_member_severity_and_rules_are_listed():
    groups = [
        group("A", 0, 10, rule="RAVEN-R002", severity="MEDIUM"),
        group("B", 20, 30, rule="RAVEN-R001", severity="HIGH"),
        group("C", 40, 50, rule="RAVEN-R001", severity="HIGH"),
    ]
    (plan,) = build_sessions(groups)
    assert plan.severity == "HIGH"
    assert plan.rule_ids == ("RAVEN-R001", "RAVEN-R002")
    assert plan.description == "Reconstructed attack session containing 3 correlation group(s) from rule(s): RAVEN-R001, RAVEN-R002."
    assert describe(plan.groups) == plan.description


def test_groups_with_the_same_start_are_ordered_by_group_id():
    b, a = group("B", 0, 10), group("A", 0, 20)
    (plan,) = build_sessions([b, a])
    assert [g.group_id for g in plan.groups] == ["A", "B"]
    assert plan.session_id.endswith("-A")
    assert plan.end_time == ts(20)


def test_the_result_does_not_depend_on_the_input_order():
    groups = [group(name, start, start + 5) for name, start in (("A", 0), ("B", 100), ("C", 1000), ("D", 1050))]
    forward = build_sessions(groups)
    backward = build_sessions(list(reversed(groups)))
    assert forward == backward
    assert len(forward) == 2


def test_no_groups_no_sessions():
    assert build_sessions([]) == []


def test_sessions_are_ordered_by_start_time():
    plans = build_sessions([group("B", 2000, 2010, computer="X"), group("A", 0, 10, computer="Y")])
    assert [p.computer for p in plans] == ["Y", "X"]
