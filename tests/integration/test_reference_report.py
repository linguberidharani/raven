"""S10 acceptance on the reference EVTX (spec sections 6.5b, 6.11 and 12): the report generated from the RARF of
the one attack session is valid against that RARF, uses the reference numbers in its statements, and the same
RARF gives a byte-identical report twice.

The database with the correlation groups comes from the shared fixture in conftest.py (reference file needed,
otherwise these tests are skipped). Everything is written to temporary directories.
"""

import json

import pytest

from raven.database.session import open_workspace_database
from raven.impact.persist import run_impact
from raven.rarf.builder import build_rarf, list_session_ids
from raven.rarf.exporter import export_rarf
from raven.reconstruction.persist import run_reconstruction
from raven.report.generator import generate_report, report_text
from raven.report.schema import FORBIDDEN_PHRASES, SECTION_IDS, validate_report
from raven.timeline.persist import run_timeline

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def generated(reference_db, tmp_path_factory):
    directory = tmp_path_factory.mktemp("reference_s10")
    factory = open_workspace_database(reference_db)
    try:
        run_reconstruction(factory, None)
        run_timeline(factory)
        run_impact(factory)
        (item,) = export_rarf(factory, directory / "rarf")
        rarf = json.loads(item.path.read_text(encoding="utf-8"))
        rebuilt = build_rarf(factory, list_session_ids(factory)[0])
    finally:
        factory.kw["bind"].dispose()
    first = generate_report(rarf, attack_session_id=1)
    second = generate_report(json.loads(item.path.read_text(encoding="utf-8")), attack_session_id=1)
    return {"rarf": rarf, "rebuilt": rebuilt, "first": first, "second": second}


def statements(report, section_id):
    (section,) = [s for s in report["sections"] if s["section_id"] == section_id]
    return [f["statement"] for f in section["findings"]]


def test_the_report_is_valid_against_its_rarf(generated):
    report = generated["first"]
    assert validate_report(report, generated["rarf"]) == []
    assert [s["section_id"] for s in report["sections"]] == list(SECTION_IDS)
    assert report["generated_at"] is None and report["attack_session_id"] == 1


def test_the_same_rarf_gives_a_byte_identical_report(generated):
    assert report_text(generated["first"]) == report_text(generated["second"])
    assert generated["rebuilt"] == generated["rarf"]
    assert report_text(generate_report(generated["rebuilt"], 1)) == report_text(generated["first"])


def test_statements_use_the_reference_numbers(generated):
    report = generated["first"]
    summary = " ".join(statements(report, "executive_summary"))
    assert "597 recorded events from the computer Dharani" in summary
    assert "558 file creation events, 14 network connection events and 25 process creation events." in summary
    assert "87 correlation groups from 3 rules (RAVEN-R001, RAVEN-R002, RAVEN-R003)" in summary
    detection = statements(report, "detection_evidence")
    assert detection[0].startswith("Rule RAVEN-R001 (Mass File Modification Burst, severity HIGH, rule confidence 85) matched 19 correlation groups.")
    assert any(t.startswith("Rule RAVEN-R002") and "matched 14 correlation groups" in t for t in detection)
    assert any(t.startswith("Rule RAVEN-R003") and "matched 54 correlation groups" in t for t in detection)
    assert "In total 87 correlation groups contain 696 event entries, of which 597 are distinct recorded events." in detection[-1]
    impact = " ".join(statements(report, "impact_analysis"))
    assert "558 file creation event(s) cover 475 distinct file path(s)" in impact
    assert "14 network connection event(s) cover 12 distinct destination(s)" in impact
    assert "25 process creation event(s) cover 14 distinct process image(s)" in impact
    assert "files 475, network destinations 12, process images 14, other event types 0" in impact


def test_the_wording_rules_hold_on_the_reference_report(generated):
    text = report_text(generated["first"]).lower()
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in text
    for word in ("attacker", "malicious", "ransom", "stolen", "compromised"):
        assert word not in text
    limitations = " ".join(statements(generated["first"], "confidence_limitations")).lower()
    for word in ("intent", "malware", "exfiltration", "complete encryption", "normal system activity"):
        assert word in limitations


def test_every_finding_is_labelled_and_linked(generated):
    findings = [f for s in generated["first"]["sections"] for f in s["findings"]]
    assert {f["basis"] for f in findings} == {"observed", "derived"}
    linked = [f for f in findings if f["evidence"]["event_ids"]]
    assert len(linked) >= len(findings) // 2
    whole = next(f for f in findings if f["statement"].startswith("This report rests on"))
    assert len(whole["evidence"]["event_ids"]) == 597 and len(whole["evidence"]["correlation_group_ids"]) == 87
