"""Unit tests for the rule schema and loader. Rules here are test data in temporary folders."""

import copy

import pytest

from raven.correlation.rule_schema import SHIPPED_RULES_DIR, Rule, RuleError, Step, load_rule, load_rules, rule_from_dict

GOOD = {
    "rule_id": "TEST-R1",
    "rule_name": "Example",
    "description": "An example.",
    "steps": [{"event_type": "process_creation", "min_count": 1}, {"event_type": "file_create", "min_count": 5}],
    "match_key": "process_id",
    "time_window_seconds": 60,
    "severity": "HIGH",
    "confidence": 85,
}


def changed(**changes):
    data = copy.deepcopy(GOOD)
    data.update(changes)
    return data


def test_a_good_rule_loads():
    rule = rule_from_dict(GOOD)
    assert rule == Rule(
        "TEST-R1", "Example", "An example.", (Step("process_creation", 1), Step("file_create", 5)), "process_id", 60, "HIGH", 85
    )
    assert rule.window_ms == 60000


def test_the_definition_round_trips():
    rule = rule_from_dict(GOOD)
    assert rule.to_definition() == GOOD
    assert rule_from_dict(rule.to_definition()) == rule


def test_surrounding_spaces_are_removed():
    rule = rule_from_dict(changed(rule_id=" TEST-R1 ", rule_name="  Example  "))
    assert rule.rule_id == "TEST-R1" and rule.rule_name == "Example"


@pytest.mark.parametrize("field", list(GOOD))
def test_a_missing_field_is_reported(field):
    data = copy.deepcopy(GOOD)
    del data[field]
    with pytest.raises(RuleError, match=f"missing field.*{field}"):
        rule_from_dict(data)


def test_an_unknown_field_is_reported():
    with pytest.raises(RuleError, match="unknown field.*extra"):
        rule_from_dict(changed(extra=1))


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"rule_id": ""}, "rule_id must be a non-empty string"),
        ({"rule_name": 5}, "rule_name must be a non-empty string"),
        ({"description": "   "}, "description must be a non-empty string"),
        ({"match_key": "user"}, "match_key must be one of"),
        ({"time_window_seconds": 0}, "time_window_seconds"),
        ({"time_window_seconds": "60"}, "time_window_seconds"),
        ({"time_window_seconds": True}, "time_window_seconds"),
        ({"severity": "CRITICAL"}, "severity must be one of"),
        ({"confidence": 101}, "confidence"),
        ({"confidence": -1}, "confidence"),
        ({"confidence": 85.5}, "confidence"),
        ({"steps": []}, "steps must be a non-empty list"),
        ({"steps": "x"}, "steps must be a non-empty list"),
        ({"steps": [{"event_type": "file_create"}]}, "step 1 must have exactly"),
        ({"steps": [{"event_type": "file_create", "min_count": 1, "x": 1}]}, "step 1 must have exactly"),
        ({"steps": [{"event_type": "registry", "min_count": 1}]}, "step 1: event_type must be one of"),
        ({"steps": [{"event_type": "unsupported", "min_count": 1}]}, "step 1: event_type must be one of"),
        ({"steps": [{"event_type": "file_create", "min_count": 0}]}, "step 1: min_count"),
    ],
)
def test_invalid_values_are_reported(changes, message):
    with pytest.raises(RuleError, match=message):
        rule_from_dict(changed(**changes))


def test_not_a_mapping():
    with pytest.raises(RuleError, match="mapping"):
        rule_from_dict(["a"])


def test_the_test_severity_needs_permission():
    with pytest.raises(RuleError, match="severity must be one of"):
        rule_from_dict(changed(severity="TEST"))
    assert rule_from_dict(changed(severity="TEST"), allow_test=True).severity == "TEST"


def test_process_guid_is_an_allowed_match_key():
    assert rule_from_dict(changed(match_key="process_guid")).match_key == "process_guid"


def write_rule(folder, name, text):
    path = folder / name
    path.write_text(text, encoding="utf-8")
    return path


def test_load_rule_names_the_file_in_errors(tmp_path):
    bad_yaml = write_rule(tmp_path, "bad.yaml", "rule_id: [unclosed")
    with pytest.raises(RuleError, match="bad.yaml: invalid YAML"):
        load_rule(bad_yaml)
    bad_rule = write_rule(tmp_path, "worse.yaml", "rule_id: X\n")
    with pytest.raises(RuleError, match="worse.yaml: missing field"):
        load_rule(bad_rule)


def test_load_rules_reads_yaml_files_in_name_order(tmp_path):
    import yaml

    for name, rule_id in (("b.yaml", "TEST-B"), ("a.yaml", "TEST-A")):
        (tmp_path / name).write_text(yaml.safe_dump(changed(rule_id=rule_id)), encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignored", encoding="utf-8")
    assert [rule.rule_id for rule in load_rules(tmp_path)] == ["TEST-A", "TEST-B"]


def test_duplicate_rule_ids_are_rejected(tmp_path):
    import yaml

    for name in ("a.yaml", "b.yaml"):
        (tmp_path / name).write_text(yaml.safe_dump(changed()), encoding="utf-8")
    with pytest.raises(RuleError, match="more than one"):
        load_rules(tmp_path)


def test_a_missing_folder_is_an_error(tmp_path):
    with pytest.raises(RuleError, match="not found"):
        load_rules(tmp_path / "missing")


# ---------------------------------------------------------------- the shipped rules


def test_the_shipped_rules_are_the_three_of_the_spec():
    rules = {rule.rule_id: rule for rule in load_rules(SHIPPED_RULES_DIR)}
    assert list(rules) == ["RAVEN-R001", "RAVEN-R002", "RAVEN-R003"]

    r1, r2, r3 = rules["RAVEN-R001"], rules["RAVEN-R002"], rules["RAVEN-R003"]
    assert r1.rule_name == "Mass File Modification Burst"
    assert r1.steps == (Step("process_creation", 1), Step("file_create", 5))
    assert (r1.time_window_seconds, r1.severity, r1.confidence, r1.match_key) == (60, "HIGH", 85, "process_id")

    assert r2.rule_name == "Process Network File Stager Pattern"
    assert r2.steps == (Step("process_creation", 1), Step("network_connection", 1), Step("file_create", 1))
    assert (r2.time_window_seconds, r2.severity, r2.confidence, r2.match_key) == (120, "MEDIUM", 75, "process_id")

    assert r3.rule_name == "Sustained File Creation Burst"
    assert r3.steps == (Step("file_create", 10),)
    assert (r3.time_window_seconds, r3.severity, r3.confidence, r3.match_key) == (120, "HIGH", 90, "process_id")


def test_the_shipped_rules_have_no_test_severity_and_no_forbidden_wording():
    forbidden = ("encrypt", "decrypt", "real-time protection", "automatically detects and prevents")
    for rule in load_rules(SHIPPED_RULES_DIR):
        assert rule.severity != "TEST"
        text = (rule.rule_name + " " + rule.description).lower()
        assert not any(word in text for word in forbidden), rule.rule_id
