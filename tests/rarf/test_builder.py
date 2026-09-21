"""Unit tests for building RARF documents. Synthetic events, temporary directories only."""

import json

import pytest
from sqlalchemy import text

from raven.rarf.builder import RarfError, build_rarf, list_session_ids
from raven.rarf.schema import IMPACT_CATEGORIES, validate_rarf

from tests.rarf.conftest import prepare_workspace, rows_for, stamp


def build(factory):
    (session_id,) = list_session_ids(factory)
    return build_rarf(factory, session_id)


def test_the_document_is_valid_and_has_the_sections_of_the_spec(factory):
    prepare_workspace(factory, rows_for(10, 0))
    document = build(factory)
    assert validate_rarf(document) == []
    assert list(document) == ["rarf_version", "rarf_id", "attack_session", "detection", "timeline", "impact", "traceability"]
    assert document["rarf_version"] == "1.0"
    assert document["rarf_id"] == "RARF-" + document["attack_session"]["session_id"]


def test_attack_session_section(factory):
    prepare_workspace(factory, rows_for(10, 0))
    session = build(factory)["attack_session"]
    assert list(session) == ["session_id", "computer", "start_time", "end_time", "severity", "confidence", "description"]
    assert session["computer"] == "Dharani"
    assert session["start_time"] == stamp(0) and session["end_time"] == stamp(10)
    assert session["severity"] == "HIGH" and session["confidence"] is None
    assert session["description"].startswith("Reconstructed attack session containing 2 correlation group(s)")


def test_detection_section_lists_groups_rules_and_events(factory):
    prepare_workspace(factory, rows_for(10, 0))
    detection = build(factory)["detection"]
    groups = detection["correlation_groups"]
    assert [g["correlation_group_id"] for g in groups] == ["RAVEN-R001:10:" + stamp(0), "RAVEN-R003:10:" + stamp(1)]
    assert [g["correlation_type"] for g in groups] == ["RAVEN-R001", "RAVEN-R003"]
    assert [len(g["event_ids"]) for g in groups] == [6, 10]
    assert detection["event_ids"] == sorted(detection["event_ids"]) and len(detection["event_ids"]) == 11
    rules = detection["rules"]
    assert [r["rule_id"] for r in rules] == ["RAVEN-R001", "RAVEN-R003"]  # only the rules the groups came from
    assert rules[0]["rule_definition"]["steps"][0] == {"event_type": "process_creation", "min_count": 1}
    assert rules[0]["enabled"] is True and rules[0]["rule_name"] == "Mass File Modification Burst"
    assert isinstance(rules[0]["rule_database_id"], int)


def test_group_events_are_in_time_order(factory):
    prepare_workspace(factory, rows_for(10, 0))
    document = build(factory)
    by_id = {e["event_id"]: e for e in document["timeline"]["events"]}
    for group in document["detection"]["correlation_groups"]:
        stamps = [by_id[i]["timestamp"] for i in group["event_ids"]]
        assert stamps == sorted(stamps)


def test_timeline_section(factory):
    prepare_workspace(factory, rows_for(10, 0))
    events = build(factory)["timeline"]["events"]
    assert len(events) == 11
    assert list(events[0]) == ["timeline_event_id", "event_id", "sequence_number", "timestamp", "raw_event_ref", "event_type", "computer", "user"]
    assert [e["sequence_number"] for e in events] == list(range(1, 12))
    assert events[0]["event_type"] == "process_creation" and events[0]["raw_event_ref"] == "1:1"
    assert events[0]["computer"] == "Dharani" and events[0]["user"] == "SYNTHETIC\\tester"


def test_impact_section(factory):
    prepare_workspace(factory, rows_for(10, 0))
    categories = build(factory)["impact"]["categories"]
    assert list(categories) == list(IMPACT_CATEGORIES)
    files = categories["files_affected"]
    assert files["impact_score"] == 3 == len(files["affected_assets"])
    assert files["analysis"]["event_count"] == 10
    assert categories["unsupported_events"]["impact_score"] == 0 and categories["unsupported_events"]["affected_assets"] == []
    assert isinstance(files["impact_analysis_id"], int)


def test_traceability_section(factory):
    prepare_workspace(factory, rows_for(10, 0))
    document = build(factory)
    trace = document["traceability"]
    assert list(trace) == ["event_ids", "raw_event_refs", "correlation_group_ids", "timeline_event_ids", "impact_analysis_ids"]
    assert len(trace["event_ids"]) == len(trace["raw_event_refs"]) == len(trace["timeline_event_ids"]) == 11
    assert len(trace["correlation_group_ids"]) == 2 and len(trace["impact_analysis_ids"]) == 4
    assert trace["event_ids"] == document["detection"]["event_ids"]


def test_building_twice_gives_the_same_document(factory):
    prepare_workspace(factory, rows_for(10, 0))
    assert json.dumps(build(factory)) == json.dumps(build(factory))


def test_two_sessions_give_two_separate_documents(factory):
    prepare_workspace(factory, rows_for(10, 0) + rows_for(20, 5000, first_number=100))
    first_id, second_id = list_session_ids(factory)
    first, second = build_rarf(factory, first_id), build_rarf(factory, second_id)
    assert validate_rarf(first) == [] and validate_rarf(second) == []
    assert set(first["traceability"]["event_ids"]).isdisjoint(second["traceability"]["event_ids"])
    assert first["attack_session"]["start_time"] == stamp(0) and second["attack_session"]["start_time"] == stamp(5000)


def test_an_unknown_session_is_an_error(factory):
    prepare_workspace(factory, rows_for(10, 0))
    with pytest.raises(RarfError, match="not found"):
        build_rarf(factory, "RAVEN-SESSION-nothing")


def test_a_missing_timeline_is_an_error(factory):
    prepare_workspace(factory, rows_for(10, 0), through="reconstruction")
    with pytest.raises(RarfError, match="no timeline"):
        build(factory)


def test_a_missing_impact_analysis_is_an_error(factory):
    prepare_workspace(factory, rows_for(10, 0), through="timeline")
    with pytest.raises(RarfError, match="impact"):
        build(factory)


def test_a_partial_impact_analysis_is_an_error(factory):
    prepare_workspace(factory, rows_for(10, 0))
    with factory.kw["bind"].begin() as connection:
        connection.execute(text("DELETE FROM impact_analysis WHERE impact_category = 'network_activity'"))
    with pytest.raises(RarfError, match="impact"):
        build(factory)


def test_no_sessions_no_ids(factory):
    assert list_session_ids(factory) == []


def test_sections_do_not_share_list_objects(factory):
    prepare_workspace(factory, rows_for(10, 0))
    document = build(factory)
    assert document["detection"]["event_ids"] is not document["traceability"]["event_ids"]
    assert document["detection"]["event_ids"] == document["traceability"]["event_ids"]
