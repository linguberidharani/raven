"""S12 acceptance on the reference EVTX (spec sections 6.5b, 8 and 12): uploading the reference file through the
API and running the analysis gives the same numbers as the stages S2 to S10 one by one, and the RARF file that the
run writes is byte-identical to the one of stage S9.

The reference file is real telemetry and is never committed (*.evtx is ignored). Put it at
tests/fixtures/sysmon_export.evtx to run this test; without it the test is skipped.
Everything is written to a temporary directory, never to the real data folder.
"""

import hashlib
import json
from pathlib import Path

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from raven.api.main import create_app
from raven.database.validate import validate_database
from tests.api.conftest import FAST_HASHER, make_investigation, make_settings, register_and_login

pytestmark = pytest.mark.slow

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sysmon_export.evtx"
REFERENCE_SIZE = 3_215_360
S9_RARF_SHA256 = "845724C83763D2B12B98247C64F67830DEF4BB0B9E3E8923C051B887E70B210B"


@pytest.fixture(scope="module")
def case(tmp_path_factory):
    if not FIXTURE.is_file():
        pytest.skip(f"reference file not present: {FIXTURE}")
    if FIXTURE.stat().st_size != REFERENCE_SIZE:
        pytest.skip(f"{FIXTURE.name} is not the {REFERENCE_SIZE}-byte reference file")
    directory = tmp_path_factory.mktemp("reference_s12")
    settings = make_settings(directory)
    app = create_app(settings, PasswordHasher(**FAST_HASHER))
    try:
        with TestClient(app) as client:
            register_and_login(client)
            investigation = make_investigation(client, "Reference data", host="Dharani")
            base = f"/api/investigations/{investigation['id']}"
            uploaded = client.post(base + "/evidence", files={"file": ("sysmon_export.evtx", FIXTURE.read_bytes(), "application/octet-stream")})
            duplicate = client.post(base + "/evidence", files={"file": ("again.evtx", FIXTURE.read_bytes(), "application/octet-stream")})

            def run_once():
                started = client.post(base + "/analysis")
                assert started.status_code == 202, started.text
                assert app.state.runs.wait(started.json()["id"], 600), "the analysis run did not finish"
                return client.get(base + "/analysis").json()

            first = run_once()
            workspace = settings.resolved_data_dir / "investigations" / str(investigation["id"])
            rarf_path = next((workspace / "processed" / "rarf").glob("RARF-*.json"))
            report_path = next((workspace / "processed" / "report").glob("REPORT-*.json"))
            first_files = (rarf_path.read_bytes(), report_path.read_bytes())
            header = client.get(base).json()
            evidence = client.get(base + "/evidence").json()
            second = run_once()
            second_files = (rarf_path.read_bytes(), report_path.read_bytes())
            validation = validate_database(str(workspace / "raven.db"))
    finally:
        app.state.registry_factory.kw["bind"].dispose()
    return {
        "uploaded": uploaded,
        "duplicate": duplicate,
        "first": first,
        "second": second,
        "header": header,
        "evidence": evidence,
        "first_files": first_files,
        "second_files": second_files,
        "validation": validation,
    }


def stage(run, name):
    return next(item["summary"] for item in run["stages"] if item["name"] == name)


def test_the_upload_is_stored_with_the_hash_of_the_file(case):
    body = case["uploaded"].json()
    assert case["uploaded"].status_code == 201
    assert body["sha256"] == hashlib.sha256(FIXTURE.read_bytes()).hexdigest().upper() and body["size_bytes"] == REFERENCE_SIZE
    assert case["duplicate"].status_code == 409 and case["duplicate"].json()["code"] == "duplicate_evidence"


def test_the_run_completes_with_every_stage(case):
    run = case["first"]
    assert run["status"] == "completed" and run["error"] is None and run["stage"] == "report"
    assert [s["status"] for s in run["stages"]] == ["completed"] * 10


def test_the_processing_numbers_are_those_of_s2_to_s5(case):
    run = case["first"]
    assert stage(run, "collect") == {"evidence": [{"evidence_id": 1, "records": 2816, "reused": False}], "records": 2816}
    normalize = stage(run, "normalize")
    assert normalize["events"] == 2816 and normalize["status_counts"] == {"OK": 1984, "UNSUPPORTED_EVENT_ID": 832}
    assert normalize["event_type_counts"] == {"file_create": 842, "network_connection": 212, "process_creation": 930, "unsupported": 832}
    assert stage(run, "deduplicate") == {"input": 2816, "unique": 2719, "removed": 97}
    assert stage(run, "ingest") == {"read": 2719, "inserted": 2719, "skipped_existing": 0}
    correlate = stage(run, "correlate")
    assert correlate["groups"] == 87 and correlate["groups_by_rule"] == {"RAVEN-R001": 19, "RAVEN-R002": 14, "RAVEN-R003": 54}
    assert correlate["distinct_events"] == 597
    assert correlate["distinct_events_by_type"] == {"file_create": 558, "network_connection": 14, "process_creation": 25}


def test_the_session_timeline_impact_rarf_and_report_numbers_are_those_of_s6_to_s10(case):
    run = case["first"]
    assert stage(run, "reconstruct") == {"sessions": 1, "groups": 87}
    assert stage(run, "timeline") == {"timeline_events": 597}
    (impact,) = stage(run, "impact")["sessions"]
    assert impact["scores"] == {"files_affected": 475, "network_activity": 12, "process_activity": 14, "unsupported_events": 0}
    assert impact["events"] == {"files_affected": 558, "network_activity": 14, "process_activity": 25, "unsupported_events": 0}
    rarf = stage(run, "rarf")
    assert len(rarf["files"]) == 1 and rarf["traceability"] == [
        {"event_ids": 597, "raw_event_refs": 597, "correlation_group_ids": 87, "timeline_event_ids": 597, "impact_analysis_ids": 4}
    ]
    report = stage(run, "report")
    assert len(report["files"]) == 1 and (report["observed_findings"], report["derived_findings"]) == (26, 11)


def test_the_rarf_file_is_byte_identical_to_the_one_of_stage_s9(case):
    assert hashlib.sha256(case["first_files"][0]).hexdigest().upper() == S9_RARF_SHA256


def test_the_report_file_names_the_attack_session(case):
    report = json.loads(case["first_files"][1].decode("ascii"))
    assert report["attack_session_id"] == 1 and report["generated_at"] is None
    assert sum(len(s["findings"]) for s in report["sections"]) == 37


def test_the_investigation_header_and_the_evidence_list_show_the_results(case):
    header = case["header"]
    assert (header["severity"], header["stage"], header["analysis_status"]) == ("HIGH", "report", "completed")
    assert header["counts"] == {"evidence": 1, "detections": 87, "sessions": 1, "timeline_events": 597}
    (item,) = case["evidence"]["items"]
    assert (item["status"], item["events_total"], item["error"]) == ("ready", 2816, None)
    breakdown = {(e["event_id"], e["event_type"]): e["count"] for e in case["evidence"]["event_breakdown"]}
    assert breakdown[(1, "process_creation")] == 930 and breakdown[(3, "network_connection")] == 212 and breakdown[(11, "file_create")] == 820
    unsupported = {key: count for key, count in breakdown.items() if key[1] == "unsupported"}
    assert sum(unsupported.values()) == 757 and {key[0] for key in unsupported} <= {4, 5, 16, 255}


def test_the_workspace_database_is_valid(case):
    result = case["validation"]
    assert result["problems"] == [] and result["row_counts"]["events"] == 2719
    assert result["events_by_status"] == {"OK": 1962, "UNSUPPORTED_EVENT_ID": 757}


def test_a_second_run_reuses_the_collected_file_and_changes_nothing(case):
    first, second = case["first"], case["second"]
    assert second["id"] != first["id"] and second["status"] == "completed"
    assert stage(second, "collect")["evidence"][0]["reused"] is True
    assert stage(second, "ingest") == {"read": 2719, "inserted": 0, "skipped_existing": 2719}
    for name in ("normalize", "deduplicate", "correlate", "reconstruct", "timeline", "impact", "rarf", "report"):
        assert stage(second, name) == stage(first, name), name
    assert case["second_files"] == case["first_files"]
