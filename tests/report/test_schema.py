"""Unit tests for the report validator. The good report comes from a small synthetic workspace."""

import copy

import pytest

from raven.report.generator import generate_report
from raven.report.schema import SECTION_IDS, validate_report


@pytest.fixture
def good(rarf):
    return generate_report(rarf, attack_session_id=3)


def problems(good, rarf, mutate):
    report = copy.deepcopy(good)
    mutate(report)
    return validate_report(report, rarf)


def section(report, section_id):
    return next(s for s in report["sections"] if s["section_id"] == section_id)


def test_a_generated_report_is_valid(good, rarf):
    assert validate_report(good, rarf) == []


def test_not_an_object():
    assert validate_report([]) == ["report must be an object"]


def test_top_level_keys_are_exact(good, rarf):
    assert any("missing generated_at" in p for p in problems(good, rarf, lambda r: r.pop("generated_at")))
    assert any("unexpected extra" in p for p in problems(good, rarf, lambda r: r.update(extra=1)))


@pytest.mark.parametrize(
    "mutate, fragment",
    [
        (lambda r: r.update(report_title=""), "report_title"),
        (lambda r: r.update(attack_session_id="1"), "attack_session_id"),
        (lambda r: r.update(session_id=""), "session_id must be a non-empty string"),
        (lambda r: r.update(generated_at=5), "generated_at"),
    ],
)
def test_header_problems(good, rarf, mutate, fragment):
    assert any(fragment in p for p in problems(good, rarf, mutate))


def test_a_generation_time_string_is_allowed(good, rarf):
    assert problems(good, rarf, lambda r: r.update(generated_at="2026-09-21T10:00:00Z")) == []


def test_sections_must_be_the_seven_in_order(good, rarf):
    assert any("sections must be" in p for p in problems(good, rarf, lambda r: r["sections"].reverse()))
    assert any("sections must be" in p for p in problems(good, rarf, lambda r: r["sections"].pop()))
    assert list(SECTION_IDS)[0] == "executive_summary" and len(SECTION_IDS) == 7


def test_a_section_title_is_fixed(good, rarf):
    assert any("the title must be" in p for p in problems(good, rarf, lambda r: r["sections"][0].update(title="Summary")))


def test_empty_findings_are_rejected(good, rarf):
    assert any("findings must be a non-empty list" in p for p in problems(good, rarf, lambda r: r["sections"][1].update(findings=[])))


@pytest.mark.parametrize(
    "mutate, fragment",
    [
        (lambda f: f.update(basis="maybe"), "basis must be observed or derived"),
        (lambda f: f.update(statement="  "), "non-empty string"),
        (lambda f: f.pop("evidence"), "needs exactly statement, basis and evidence"),
        (lambda f: f["evidence"].pop("raw_event_refs"), "evidence must have exactly"),
        (lambda f: f["evidence"].update(event_ids=[1]), "one raw event reference per event ID"),
    ],
)
def test_finding_problems(good, rarf, mutate, fragment):
    assert any(fragment in p for p in problems(good, rarf, lambda r: mutate(section(r, "executive_summary")["findings"][0])))


def test_forbidden_phrases_are_rejected_everywhere(good, rarf):
    def add(report):
        section(report, "timeline_summary")["findings"][0]["statement"] += " Real-time protection was active."

    assert any("forbidden wording: real-time protection" in p for p in problems(good, rarf, add))


def test_encryption_words_outside_the_limitations_are_rejected(good, rarf):
    def add(report):
        section(report, "executive_summary")["findings"][0]["statement"] += " Data may be encrypted."

    assert any("words about encryption may only appear in confidence_limitations" in p for p in problems(good, rarf, add))


@pytest.mark.parametrize("word", ["intent", "malware", "exfiltration", "encryption"])
def test_the_limitations_must_name_what_is_not_established(good, rarf, word):
    def remove(report):
        for finding in section(report, "confidence_limitations")["findings"]:
            finding["statement"] = finding["statement"].lower().replace(word, "x")

    assert any(f"must state that {word} is not established" in p for p in problems(good, rarf, remove))


def test_evidence_must_exist_in_the_rarf(good, rarf):
    def unknown_event(report):
        finding = section(report, "impact_analysis")["findings"][0]
        finding["evidence"]["event_ids"] = [10**6]
        finding["evidence"]["raw_event_refs"] = ["9:9"]

    def unknown_group(report):
        section(report, "detection_evidence")["findings"][0]["evidence"]["correlation_group_ids"] = ["nope"]

    def unknown_impact(report):
        section(report, "impact_analysis")["findings"][0]["evidence"]["impact_analysis_ids"] = [10**6]

    def wrong_ref(report):
        finding = section(report, "executive_summary")["findings"][0]
        finding["evidence"]["raw_event_refs"] = list(reversed(finding["evidence"]["raw_event_refs"]))

    assert any("events that are not in the RARF" in p for p in problems(good, rarf, unknown_event))
    assert any("correlation groups that are not in the RARF" in p for p in problems(good, rarf, unknown_group))
    assert any("impact analyses that are not in the RARF" in p for p in problems(good, rarf, unknown_impact))
    assert any("raw event references do not belong" in p for p in problems(good, rarf, wrong_ref))


def test_the_session_id_must_match_the_rarf(good, rarf):
    assert any("session ID of the RARF" in p for p in problems(good, rarf, lambda r: r.update(session_id="other")))
