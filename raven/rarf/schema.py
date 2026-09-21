"""RARF v1.0 schema and validation (spec section 6.10).

RARF is the formal evidence record of one attack session: one JSON document per session,
RARF-<session_id>.json. It only formalizes evidence that earlier stages already established. It never
infers intent, never detects and never recalculates impact, and it contains no generation time, so the
same database always gives byte-identical files.

    rarf_version, rarf_id ("RARF-<session_id>")
    attack_session  { session_id, computer, start_time, end_time, severity, confidence, description }
    detection       { correlation_groups[ {correlation_group_id, correlation_type, event_ids[]} ],
                      rules[ {rule_database_id, description, enabled, rule_definition, ...} ],
                      event_ids[] }
    timeline        { events[ {timeline_event_id, event_id, sequence_number, timestamp, raw_event_ref,
                                event_type, computer, user} ] }
    impact          { categories { <name>: {impact_analysis_id, impact_score, affected_assets[], analysis{}} } }
    traceability    { event_ids[], raw_event_refs[], correlation_group_ids[], timeline_event_ids[],
                      impact_analysis_ids[] }

All event_ids are database IDs of the events table; raw_event_refs are the "<evidence_id>:<record_id>"
references that lead to the raw record and its original XML.

validate_rarf checks the structure and that the sections agree with each other.
"""

from __future__ import annotations

from typing import Any

RARF_VERSION = "1.0"
IMPACT_CATEGORIES = ("files_affected", "network_activity", "process_activity", "unsupported_events")
SEVERITIES = ("HIGH", "MEDIUM", "LOW", "INFO")

TOP_LEVEL = ("rarf_version", "rarf_id", "attack_session", "detection", "timeline", "impact", "traceability")
SESSION_FIELDS = ("session_id", "computer", "start_time", "end_time", "severity", "confidence", "description")
GROUP_FIELDS = ("correlation_group_id", "correlation_type", "event_ids")
RULE_REQUIRED = ("rule_database_id", "description", "enabled", "rule_definition")
TIMELINE_FIELDS = ("timeline_event_id", "event_id", "sequence_number", "timestamp", "raw_event_ref", "event_type", "computer", "user")
CATEGORY_FIELDS = ("impact_analysis_id", "impact_score", "affected_assets", "analysis")
TRACEABILITY_FIELDS = ("event_ids", "raw_event_refs", "correlation_group_ids", "timeline_event_ids", "impact_analysis_ids")


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _int_list(value: Any) -> bool:
    return isinstance(value, list) and all(_is_int(item) for item in value)


def _str_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _exact_keys(name: str, value: Any, expected: tuple[str, ...], problems: list[str]) -> bool:
    if not isinstance(value, dict):
        problems.append(f"{name} must be an object")
        return False
    missing = [key for key in expected if key not in value]
    extra = [key for key in value if key not in expected]
    if missing:
        problems.append(f"{name}: missing {', '.join(missing)}")
    if extra:
        problems.append(f"{name}: unexpected {', '.join(sorted(map(str, extra)))}")
    return not missing and not extra


def validate_rarf(document: Any) -> list[str]:
    """Return the problems found in a RARF document. An empty list means it is valid."""
    problems: list[str] = []
    if not _exact_keys("rarf", document, TOP_LEVEL, problems):
        return problems

    if document["rarf_version"] != RARF_VERSION:
        problems.append(f"rarf_version must be {RARF_VERSION}")

    # ------------------------------------------------------------ attack session
    session = document["attack_session"]
    session_ok = _exact_keys("attack_session", session, SESSION_FIELDS, problems)
    if session_ok:
        for name in ("session_id", "computer", "start_time", "end_time", "description"):
            if not isinstance(session[name], str) or not session[name]:
                problems.append(f"attack_session.{name} must be a non-empty string")
        if session["severity"] not in SEVERITIES:
            problems.append("attack_session.severity must be one of " + ", ".join(SEVERITIES))
        confidence = session["confidence"]
        if confidence is not None and not (_is_int(confidence) and 0 <= confidence <= 100):
            problems.append("attack_session.confidence must be null or a whole number from 0 to 100")
        if isinstance(session["session_id"], str) and document["rarf_id"] != "RARF-" + session["session_id"]:
            problems.append("rarf_id must be RARF- followed by the session ID")

    # ------------------------------------------------------------ detection
    detection = document["detection"]
    groups: list[Any] = []
    rule_ids: set[str] = set()
    detection_event_ids: list[Any] = []
    if _exact_keys("detection", detection, ("correlation_groups", "rules", "event_ids"), problems):
        groups = detection["correlation_groups"]
        if not isinstance(groups, list):
            problems.append("detection.correlation_groups must be a list")
            groups = []
        for number, group in enumerate(groups, start=1):
            if not _exact_keys(f"detection.correlation_groups[{number}]", group, GROUP_FIELDS, problems):
                continue
            if not isinstance(group["correlation_group_id"], str) or not isinstance(group["correlation_type"], str):
                problems.append(f"detection.correlation_groups[{number}]: IDs must be strings")
            if not _int_list(group["event_ids"]) or not group["event_ids"]:
                problems.append(f"detection.correlation_groups[{number}].event_ids must be a non-empty list of integers")
        rules = detection["rules"]
        if not isinstance(rules, list):
            problems.append("detection.rules must be a list")
            rules = []
        for number, rule in enumerate(rules, start=1):
            if not isinstance(rule, dict) or any(key not in rule for key in RULE_REQUIRED):
                problems.append(f"detection.rules[{number}] needs {', '.join(RULE_REQUIRED)}")
                continue
            if not _is_int(rule["rule_database_id"]) or not isinstance(rule["enabled"], bool) or not isinstance(rule["description"], str):
                problems.append(f"detection.rules[{number}] has a field of the wrong type")
            definition = rule["rule_definition"]
            if not isinstance(definition, dict) or not isinstance(definition.get("rule_id"), str):
                problems.append(f"detection.rules[{number}].rule_definition must be an object with a rule_id")
            else:
                rule_ids.add(definition["rule_id"])
        detection_event_ids = detection["event_ids"]
        if not _int_list(detection_event_ids) or detection_event_ids != sorted(set(detection_event_ids)):
            problems.append("detection.event_ids must be a sorted list of distinct integers")
            detection_event_ids = []
        for number, group in enumerate(groups, start=1):
            if isinstance(group, dict) and _int_list(group.get("event_ids")):
                if not set(group["event_ids"]) <= set(detection_event_ids):
                    problems.append(f"detection.correlation_groups[{number}] has events that are not in detection.event_ids")
                if rule_ids and group.get("correlation_type") not in rule_ids:
                    problems.append(f"detection.correlation_groups[{number}].correlation_type is not one of the listed rules")

    # ------------------------------------------------------------ timeline
    timeline_events: list[Any] = []
    timeline = document["timeline"]
    if _exact_keys("timeline", timeline, ("events",), problems):
        timeline_events = timeline["events"] if isinstance(timeline["events"], list) else []
        if not isinstance(timeline["events"], list):
            problems.append("timeline.events must be a list")
        for number, entry in enumerate(timeline_events, start=1):
            if not _exact_keys(f"timeline.events[{number}]", entry, TIMELINE_FIELDS, problems):
                continue
            checks = (
                _is_int(entry["timeline_event_id"]),
                _is_int(entry["event_id"]),
                entry["sequence_number"] == number,
                isinstance(entry["timestamp"], str) and bool(entry["timestamp"]),
                isinstance(entry["raw_event_ref"], str) and bool(entry["raw_event_ref"]),
                isinstance(entry["event_type"], str) and bool(entry["event_type"]),
                isinstance(entry["computer"], str) and bool(entry["computer"]),
                entry["user"] is None or isinstance(entry["user"], str),
            )
            if not all(checks):
                problems.append(f"timeline.events[{number}] has a wrong value (sequence numbers must run 1, 2, 3, ...)")
        stamps = [entry.get("timestamp") for entry in timeline_events if isinstance(entry, dict)]
        if all(isinstance(stamp, str) for stamp in stamps) and stamps != sorted(stamps):
            problems.append("timeline.events must be in timestamp order")

    # ------------------------------------------------------------ impact
    impact = document["impact"]
    categories: dict[str, Any] = {}
    if _exact_keys("impact", impact, ("categories",), problems):
        categories = impact["categories"] if isinstance(impact["categories"], dict) else {}
        if list(categories) != list(IMPACT_CATEGORIES):
            problems.append("impact.categories must be " + ", ".join(IMPACT_CATEGORIES) + " in this order")
        for name, category in categories.items():
            if not _exact_keys(f"impact.categories.{name}", category, CATEGORY_FIELDS, problems):
                continue
            if not _is_int(category["impact_analysis_id"]) or not _is_int(category["impact_score"]):
                problems.append(f"impact.categories.{name}: IDs and scores must be integers")
            if not _str_list(category["affected_assets"]):
                problems.append(f"impact.categories.{name}.affected_assets must be a list of strings")
            elif category["impact_score"] != len(category["affected_assets"]):
                problems.append(f"impact.categories.{name}.impact_score must equal the number of affected assets")
            analysis = category["analysis"]
            if not isinstance(analysis, dict) or not {"event_ids", "raw_event_refs", "event_count", "details"} <= set(analysis):
                problems.append(f"impact.categories.{name}.analysis needs event_ids, raw_event_refs, event_count and details")
            elif not (analysis["event_count"] == len(analysis["event_ids"]) == len(analysis["raw_event_refs"])):
                problems.append(f"impact.categories.{name}.analysis: event_count must equal the number of events and references")

    # ------------------------------------------------------------ traceability and agreement
    trace = document["traceability"]
    if _exact_keys("traceability", trace, TRACEABILITY_FIELDS, problems):
        if not _int_list(trace["event_ids"]) or trace["event_ids"] != sorted(set(trace["event_ids"])):
            problems.append("traceability.event_ids must be a sorted list of distinct integers")
        if not _str_list(trace["raw_event_refs"]) or len(set(trace["raw_event_refs"])) != len(trace["raw_event_refs"]):
            problems.append("traceability.raw_event_refs must be a list of distinct strings")
        elif len(trace["raw_event_refs"]) != len(trace["event_ids"]):
            problems.append("traceability.raw_event_refs must have one reference per event ID")
        if not _str_list(trace["correlation_group_ids"]):
            problems.append("traceability.correlation_group_ids must be a list of strings")
        if not _int_list(trace["timeline_event_ids"]) or trace["timeline_event_ids"] != sorted(set(trace["timeline_event_ids"])):
            problems.append("traceability.timeline_event_ids must be a sorted list of distinct integers")
        if not _int_list(trace["impact_analysis_ids"]) or trace["impact_analysis_ids"] != sorted(set(trace["impact_analysis_ids"])):
            problems.append("traceability.impact_analysis_ids must be a sorted list of distinct integers")

        if not problems:
            timeline_ids = sorted(entry["event_id"] for entry in timeline_events)
            if trace["event_ids"] != detection_event_ids:
                problems.append("traceability.event_ids must equal detection.event_ids")
            if timeline_ids != trace["event_ids"]:
                problems.append("the timeline must hold exactly the events of traceability.event_ids, each once")
            if trace["correlation_group_ids"] != [group["correlation_group_id"] for group in groups]:
                problems.append("traceability.correlation_group_ids must list the detection groups in order")
            if trace["timeline_event_ids"] != sorted(entry["timeline_event_id"] for entry in timeline_events):
                problems.append("traceability.timeline_event_ids must list the timeline events")
            if trace["impact_analysis_ids"] != sorted(category["impact_analysis_id"] for category in categories.values()):
                problems.append("traceability.impact_analysis_ids must list the impact categories")
            if not {entry["raw_event_ref"] for entry in timeline_events} == set(trace["raw_event_refs"]):
                problems.append("traceability.raw_event_refs must be the references of the timeline events")
            if sum(category["analysis"]["event_count"] for category in categories.values()) != len(timeline_events):
                problems.append("the impact categories must together cover exactly the timeline events")
    return problems
