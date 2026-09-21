"""S13 acceptance on the reference EVTX (spec sections 6.5b, 8 and 12): after uploading the reference file and running
the analysis through the API, every read endpoint answers with the reference numbers.

The reference file is real telemetry and is never committed (*.evtx is ignored). Put it at
tests/fixtures/sysmon_export.evtx to run this test; without it the test is skipped.
Everything is written to a temporary directory, never to the real data folder.
"""

import json
from pathlib import Path

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from raven.api.main import create_app
from raven.rarf.schema import validate_rarf
from raven.report.schema import validate_report
from tests.api.conftest import FAST_HASHER, make_investigation, make_settings, register_and_login

pytestmark = pytest.mark.slow

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sysmon_export.evtx"
REFERENCE_SIZE = 3_215_360
SESSION = "RAVEN-SESSION-Dharani-RAVEN-R003-4-2026-09-13T08-39-49-545Z"
EXAMPLE_GROUP = "RAVEN-R001:1224:2026-09-13T08:39:49.695Z"


@pytest.fixture(scope="module")
def read():
    """A function (path) -> parsed JSON, for a signed-in client on an analysed reference investigation."""
    import tempfile

    if not FIXTURE.is_file():
        pytest.skip(f"reference file not present: {FIXTURE}")
    if FIXTURE.stat().st_size != REFERENCE_SIZE:
        pytest.skip(f"{FIXTURE.name} is not the {REFERENCE_SIZE}-byte reference file")
    with tempfile.TemporaryDirectory() as directory:
        settings = make_settings(Path(directory))
        app = create_app(settings, PasswordHasher(**FAST_HASHER))
        try:
            with TestClient(app) as client:
                register_and_login(client)
                investigation = make_investigation(client, "Reference data", host="Dharani")
                base = f"/api/investigations/{investigation['id']}"
                assert client.post(base + "/evidence", files={"file": ("sysmon_export.evtx", FIXTURE.read_bytes(), "application/octet-stream")}).status_code == 201
                started = client.post(base + "/analysis")
                assert started.status_code == 202
                assert app.state.runs.wait(started.json()["id"], 600), "the analysis run did not finish"
                assert client.get(base + "/analysis").json()["status"] == "completed"

                def get(path, **params):
                    response = client.get(path if path.startswith("/api") else base + "/" + path, params=params)
                    assert response.status_code == 200, (path, response.text[:300])
                    return response.json()

                yield get
        finally:
            app.state.registry_factory.kw["bind"].dispose()


def test_the_detections_have_the_reference_numbers(read):
    body = read("detections", page_size=200)
    assert body["total"] == 87 and body["counts"]["total_groups"] == 87
    assert body["counts"]["by_rule"] == {"RAVEN-R001": 19, "RAVEN-R002": 14, "RAVEN-R003": 54}
    assert body["counts"]["by_severity"] == {"HIGH": 73, "MEDIUM": 14}
    assert [(r["rule_id"], r["groups"]) for r in body["rules"]] == [("RAVEN-R001", 19), ("RAVEN-R002", 14), ("RAVEN-R003", 54)]
    groups = {g["group_id"]: g for g in body["groups"]}
    assert len(groups) == 87 and body["groups"][0]["group_id"] == "RAVEN-R003:4:2026-09-13T08:39:49.545Z"
    example = groups[EXAMPLE_GROUP]
    assert (example["event_count"], example["match_value"], example["evidence"]["raw_event_refs"][0]) == (6, "1224", "1:1543")
    assert example["why"]["steps"] == [{"event_type": "process_creation", "required": 1, "found": 1}, {"event_type": "file_create", "required": 5, "found": 5}]
    assert [g["window_start"] for g in body["groups"]] == sorted(g["window_start"] for g in body["groups"])


def test_the_detections_can_be_filtered_and_paged(read):
    assert read("detections", rule="RAVEN-R002")["total"] == 14
    assert read("detections", severity="MEDIUM")["total"] == 14 and read("detections", severity="HIGH")["total"] == 73
    pages = [read("detections", page=n, page_size=20) for n in range(1, 6)]
    assert [len(p["groups"]) for p in pages] == [20, 20, 20, 20, 7] and all(p["total"] == 87 for p in pages)
    assert len({g["group_id"] for p in pages for g in p["groups"]}) == 87


def test_the_reconstruction_has_the_session_the_chain_and_the_process_tree(read):
    (session,) = read("reconstruction")["sessions"]
    assert session["session_id"] == SESSION and session["computer"] == "Dharani"
    assert (session["start_time"], session["end_time"], session["duration_ms"]) == ("2026-09-13T08:39:49.545Z", "2026-09-13T08:43:09.488Z", 199943)
    assert (session["severity"], session["confidence"], session["group_count"]) == ("HIGH", None, 87)
    chain = session["chain"]
    assert len(chain) == 87 and [g["start_time"] for g in chain] == sorted(g["start_time"] for g in chain)
    assert sum(len(g["events"]) for g in chain) == 696 and all(len(g["events"]) == g["event_count"] for g in chain)
    tree = session["process_tree"]
    nodes = {n["process_guid"]: n for n in tree["nodes"]}
    assert len(nodes) == len(tree["nodes"]) and len([n for n in nodes.values() if n["in_session"]]) >= 25
    assert set(tree["roots"]) <= set(nodes) and all(not nodes[r]["parent_process_guid"] or nodes[r]["parent_process_guid"] not in nodes for r in tree["roots"])
    assert all(child in nodes for n in nodes.values() for child in n["child_guids"])
    chain_ids = {g["group_id"] for g in chain}
    assert all(set(n["group_ids"]) <= chain_ids for n in nodes.values())
    svchost = next(n for n in nodes.values() if n["process_id"] == 1224 and n["in_session"])
    assert svchost["image"].lower().endswith("svchost.exe") and EXAMPLE_GROUP in svchost["group_ids"] and svchost["parent_process_guid"]


def test_the_timeline_has_597_events(read):
    body = read("timeline", page_size=200)
    assert body["total"] == 597
    first = body["items"][0]
    assert (first["sequence_number"], first["raw_event_ref"], first["event_id"], first["timestamp"]) == (1, "1:1475", 1403, "2026-09-13T08:39:49.545Z")
    assert first["description"] == "File created: C:\\Windows\\Logs\\MeasuredBoot\\0000000007-0000000000.log by System (PID 4)"
    assert (read("timeline", event_type="file_create")["total"], read("timeline", event_type="network_connection")["total"], read("timeline", event_type="process_creation")["total"]) == (558, 14, 25)
    assert (read("timeline", rule="RAVEN-R001")["total"], read("timeline", rule="RAVEN-R002")["total"], read("timeline", rule="RAVEN-R003")["total"]) == (114, 42, 540)
    assert read("timeline", q="svchost")["total"] > 0
    ordered = [i["sequence_number"] for n in range(1, 4) for i in read("timeline", page=n, page_size=200)["items"]]
    assert ordered == list(range(1, 598))


def test_one_event_shows_the_normalized_raw_and_xml_data(read):
    body = read("events/1:1475")
    assert body["event"]["id"] == 1403 and body["event"]["event_type"] == "file_create" and body["event"]["file_path"] == "C:\\Windows\\Logs\\MeasuredBoot\\0000000007-0000000000.log"
    assert body["raw"]["record_id"] == 1475 and body["raw"]["event_id"] == 11 and "TargetFilename" in body["raw"]["event_data"]
    assert body["raw_xml"].startswith("<Event") and "Microsoft-Windows-Sysmon" in body["raw_xml"]
    assert body["timeline"]["sequence_number"] == 1 and any(g["rule_id"] == "RAVEN-R003" for g in body["groups"])
    process = read("events/1:1543")
    assert process["event"]["event_type"] == "process_creation" and process["event"]["process_id"] == 1224 and process["event"]["parent_process_guid"]
    assert any(g["group_id"] == EXAMPLE_GROUP for g in process["groups"])


def test_the_impact_has_the_reference_numbers(read):
    (session,) = read("impact")["sessions"]
    categories = {c["category"]: c for c in session["categories"]}
    assert {name: c["derived"]["impact_score"] for name, c in categories.items()} == {"files_affected": 475, "network_activity": 12, "process_activity": 14, "unsupported_events": 0}
    assert {name: c["observed"]["event_count"] for name, c in categories.items()} == {"files_affected": 558, "network_activity": 14, "process_activity": 25, "unsupported_events": 0}
    assert all(len(c["observed"]["top_assets"]) <= 5 for c in categories.values())
    assert len(categories["files_affected"]["observed"]["affected_assets"]) == 475 and len(categories["files_affected"]["evidence"]["raw_event_refs"]) == 558
    assert set(categories["network_activity"]["observed"]["details"]["protocols_seen"]) <= {"tcp", "udp"}
    assert session["activity"]["bucket_seconds"] == 10 and sum(b["total"] for b in session["activity"]["buckets"]) == 597


def test_the_rarf_and_the_report_are_valid_and_complete(read):
    rarf = read("rarf")
    assert validate_rarf(rarf) == []
    trace = rarf["traceability"]
    assert (len(trace["event_ids"]), len(trace["raw_event_refs"]), len(trace["correlation_group_ids"]), len(trace["timeline_event_ids"]), len(trace["impact_analysis_ids"])) == (597, 597, 87, 597, 4)
    report = read("report")
    assert report["generated_at"].endswith("Z") and report["attack_session_id"] == 1
    assert validate_report(report, rarf) == [] and sum(len(s["findings"]) for s in report["sections"]) == 37


def test_the_rules_and_the_dashboard(read):
    assert [r["rule_id"] for r in read("/api/rules")["rules"]] == ["RAVEN-R001", "RAVEN-R002", "RAVEN-R003"]
    dashboard = read("/api/dashboard")
    assert dashboard["totals"] == {"investigations": 1, "active_investigations": 0, "open_cases": 1, "evidence_items": 1, "sessions": 1, "high_severity_findings": 73}
    assert dashboard["findings_by_severity"] == {"HIGH": 73, "MEDIUM": 14, "LOW": 0, "INFO": 0}
    assert dashboard["cases_by_severity"]["HIGH"] == 1 and dashboard["evidence_by_status"]["ready"] == 1
    assert len(dashboard["alerts"]) == 5 and all(a["severity"] == "HIGH" for a in dashboard["alerts"])
    latest = dashboard["latest_session"]
    assert latest["session_id"] == SESSION and latest["chain"][0]["rule_id"] == "RAVEN-R003" and {c["rule_id"] for c in latest["chain"]} == {"RAVEN-R001", "RAVEN-R002", "RAVEN-R003"}
    assert sum(c["groups"] for c in latest["chain"]) == 87
