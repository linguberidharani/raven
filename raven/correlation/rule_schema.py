"""Correlation rule schema and loader (spec section 6.6).

A rule is one YAML file:

    rule_id: "RAVEN-R001"
    rule_name: "Mass File Modification Burst"
    description: "..."
    steps:
      - event_type: "process_creation"
        min_count: 1
      - event_type: "file_create"
        min_count: 5
    match_key: "process_id"
    time_window_seconds: 60
    severity: "HIGH"          # HIGH | MEDIUM | LOW | INFO
    confidence: 85            # 0 to 100

A step may optionally narrow its event_type match to events whose value of one field contains a
piece of text (case-insensitive), instead of counting every event of that type:

    steps:
      - event_type: "file_create"
        min_count: 1
        field_match:
          field: "file_path"
          contains: "README"

field_match is optional; a step without it behaves exactly as before. When present it must have
exactly the two keys field and contains. field is "file_path" or "command_line" -- the only two
normalized-event fields rules can look inside for now, not a general query language. Each is only
meaningful on the event type that carries it, so it is only allowed on a step of the matching
event_type: file_path on file_create, command_line on process_creation. contains is matched as a
plain substring, case-insensitive; it is never a regular expression.

Test-only rules may use the severity TEST. They live in the tests, never in the shipped rules folder,
so the loader accepts TEST only when it is asked to (allow_test=True).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ALLOWED_EVENT_TYPES = ("process_creation", "network_connection", "file_create")
ALLOWED_MATCH_KEYS = ("process_id", "process_guid")
ALLOWED_SEVERITIES = ("HIGH", "MEDIUM", "LOW", "INFO")
TEST_SEVERITY = "TEST"

# field_match.field -> the one event_type it is allowed on (the only event_type that carries it).
ALLOWED_FIELD_MATCH_FIELDS: dict[str, str] = {
    "file_path": "file_create",
    "command_line": "process_creation",
}

_RULE_FIELDS = ("rule_id", "rule_name", "description", "steps", "match_key", "time_window_seconds", "severity", "confidence")
_STEP_FIELDS = ("event_type", "min_count")
_STEP_FIELDS_WITH_MATCH = ("event_type", "min_count", "field_match")
_FIELD_MATCH_FIELDS = ("field", "contains")

SHIPPED_RULES_DIR = Path(__file__).resolve().parent / "rules"


class RuleError(ValueError):
    """A rule file is invalid."""


@dataclass(frozen=True)
class FieldMatch:
    field: str
    contains: str


@dataclass(frozen=True)
class Step:
    event_type: str
    min_count: int
    field_match: FieldMatch | None = None


@dataclass(frozen=True)
class Rule:
    rule_id: str
    rule_name: str
    description: str
    steps: tuple[Step, ...]
    match_key: str
    time_window_seconds: int
    severity: str
    confidence: int

    @property
    def window_ms(self) -> int:
        return self.time_window_seconds * 1000

    def to_definition(self) -> dict[str, Any]:
        """The rule as a plain dictionary in the shape of the YAML file (stored as JSON in the database)."""
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "description": self.description,
            "steps": [_step_to_definition(s) for s in self.steps],
            "match_key": self.match_key,
            "time_window_seconds": self.time_window_seconds,
            "severity": self.severity,
            "confidence": self.confidence,
        }


def _step_to_definition(step: Step) -> dict[str, Any]:
    definition: dict[str, Any] = {"event_type": step.event_type, "min_count": step.min_count}
    if step.field_match is not None:
        definition["field_match"] = {"field": step.field_match.field, "contains": step.field_match.contains}
    return definition


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _field_match_from_dict(data: Any, step_number: int, event_type: str) -> FieldMatch:
    if not isinstance(data, dict) or set(data) != set(_FIELD_MATCH_FIELDS):
        raise RuleError(f"step {step_number}: field_match must have exactly the fields field and contains")
    if data["field"] not in ALLOWED_FIELD_MATCH_FIELDS:
        raise RuleError(f"step {step_number}: field_match.field must be one of " + ", ".join(ALLOWED_FIELD_MATCH_FIELDS))
    required_event_type = ALLOWED_FIELD_MATCH_FIELDS[data["field"]]
    if event_type != required_event_type:
        raise RuleError(
            f"step {step_number}: field_match.field {data['field']!r} is only valid on a step of "
            f"event_type {required_event_type!r}, not {event_type!r}"
        )
    if not isinstance(data["contains"], str) or not data["contains"].strip():
        raise RuleError(f"step {step_number}: field_match.contains must be a non-empty string")
    return FieldMatch(field=data["field"], contains=data["contains"])


def rule_from_dict(data: Any, *, allow_test: bool = False) -> Rule:
    """Validate a dictionary read from YAML and turn it into a Rule."""
    if not isinstance(data, dict):
        raise RuleError("a rule must be a mapping of fields")
    missing = [name for name in _RULE_FIELDS if name not in data]
    if missing:
        raise RuleError("missing field(s): " + ", ".join(missing))
    unknown = [name for name in data if name not in _RULE_FIELDS]
    if unknown:
        raise RuleError("unknown field(s): " + ", ".join(sorted(map(str, unknown))))

    for name in ("rule_id", "rule_name", "description"):
        if not isinstance(data[name], str) or not data[name].strip():
            raise RuleError(f"{name} must be a non-empty string")
    if data["match_key"] not in ALLOWED_MATCH_KEYS:
        raise RuleError("match_key must be one of " + ", ".join(ALLOWED_MATCH_KEYS))
    if not _is_int(data["time_window_seconds"]) or data["time_window_seconds"] < 1:
        raise RuleError("time_window_seconds must be a whole number of at least 1")
    severities = ALLOWED_SEVERITIES + ((TEST_SEVERITY,) if allow_test else ())
    if data["severity"] not in severities:
        raise RuleError("severity must be one of " + ", ".join(severities))
    if not _is_int(data["confidence"]) or not 0 <= data["confidence"] <= 100:
        raise RuleError("confidence must be a whole number from 0 to 100")

    raw_steps = data["steps"]
    if not isinstance(raw_steps, list) or not raw_steps:
        raise RuleError("steps must be a non-empty list")
    steps: list[Step] = []
    for number, raw_step in enumerate(raw_steps, start=1):
        if not isinstance(raw_step, dict) or set(raw_step) not in (set(_STEP_FIELDS), set(_STEP_FIELDS_WITH_MATCH)):
            raise RuleError(
                f"step {number} must have exactly the fields event_type and min_count "
                "(an optional field_match is also allowed)"
            )
        if raw_step["event_type"] not in ALLOWED_EVENT_TYPES:
            raise RuleError(f"step {number}: event_type must be one of " + ", ".join(ALLOWED_EVENT_TYPES))
        if not _is_int(raw_step["min_count"]) or raw_step["min_count"] < 1:
            raise RuleError(f"step {number}: min_count must be a whole number of at least 1")
        field_match = None
        if "field_match" in raw_step:
            field_match = _field_match_from_dict(raw_step["field_match"], number, raw_step["event_type"])
        steps.append(Step(raw_step["event_type"], raw_step["min_count"], field_match))

    return Rule(
        rule_id=data["rule_id"].strip(),
        rule_name=data["rule_name"].strip(),
        description=data["description"].strip(),
        steps=tuple(steps),
        match_key=data["match_key"],
        time_window_seconds=data["time_window_seconds"],
        severity=data["severity"],
        confidence=data["confidence"],
    )


def load_rule(path: str | os.PathLike[str], *, allow_test: bool = False) -> Rule:
    """Load one rule file. Errors name the file."""
    file = Path(path)
    try:
        data = yaml.safe_load(file.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RuleError(f"{file.name}: invalid YAML: {exc}") from exc
    try:
        return rule_from_dict(data, allow_test=allow_test)
    except RuleError as exc:
        raise RuleError(f"{file.name}: {exc}") from exc


def load_rules(folder: str | os.PathLike[str] = SHIPPED_RULES_DIR, *, allow_test: bool = False) -> list[Rule]:
    """Load every *.yaml rule of a folder, in file name order. Rule IDs must be unique."""
    directory = Path(folder)
    if not directory.is_dir():
        raise RuleError(f"rules folder not found: {directory}")
    rules = [load_rule(path, allow_test=allow_test) for path in sorted(directory.glob("*.yaml"))]
    seen: set[str] = set()
    for rule in rules:
        if rule.rule_id in seen:
            raise RuleError(f"rule_id {rule.rule_id} is used by more than one rule file")
        seen.add(rule.rule_id)
    return rules
