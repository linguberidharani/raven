"""Unit tests for the report generator. The RARF documents come from small synthetic workspaces."""

import copy
import json

import pytest

from raven.rarf.schema import validate_rarf
from raven.report.generator import ReportError, generate_report, main, render_text, report_text
from raven.report.schema import (
    EVIDENCE_FIELDS,
    FORBIDDEN_PHRASES,
    SECTION_IDS,
    SECTION_TITLES,
    validate_report,
)


def findings_of(report, section_id):
    (section,) = [s for s in report["sections"] if s["section_id"] == section_id]
    return section["findings"]


def all_findings(report):
    return [f for s in report["sections"] for f in s["findings"]]


def statements(report, section_id):
    return [f["statement"] for f in findings_of(report, section_id)]


def test_the_report_has_the_structure_of_the_spec(rarf):
    report = generate_report(rarf, attack_session_id=7)
    assert list(report) == ["report_title", "attack_session_id", "session_id", "generated_at", "sections"]
    assert report["attack_session_id"] == 7
    assert report["session_id"] == rarf["attack_session"]["session_id"]
    assert report["report_title"] == "Investigation Report: " + report["session_id"]
    assert report["generated_at"] is None
    assert [s["section_id"] for s in report["sections"]] == list(SECTION_IDS)
    assert [s["title"] for s in report["sections"]] == [SECTION_TITLES[i] for i in SECTION_IDS]


def test_the_report_is_valid_against_its_rarf(rarf):
    report = generate_report(rarf)
    assert validate_report(report, rarf) == []
    assert validate_report(report) == []
    assert report["attack_session_id"] is None


def test_every_finding_has_a_basis_and_evidence_in_the_fixed_order(rarf):
    for finding in all_findings(generate_report(rarf)):
        assert list(finding) == ["statement", "basis", "evidence"]
        assert finding["basis"] in ("observed", "derived")
        assert list(finding["evidence"]) == list(EVIDENCE_FIELDS)
        assert len(finding["evidence"]["raw_event_refs"]) == len(finding["evidence"]["event_ids"])


def test_both_bases_are_used(rarf):
    bases = {f["basis"] for f in all_findings(generate_report(rarf))}
    assert bases == {"observed", "derived"}


def test_the_executive_summary_states_the_counts_of_the_rarf(rarf):
    text = " ".join(statements(generate_report(rarf), "executive_summary"))
    assert "Based on the available evidence, 11 recorded events from the computer Dharani" in text
    assert "between 2026-09-13T08:00:00.000Z and 2026-09-13T08:00:10.000Z (UTC)" in text
    assert "10 file creation events, 0 network connection events and 1 process creation event." in text
    assert "2 correlation groups from 2 rules (RAVEN-R001, RAVEN-R003)" in text
    assert "severity HIGH" in text
    assert "does not show the purpose of the activity" in text


def test_derived_and_observed_findings_of_the_executive_summary(rarf):
    findings = findings_of(generate_report(rarf), "executive_summary")
    assert [f["basis"] for f in findings] == ["observed", "observed", "derived", "derived"]


def test_the_session_overview(rarf):
    report = generate_report(rarf)
    text = statements(report, "session_overview")
    assert text[0] == f"Session ID: {rarf['attack_session']['session_id']}. Computer: Dharani."
    assert "The time between the first and the last recorded event is 10.000 s." in text
    assert "No confidence value is assigned to this session; RAVEN does not claim one." in text
    assert findings_of(report, "session_overview")[2]["basis"] == "derived"


def test_a_session_confidence_value_is_stated_when_present(rarf):
    changed = copy.deepcopy(rarf)
    changed["attack_session"]["confidence"] = 85
    text = statements(generate_report(changed), "session_overview")
    assert "The confidence value assigned to this session is 85." in text


def test_detection_evidence_describes_each_rule_and_its_groups(rarf):
    report = generate_report(rarf)
    text = statements(report, "detection_evidence")
    assert text[0].startswith("Rule RAVEN-R001 (Mass File Modification Burst, severity HIGH, rule confidence 85) matched 1 correlation group.")
    assert "at least 1 process creation event(s), then at least 5 file creation event(s) within 60 seconds" in text[0]
    assert "involve 1 different process ID(s) and 6 distinct recorded events" in text[1]
    assert text[2].startswith("Rule RAVEN-R003 (Sustained File Creation Burst")
    assert "at least 10 file creation event(s) within 120 seconds" in text[2]
    assert text[-1].startswith("In total 2 correlation groups contain 16 event entries, of which 11 are distinct recorded events.")
    first = findings_of(report, "detection_evidence")[0]
    assert first["basis"] == "derived" and len(first["evidence"]["correlation_group_ids"]) == 1
    assert len(first["evidence"]["event_ids"]) == 6


def test_the_timeline_summary(rarf):
    text = statements(generate_report(rarf), "timeline_summary")
    assert text[0] == "The timeline lists 11 events in time order, from 2026-09-13T08:00:00.000Z to 2026-09-13T08:00:10.000Z (UTC)."
    assert text[1] == "Recorded events per minute (UTC): 2026-09-13 08:00: 11."
    assert text[2] == "The busiest minute is 2026-09-13 08:00 with 11 recorded events."
    assert text[3].startswith("The first correlation group starts at 2026-09-13T08:00:00.000Z (RAVEN-R001:10:")
    assert text[4].startswith("The first process creation event of the timeline is at 2026-09-13T08:00:00.000Z (raw event reference 1:1);")
    assert len(text) == 5  # no network connection events in this session


def test_the_timeline_summary_mentions_network_events_when_there_are_some(rarf_with_network):
    text = statements(generate_report(rarf_with_network), "timeline_summary")
    assert any(t.startswith("The first network connection event of the timeline is at") for t in text)


def test_the_impact_analysis(rarf):
    report = generate_report(rarf)
    text = statements(report, "impact_analysis")
    assert text[0].startswith("File creation: 10 file creation event(s) cover 3 distinct file path(s) and were recorded for 1 distinct process image(s).")
    assert "Examples: " in text[0]
    assert text[1].startswith("Process creation: 1 process creation event(s) cover 1 distinct process image(s).")
    assert "No events of types that RAVEN does not interpret belong to this session." in text
    derived = findings_of(report, "impact_analysis")[-1]
    assert derived["basis"] == "derived"
    assert "It does not measure damage, and no monetary or business impact is calculated." in derived["statement"]
    assert "files 3, network destinations 0, process images 1, other event types 0" in derived["statement"]
    assert len(derived["evidence"]["impact_analysis_ids"]) == 4


def test_the_impact_analysis_with_network_events(rarf_with_network):
    text = statements(generate_report(rarf_with_network), "impact_analysis")
    network = [t for t in text if t.startswith("Network connection:")]
    assert network and "1 network connection event(s) cover 1 distinct destination(s) (address:port); protocols seen: tcp." in network[0]
    assert "10.0.0.1:443" in network[0]


def test_evidence_traceability(rarf):
    report = generate_report(rarf)
    text = statements(report, "evidence_traceability")
    assert text[0].startswith("This report rests on 11 event IDs, 11 raw event references, 2 correlation group IDs, 11 timeline event IDs and 4 impact analysis IDs")
    assert rarf["rarf_id"] in text[0]
    assert "identifies one record of the original Sysmon log file" in text[1]
    assert "names the rule, the process ID and the start time of the group" in text[2]
    whole = findings_of(report, "evidence_traceability")[0]["evidence"]
    assert len(whole["event_ids"]) == 11 and len(whole["impact_analysis_ids"]) == 4 and len(whole["correlation_group_ids"]) == 2


def test_confidence_and_limitations_always_state_what_is_not_established(rarf):
    text = " ".join(statements(generate_report(rarf), "confidence_limitations")).lower()
    for word in ("intent", "malware", "exfiltration", "complete encryption"):
        assert word in text
    assert "does not establish the intent of the activity" in text
    assert "also occur in normal system activity" in text
    assert "0 of them belong to this session" in text


def test_no_forbidden_wording_anywhere(rarf, rarf_with_network):
    for document in (rarf, rarf_with_network):
        text = report_text(generate_report(document)).lower()
        for phrase in FORBIDDEN_PHRASES:
            assert phrase not in text


def test_words_about_encryption_only_appear_in_the_limitations(rarf):
    report = generate_report(rarf)
    for section in report["sections"]:
        joined = " ".join(f["statement"].lower() for f in section["findings"])
        assert ("encrypt" in joined) == (section["section_id"] == "confidence_limitations")


def test_the_report_makes_no_claims_of_intent_or_harm(rarf):
    text = report_text(generate_report(rarf)).lower()
    for word in ("attacker", "malicious", "ransom", "stolen", "damage was", "compromised"):
        assert word not in text


def test_the_same_rarf_gives_a_byte_identical_report(rarf):
    first = report_text(generate_report(rarf, 1))
    second = report_text(generate_report(copy.deepcopy(rarf), 1))
    assert first == second
    assert first.encode("ascii") == second.encode("ascii") and "\r" not in first and first.endswith("}\n")


def test_a_rarf_that_went_through_json_gives_the_same_report(rarf):
    round_trip = json.loads(json.dumps(rarf))
    assert report_text(generate_report(rarf)) == report_text(generate_report(round_trip))


def test_the_generation_time_is_not_part_of_the_content(rarf):
    assert '"generated_at": null' in report_text(generate_report(rarf))


def test_an_invalid_rarf_is_refused(rarf):
    broken = copy.deepcopy(rarf)
    broken["traceability"]["event_ids"].pop()
    assert validate_rarf(broken) != []
    with pytest.raises(ReportError, match="RARF document is not valid"):
        generate_report(broken)


def test_the_plain_text_rendering_labels_every_finding(rarf):
    report = generate_report(rarf)
    text = render_text(report)
    assert text.startswith(report["report_title"])
    assert text.count("[OBSERVED]") + text.count("[DERIVED]") == len(all_findings(report))
    for section in report["sections"]:
        assert f"== {section['title']} ==" in text


def test_main_writes_the_report_and_prints_the_counts(rarf, tmp_path, capsys):
    source = tmp_path / "RARF-x.json"
    source.write_text(json.dumps(rarf), encoding="utf-8")
    assert main([str(source), str(tmp_path / "out"), "--print"]) == 0
    printed = capsys.readouterr().out
    path = tmp_path / "out" / f"REPORT-{rarf['attack_session']['session_id']}.json"
    assert path.is_file()
    assert "  validation: valid" in printed and "  generated_at: None" in printed
    assert "  sections: 7, findings:" in printed
    assert "  observed findings:" in printed and "  derived findings:" in printed
    assert "== Confidence and limitations ==" in printed
    assert json.loads(path.read_text(encoding="utf-8"))["session_id"] == rarf["attack_session"]["session_id"]


def test_main_twice_gives_identical_files(rarf, tmp_path):
    source = tmp_path / "RARF-x.json"
    source.write_text(json.dumps(rarf), encoding="utf-8")
    main([str(source), str(tmp_path / "a")])
    main([str(source), str(tmp_path / "b")])
    name = f"REPORT-{rarf['attack_session']['session_id']}.json"
    assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()


def test_main_reports_errors(tmp_path, capsys):
    assert main([str(tmp_path / "missing.json"), str(tmp_path / "out")]) == 1
    assert "ERROR" in capsys.readouterr().err
    bad = tmp_path / "bad.json"
    bad.write_text('{"not": "a rarf"}', encoding="utf-8")
    assert main([str(bad), str(tmp_path / "out")]) == 1
