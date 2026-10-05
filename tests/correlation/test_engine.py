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
from raven.correlation.rule_schema import SHIPPED_RULES_DIR, FieldMatch, Rule, Step, load_rules

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
    assert EngineOptions().label() == "strict/skip_matched/minimal/inclusive"


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


# ---------------------------------------------------------------- field_match (optional step condition)


def make_file_events(spec, pid=1224):
    """spec: list of (seconds, file_path) -> file_create EventPoints."""
    return [EventPoint.create(n, f"1:{n}", "file_create", ts(seconds), pid, file_path=path) for n, (seconds, path) in enumerate(spec, start=1)]


def make_process_events(spec, pid=1224):
    """spec: list of (seconds, command_line) -> process_creation EventPoints."""
    return [EventPoint.create(n, f"1:{n}", "process_creation", ts(seconds), pid, command_line=cmd) for n, (seconds, cmd) in enumerate(spec, start=1)]


RANSOM_NOTE_RULE = Rule(
    "TEST-NOTE", "Ransom note", "d",
    (Step("file_create", 1, FieldMatch("file_path", "README")),),
    "process_id", 60, "HIGH", 80,
)

VSSADMIN_RULE = Rule(
    "TEST-VSS", "Shadow copy delete", "d",
    (Step("process_creation", 1, FieldMatch("command_line", "vssadmin")),),
    "process_id", 60, "HIGH", 80,
)


# 1. A matching file_path pattern produces a match.
def test_a_matching_file_path_field_match_produces_a_group():
    events = make_file_events([(0, r"C:\Users\lab\Desktop\README_DECRYPT.txt")])
    (group,) = find_groups(RANSOM_NOTE_RULE, events, DEFAULT)
    assert group.event_row_ids == (1,)
    assert group.step_counts == (1,)


def test_a_matching_file_path_field_match_is_case_insensitive():
    events = make_file_events([(0, r"C:\Users\lab\Desktop\readme_decrypt.TXT")])
    (group,) = find_groups(RANSOM_NOTE_RULE, events, DEFAULT)
    assert group.event_row_ids == (1,)


# 2. A non-matching file_path produces no match.
def test_a_non_matching_file_path_field_match_produces_no_group():
    events = make_file_events([(0, r"C:\Users\lab\Documents\report.docx")])
    assert find_groups(RANSOM_NOTE_RULE, events, DEFAULT) == []


def test_a_null_file_path_does_not_satisfy_a_field_match():
    events = [EventPoint.create(1, "1:1", "file_create", ts(0), 1224, file_path=None)]
    assert find_groups(RANSOM_NOTE_RULE, events, DEFAULT) == []


# 3. A matching command_line pattern produces a match.
def test_a_matching_command_line_field_match_produces_a_group():
    events = make_process_events([(0, r"C:\Windows\System32\vssadmin.exe delete shadows /all /quiet")])
    (group,) = find_groups(VSSADMIN_RULE, events, DEFAULT)
    assert group.event_row_ids == (1,)


def test_a_matching_command_line_field_match_is_case_insensitive():
    events = make_process_events([(0, "VSSADMIN.EXE DELETE SHADOWS /ALL /QUIET")])
    (group,) = find_groups(VSSADMIN_RULE, events, DEFAULT)
    assert group.event_row_ids == (1,)


# 4. A non-matching command_line produces no match.
def test_a_non_matching_command_line_field_match_produces_no_group():
    events = make_process_events([(0, r"C:\Windows\System32\notepad.exe")])
    assert find_groups(VSSADMIN_RULE, events, DEFAULT) == []


def test_a_null_command_line_does_not_satisfy_a_field_match():
    events = [EventPoint.create(1, "1:1", "process_creation", ts(0), 1224, command_line=None)]
    assert find_groups(VSSADMIN_RULE, events, DEFAULT) == []


# A rule can mix a field_match step with a plain step, in the same strict sequence.
def test_field_match_combines_with_a_plain_step_in_sequence():
    rule = Rule(
        "TEST-MIX", "Mix", "d",
        (Step("process_creation", 1), Step("file_create", 1, FieldMatch("file_path", "README"))),
        "process_id", 60, "HIGH", 80,
    )
    events = [
        EventPoint.create(1, "1:1", "process_creation", ts(0), 1224),
        EventPoint.create(2, "1:2", "file_create", ts(1), 1224, file_path=r"C:\Temp\notes.txt"),
        EventPoint.create(3, "1:3", "file_create", ts(2), 1224, file_path=r"C:\Temp\README.txt"),
    ]
    (group,) = find_groups(rule, events, DEFAULT)
    assert group.event_row_ids == (1, 3)  # the non-matching file_create (2) is skipped, not counted


def test_field_match_is_honoured_in_loose_step_order_too():
    # Mirrors the existing test_strict_order_needs_each_step_after_the_previous_one (R002), but the
    # last step also carries a field_match: the matching file_create (the README) sits chronologically
    # BEFORE the network_connection step that must precede it in a strict sequence, so strict order
    # must fail to find it there while loose order (counts only, any order) must still find it.
    rule = Rule(
        "TEST-ORDER", "Order", "d",
        (Step("process_creation", 1), Step("network_connection", 1), Step("file_create", 1, FieldMatch("file_path", "README"))),
        "process_id", 60, "HIGH", 80,
    )
    events = [
        EventPoint.create(1, "1:1", "process_creation", ts(0), 1224),
        EventPoint.create(2, "1:2", "file_create", ts(5), 1224, file_path=r"C:\Temp\README.txt"),
        EventPoint.create(3, "1:3", "network_connection", ts(10), 1224),
    ]
    assert find_groups(rule, events, EngineOptions(step_order="strict")) == []
    (group,) = find_groups(rule, events, EngineOptions(step_order="loose"))
    # matched indexes are sorted before being returned (engine.py: "return sorted(matched)"), so the
    # row ids come back in index order, not in the order each step happened to pick them.
    assert group.event_row_ids == (1, 2, 3)


def test_field_match_is_honoured_in_window_membership_and_never_silently_ignored():
    rule = Rule(
        "TEST-NOTE-W", "Ransom note", "d",
        (Step("file_create", 1, FieldMatch("file_path", "README")),),
        "process_id", 60, "HIGH", 80,
    )
    events = make_file_events(
        [
            (0, r"C:\Temp\README.txt"),
            (1, r"C:\Temp\unrelated.txt"),  # same event_type, does not satisfy field_match
            (2, r"C:\Temp\README2.txt"),
        ]
    )
    (first_minimal, second_minimal) = find_groups(rule, events, EngineOptions(membership="minimal"))
    (first_window,) = find_groups(rule, events, EngineOptions(membership="window"))
    assert first_minimal.event_row_ids == (1,)
    # "window" holds every event that satisfies a step of the rule -- the unrelated file_create (2)
    # does not satisfy the rule's only step (its field_match fails), so it stays out even though its
    # event_type matches. This is the "never silently ignored" requirement.
    assert first_window.event_row_ids == (1, 3)


def test_explain_group_reports_the_field_match_of_a_step():
    events = make_file_events([(0, r"C:\Temp\README.txt")])
    (group,) = find_groups(RANSOM_NOTE_RULE, events, DEFAULT)
    explanation = explain_group(RANSOM_NOTE_RULE, group, {e.row_id: e for e in events})
    assert explanation["steps"] == [
        {"event_type": "file_create", "required": 1, "found": 1, "field_match": {"field": "file_path", "contains": "README"}}
    ]


def test_explain_group_omits_field_match_for_a_plain_step_unchanged_shape():
    # Same assertion as test_explain_group_says_why_it_matched (R001, no field_match anywhere):
    # proves the "steps" shape for an ordinary rule is byte-identical to before field_match existed.
    events = make_events([("process_creation", 10)] + [("file_create", 20 + i) for i in range(5)])
    (group,) = find_groups(R001, events, DEFAULT)
    explanation = explain_group(R001, group, {e.row_id: e for e in events})
    assert explanation["steps"] == [
        {"event_type": "process_creation", "required": 1, "found": 1},
        {"event_type": "file_create", "required": 5, "found": 5},
    ]
    assert all("field_match" not in step for step in explanation["steps"])


# 5. Existing R001/R002/R003 behaviour remains unchanged: every pre-existing test above still
# passes unmodified against the new engine.py (see the full run below), and these three repeat the
# shipped rules' exact defining numbers from the spec as an explicit, named regression check.
def test_r001_r002_r003_shapes_are_exactly_as_before_field_match():
    assert R001.steps == (Step("process_creation", 1), Step("file_create", 5))
    assert R002.steps == (Step("process_creation", 1), Step("network_connection", 1), Step("file_create", 1))
    assert R003.steps == (Step("file_create", 10),)
    for rule in (R001, R002, R003):
        assert all(step.field_match is None for step in rule.steps)


# ---------------------------------------------------------------- R004 (the shipped README-pattern rule)

R004 = next(rule for rule in load_rules(SHIPPED_RULES_DIR) if rule.rule_id == "RAVEN-R004")


def test_r004_is_shipped_with_exactly_one_field_match_step():
    assert R004.steps == (Step("file_create", 1, FieldMatch("file_path", "README")),)
    assert R004.severity == "MEDIUM" and R004.confidence == 55


def test_r004_matches_a_readme_named_file_and_explains_why():
    events = make_file_events([(0, r"C:\Users\lab\Desktop\README_RESTORE_FILES.txt")])
    (group,) = find_groups(R004, events, DEFAULT)
    assert group.rule_id == "RAVEN-R004"
    explanation = explain_group(R004, group, {e.row_id: e for e in events})
    assert explanation["steps"] == [
        {"event_type": "file_create", "required": 1, "found": 1, "field_match": {"field": "file_path", "contains": "README"}}
    ]


def test_r004_does_not_match_an_ordinary_file_create():
    events = make_file_events([(0, r"C:\Users\lab\Documents\budget.xlsx")])
    assert find_groups(R004, events, DEFAULT) == []


def test_r004_does_not_match_a_legitimate_readme_from_installed_software():
    # The honest cost of a narrow substring rule: it cannot distinguish a ransom note from an
    # ordinary software README. RAVEN says so in the rule's own description rather than hiding it.
    events = make_file_events([(0, r"C:\Program Files\SomeApp\README.txt")])
    (group,) = find_groups(R004, events, DEFAULT)
    assert group.rule_id == "RAVEN-R004"  # it DOES match -- this is the rule's known limitation, not a bug


# ---------------------------------------------------------------- R005 (the shipped vssadmin-delete rule)

R005 = next(rule for rule in load_rules(SHIPPED_RULES_DIR) if rule.rule_id == "RAVEN-R005")


def test_r005_is_shipped_with_exactly_one_field_match_step():
    assert R005.steps == (Step("process_creation", 1, FieldMatch("command_line", "delete shadows")),)
    assert R005.severity == "HIGH" and R005.confidence == 70


def test_r005_matches_a_vssadmin_delete_command_and_explains_why():
    events = make_process_events([(0, r"C:\Windows\System32\vssadmin.exe delete shadows /all /quiet")])
    (group,) = find_groups(R005, events, DEFAULT)
    assert group.rule_id == "RAVEN-R005"
    explanation = explain_group(R005, group, {e.row_id: e for e in events})
    assert explanation["steps"] == [
        {"event_type": "process_creation", "required": 1, "found": 1, "field_match": {"field": "command_line", "contains": "delete shadows"}}
    ]


def test_r005_matches_case_insensitively():
    events = make_process_events([(0, "VSSADMIN.EXE DELETE SHADOWS /ALL /QUIET")])
    (group,) = find_groups(R005, events, DEFAULT)
    assert group.rule_id == "RAVEN-R005"


def test_r005_does_not_match_an_ordinary_process():
    events = make_process_events([(0, r"C:\Windows\System32\notepad.exe")])
    assert find_groups(R005, events, DEFAULT) == []


def test_r005_does_not_match_a_harmless_vssadmin_subcommand():
    # The precise two-word pattern ("vssadmin delete") is the point: listing or resizing shadow storage
    # uses vssadmin too but is not the destructive subcommand, and must not be flagged.
    events = make_process_events(
        [
            (0, r"C:\Windows\System32\vssadmin.exe list shadows"),
            (1, r"C:\Windows\System32\vssadmin.exe resize shadowstorage /for=C: /maxsize=10%"),
        ]
    )
    assert find_groups(R005, events, DEFAULT) == []


def test_r005_does_not_match_a_different_tool_that_also_deletes_shadow_copies():
    # The honest cost of a narrow substring rule: wmic-based deletion (a real alternative technique
    # some ransomware families use instead of vssadmin) is not covered by this one pattern. RAVEN's own
    # rule description does not claim otherwise -- this is a documented limitation, not a bug.
    events = make_process_events([(0, "wmic.exe shadowcopy delete")])
    assert find_groups(R005, events, DEFAULT) == []
