"""Unit tests for the RARF validator. The good document comes from a small synthetic workspace."""

import copy

import pytest

from raven.rarf.builder import build_rarf, list_session_ids
from raven.rarf.schema import RARF_VERSION, validate_rarf

from tests.rarf.conftest import prepare_workspace, rows_for


@pytest.fixture
def good(factory):
    prepare_workspace(factory, rows_for(10, 0))
    (session_id,) = list_session_ids(factory)
    return build_rarf(factory, session_id)


def broken(good, mutate):
    document = copy.deepcopy(good)
    mutate(document)
    return validate_rarf(document)


def test_a_built_document_is_valid(good):
    assert validate_rarf(good) == []
    assert RARF_VERSION == "1.0"


def test_not_an_object():
    assert validate_rarf([]) == ["rarf must be an object"]


def test_top_level_keys_are_exact(good):
    assert any("missing traceability" in p for p in broken(good, lambda d: d.pop("traceability")))
    assert any("unexpected extra" in p for p in broken(good, lambda d: d.update(extra=1)))


def test_version_and_id(good):
    assert "rarf_version must be 1.0" in broken(good, lambda d: d.update(rarf_version="2.0"))
    assert "rarf_id must be RARF- followed by the session ID" in broken(good, lambda d: d.update(rarf_id="RARF-other"))


@pytest.mark.parametrize(
    "mutate, fragment",
    [
        (lambda d: d["attack_session"].update(severity="CRITICAL"), "attack_session.severity"),
        (lambda d: d["attack_session"].update(confidence=101), "attack_session.confidence"),
        (lambda d: d["attack_session"].update(confidence="high"), "attack_session.confidence"),
        (lambda d: d["attack_session"].update(computer=""), "attack_session.computer"),
        (lambda d: d["attack_session"].pop("description"), "attack_session: missing description"),
    ],
)
def test_attack_session_problems(good, mutate, fragment):
    assert any(fragment in p for p in broken(good, mutate))


def test_a_confidence_value_is_allowed_when_it_is_a_whole_number(good):
    assert broken(good, lambda d: d["attack_session"].update(confidence=85)) == []


@pytest.mark.parametrize(
    "mutate, fragment",
    [
        (lambda d: d["detection"]["correlation_groups"][0].update(event_ids=[]), "event_ids must be a non-empty list"),
        (lambda d: d["detection"]["correlation_groups"][0].update(event_ids=[10**6]), "not in detection.event_ids"),
        (lambda d: d["detection"]["correlation_groups"][0].update(correlation_type="RAVEN-R999"), "not one of the listed rules"),
        (lambda d: d["detection"]["rules"][0].pop("enabled"), "needs rule_database_id"),
        (lambda d: d["detection"]["rules"][0].update(rule_definition={}), "rule_definition must be an object with a rule_id"),
        (lambda d: d["detection"].update(event_ids=list(reversed(d["detection"]["event_ids"]))), "sorted list"),
    ],
)
def test_detection_problems(good, mutate, fragment):
    assert any(fragment in p for p in broken(good, mutate))


@pytest.mark.parametrize(
    "mutate, fragment",
    [
        (lambda d: d["timeline"]["events"][3].update(sequence_number=99), "wrong value"),
        (lambda d: d["timeline"]["events"][0].update(user=5), "wrong value"),
        (lambda d: d["timeline"]["events"][0].pop("raw_event_ref"), "missing raw_event_ref"),
        (lambda d: d["timeline"]["events"].reverse(), "wrong value"),
    ],
)
def test_timeline_problems(good, mutate, fragment):
    assert any(fragment in p for p in broken(good, mutate))


def test_a_timeline_out_of_time_order_is_reported(good):
    def swap(document):
        events = document["timeline"]["events"]
        events[0]["timestamp"], events[-1]["timestamp"] = events[-1]["timestamp"], events[0]["timestamp"]

    assert "timeline.events must be in timestamp order" in broken(good, swap)


@pytest.mark.parametrize(
    "mutate, fragment",
    [
        (lambda d: d["impact"]["categories"]["files_affected"].update(impact_score=99), "impact_score must equal"),
        (lambda d: d["impact"]["categories"]["files_affected"]["analysis"].update(event_count=1), "event_count must equal"),
        (lambda d: d["impact"]["categories"].pop("network_activity"), "impact.categories must be"),
        (lambda d: d["impact"]["categories"]["files_affected"].pop("analysis"), "missing analysis"),
    ],
)
def test_impact_problems(good, mutate, fragment):
    assert any(fragment in p for p in broken(good, mutate))


@pytest.mark.parametrize(
    "mutate, fragment",
    [
        (lambda d: d["traceability"]["event_ids"].__setitem__(-1, d["traceability"]["event_ids"][-1] + 10**6), "traceability.event_ids must equal detection.event_ids"),
        (lambda d: d["traceability"]["raw_event_refs"].pop(), "one reference per event ID"),
        (lambda d: d["traceability"]["correlation_group_ids"].pop(), "correlation_group_ids must list"),
        (lambda d: d["traceability"]["timeline_event_ids"].pop(), "timeline_event_ids"),
        (lambda d: d["traceability"]["impact_analysis_ids"].pop(), "impact_analysis_ids"),
        (lambda d: d["traceability"].pop("event_ids"), "missing event_ids"),
    ],
)
def test_traceability_problems(good, mutate, fragment):
    assert any(fragment in p for p in broken(good, mutate))


def test_the_timeline_must_hold_exactly_the_events_of_the_detection(good):
    def drop_last(document):
        document["timeline"]["events"].pop()

    assert any("timeline" in p for p in broken(good, drop_last))
