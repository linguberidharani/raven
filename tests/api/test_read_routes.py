"""API tests: the read endpoints on a SYNTHETIC analysed investigation (a fake loader replaces the EVTX reader)."""

import json

import pytest
from fastapi.testclient import TestClient

from raven.rarf.schema import validate_rarf
from raven.report.schema import validate_report
from tests.api.conftest import analysed_case, make_investigation, register_and_login, upload_evtx

SESSION = "RAVEN-SESSION-SYNTHETIC-LAB-HOST-RAVEN-R001-1001-2026-09-13T09-00-00-500Z"
R001_GROUP = "RAVEN-R001:1001:2026-09-13T09:00:00.500Z"
R003_GROUP = "RAVEN-R003:1001:2026-09-13T09:00:01.500Z"
PARENT_GUID = "{00000000-0000-0000-0000-000000000001}"
PROCESS_GUID = "{00000000-0000-0000-0000-000000001001}"

PER_INVESTIGATION = ["detections", "reconstruction", "timeline", "events/1:1", "impact", "rarf", "report"]


@pytest.fixture
def signed_in(client):
    register_and_login(client)
    return client


@pytest.fixture
def case(app, signed_in):
    return analysed_case(app, signed_in)


def get(client, case, path, **params):
    return client.get(f"/api/investigations/{case['id']}/{path}", params=params)


# ---------------------------------------------------------------- access


@pytest.mark.parametrize("path", ["/api/dashboard", "/api/rules"] + [f"/api/investigations/1/{p}" for p in PER_INVESTIGATION])
def test_every_read_route_needs_a_signed_in_user(client, path):
    response = client.get(path)
    assert response.status_code == 401 and response.json()["code"] == "not_authenticated"


@pytest.mark.parametrize("path", PER_INVESTIGATION)
def test_an_unknown_investigation_is_not_found(signed_in, path):
    response = signed_in.get(f"/api/investigations/999/{path}")
    assert response.status_code == 404 and response.json()["code"] == "investigation_not_found"


@pytest.mark.parametrize("path", PER_INVESTIGATION)
def test_investigation_ids_in_paths_are_validated(signed_in, path):
    assert signed_in.get(f"/api/investigations/0/{path}").status_code == 422
    assert signed_in.get(f"/api/investigations/abc/{path}").status_code == 422


def test_reading_does_not_cache(signed_in, case):
    for path in ("/api/dashboard", "/api/rules", f"/api/investigations/{case['id']}/detections", f"/api/investigations/{case['id']}/rarf"):
        assert signed_in.get(path).headers["Cache-Control"] == "no-store"


# ---------------------------------------------------------------- before an analysis


def test_before_an_analysis_the_lists_are_empty_and_the_files_are_not_there(signed_in):
    fresh = make_investigation(signed_in, "Fresh")
    assert get(signed_in, fresh, "detections").json() == {
        "analysed": False, "rules": [], "counts": {"total_groups": 0, "by_rule": {}, "by_severity": {}}, "groups": [], "total": 0, "page": 1, "page_size": 50}
    assert get(signed_in, fresh, "reconstruction").json() == {"sessions": []}
    assert get(signed_in, fresh, "timeline").json() == {"items": [], "total": 0, "page": 1, "page_size": 100}
    assert get(signed_in, fresh, "impact").json() == {"sessions": []}
    for path in ("rarf", "report"):
        response = get(signed_in, fresh, path)
        assert response.status_code == 404 and response.json()["code"] == "not_analysed"
    assert get(signed_in, fresh, "events/1:1").status_code == 404


# ---------------------------------------------------------------- detections


def test_detections_list_rules_and_groups(signed_in, case):
    body = get(signed_in, case, "detections").json()
    assert body["analysed"] is True and (body["total"], body["page"], body["page_size"]) == (2, 1, 50)
    assert [(r["rule_id"], r["groups"]) for r in body["rules"]] == [("RAVEN-R001", 1), ("RAVEN-R002", 0), ("RAVEN-R003", 1)]
    assert body["counts"] == {"total_groups": 2, "by_rule": {"RAVEN-R001": 1, "RAVEN-R003": 1}, "by_severity": {"HIGH": 2}}
    first, second = body["groups"]
    assert (first["group_id"], second["group_id"]) == (R001_GROUP, R003_GROUP)
    assert (first["rule_name"], first["severity"], first["confidence"], first["match_key"], first["match_value"], first["time_window_seconds"]) == (
        "Mass File Modification Burst", "HIGH", 85, "process_id", "1001", 60)
    assert (first["window_start"], first["window_end"], first["event_count"]) == ("2026-09-13T09:00:00.500Z", "2026-09-13T09:00:05.500Z", 6)


def test_a_group_says_why_it_matched_and_links_its_evidence(signed_in, case):
    group = get(signed_in, case, "detections").json()["groups"][0]
    assert group["why"]["basis"] == "derived" and group["why"]["steps"] == [
        {"event_type": "process_creation", "required": 1, "found": 1}, {"event_type": "file_create", "required": 5, "found": 5}]
    assert "process ID 1001" in group["why"]["text"] and "RAVEN-R001" in group["why"]["text"] and "within 60 seconds" in group["why"]["text"]
    assert group["interpretation"]["basis"] == "derived" and "does not show the purpose" in group["interpretation"]["text"]
    assert len(group["evidence"]["event_ids"]) == len(group["evidence"]["raw_event_refs"]) == 6
    assert group["evidence"]["raw_event_refs"][0] == "1:1"


def test_detections_can_be_filtered_and_paged(signed_in, case):
    assert [g["group_id"] for g in get(signed_in, case, "detections", rule="RAVEN-R003").json()["groups"]] == [R003_GROUP]
    body = get(signed_in, case, "detections", severity="MEDIUM").json()
    assert body["groups"] == [] and body["total"] == 0 and body["counts"]["total_groups"] == 2 and len(body["rules"]) == 3
    assert get(signed_in, case, "detections", rule="RAVEN-R404").json()["total"] == 0
    first = get(signed_in, case, "detections", page_size=1).json()
    second = get(signed_in, case, "detections", page_size=1, page=2).json()
    assert [g["group_id"] for g in first["groups"]] == [R001_GROUP] and [g["group_id"] for g in second["groups"]] == [R003_GROUP]
    assert first["total"] == second["total"] == 2
    assert get(signed_in, case, "detections", page=5).json()["groups"] == []


@pytest.mark.parametrize("params", [{"severity": "CRITICAL"}, {"page": 0}, {"page_size": 0}, {"page_size": 201}, {"rule": "x" * 65}])
def test_detections_reject_bad_parameters(signed_in, case, params):
    assert get(signed_in, case, "detections", **params).status_code == 422


# ---------------------------------------------------------------- reconstruction


def test_the_reconstruction_shows_the_session_and_the_attack_chain(signed_in, case):
    (session,) = get(signed_in, case, "reconstruction").json()["sessions"]
    assert session["session_id"] == SESSION and session["computer"] == "SYNTHETIC-LAB-HOST"
    assert (session["start_time"], session["end_time"], session["duration_ms"]) == ("2026-09-13T09:00:00.500Z", "2026-09-13T09:00:10.500Z", 10000)
    assert (session["severity"], session["confidence"], session["group_count"], session["rule_ids"]) == ("HIGH", None, 2, ["RAVEN-R001", "RAVEN-R003"])
    assert [g["group_id"] for g in session["chain"]] == [R001_GROUP, R003_GROUP]
    first = session["chain"][0]
    assert (first["event_count"], first["match_value"], len(first["events"])) == (6, "1001", 6)
    assert first["events"][0]["description"].startswith("Process created: C:\\Test\\synthetic1.exe (PID 1001)")
    assert first["events"][1]["event_type"] == "file_create" and first["interpretation"]["basis"] == "derived"


def test_the_process_tree_comes_from_the_process_guids(signed_in, case):
    (session,) = get(signed_in, case, "reconstruction").json()["sessions"]
    tree = session["process_tree"]
    nodes = {n["process_guid"]: n for n in tree["nodes"]}
    assert set(nodes) == {PROCESS_GUID, PARENT_GUID} and tree["roots"] == [PARENT_GUID]
    child, parent = nodes[PROCESS_GUID], nodes[PARENT_GUID]
    assert (child["process_id"], child["image"], child["parent_process_guid"], child["in_session"], child["basis"]) == (1001, "C:\\Test\\synthetic1.exe", PARENT_GUID, True, "observed")
    assert child["event_counts"] == {"process_creation": 1, "file_create": 10} and child["group_ids"] == [R001_GROUP, R003_GROUP]
    assert (parent["process_id"], parent["image"], parent["in_session"], parent["child_guids"], parent["first_seen"]) == (900, "C:\\Test\\parent.exe", False, [PROCESS_GUID], None)


# ---------------------------------------------------------------- timeline


def test_the_timeline_lists_the_events_in_order(signed_in, case):
    body = get(signed_in, case, "timeline").json()
    assert (body["total"], body["page"], body["page_size"]) == (11, 1, 100)
    items = body["items"]
    assert [i["sequence_number"] for i in items] == list(range(1, 12))
    first = items[0]
    assert (first["session_id"], first["event_type"], first["sysmon_event_id"], first["raw_event_ref"], first["basis"]) == (SESSION, "process_creation", 1, "1:1", "observed")
    assert first["description"].startswith("Process created:") and first["computer"] == "SYNTHETIC-LAB-HOST"
    assert first["groups"] == [{"group_id": R001_GROUP, "rule_id": "RAVEN-R001", "basis": "derived"}]
    both = [i for i in items if len(i["groups"]) == 2]
    assert len(both) == 5 and all({g["rule_id"] for g in i["groups"]} == {"RAVEN-R001", "RAVEN-R003"} for i in both)
    assert items[-1]["groups"] == [{"group_id": R003_GROUP, "rule_id": "RAVEN-R003", "basis": "derived"}]


def test_the_timeline_can_be_filtered(signed_in, case):
    assert get(signed_in, case, "timeline", event_type="file_create").json()["total"] == 10
    assert get(signed_in, case, "timeline", event_type="process_creation").json()["total"] == 1
    assert get(signed_in, case, "timeline", event_type="network_connection").json()["total"] == 0
    assert get(signed_in, case, "timeline", rule="RAVEN-R001").json()["total"] == 6
    assert get(signed_in, case, "timeline", rule="RAVEN-R003").json()["total"] == 10
    assert get(signed_in, case, "timeline", rule="RAVEN-R002").json()["total"] == 0
    found = get(signed_in, case, "timeline", q="FILE_003").json()
    assert found["total"] == 1 and found["items"][0]["description"].endswith("(PID 1001)") and "file_003" in found["items"][0]["description"]
    assert get(signed_in, case, "timeline", session=SESSION).json()["total"] == 11
    assert get(signed_in, case, "timeline", session="RAVEN-SESSION-nothing").json()["total"] == 0
    assert get(signed_in, case, "timeline", q="%").json()["total"] == 0
    assert get(signed_in, case, "timeline", event_type="file_create", rule="RAVEN-R001", q="file_00").json()["total"] == 5


def test_the_timeline_is_paged(signed_in, case):
    pages = [get(signed_in, case, "timeline", page=n, page_size=4).json() for n in (1, 2, 3, 4)]
    assert [len(p["items"]) for p in pages] == [4, 4, 3, 0] and all(p["total"] == 11 for p in pages)
    assert [i["sequence_number"] for p in pages for i in p["items"]] == list(range(1, 12))


@pytest.mark.parametrize("params", [{"event_type": "registry"}, {"page": 0}, {"page_size": 201}, {"q": "x" * 101}])
def test_the_timeline_rejects_bad_parameters(signed_in, case, params):
    assert get(signed_in, case, "timeline", **params).status_code == 422


# ---------------------------------------------------------------- one event


def test_an_event_shows_the_normalized_and_the_raw_data(signed_in, case):
    body = get(signed_in, case, "events/1:1").json()
    assert body["raw_event_ref"] == "1:1"
    assert len(body["event"]) == 28 and body["event"]["id"] == 1 and body["event"]["event_type"] == "process_creation"
    assert body["event"]["process_name"] == "C:\\Test\\synthetic1.exe" and body["event"]["hash_md5"] is None
    assert body["raw"]["record_id"] == 1 and body["raw"]["event_id"] == 1 and body["raw"]["event_data"]["Image"] == "C:\\Test\\synthetic1.exe"
    assert body["raw_xml"] == "<Event>1</Event>"
    assert body["groups"] == [{"group_id": R001_GROUP, "rule_id": "RAVEN-R001", "basis": "derived"}]
    assert body["timeline"] == {"session_id": SESSION, "sequence_number": 1, "description": body["timeline"]["description"]}
    assert body["timeline"]["description"].startswith("Process created:")


def test_an_event_can_be_found_by_a_reference_that_is_a_prefix_of_another(signed_in, case):
    for record_id in (2, 11):
        body = get(signed_in, case, f"events/1:{record_id}").json()
        assert body["raw"]["record_id"] == record_id and body["event"]["raw_event_ref"] == f"1:{record_id}"


@pytest.mark.parametrize("ref", ["1:999", "2:1", "9:9"])
def test_an_unknown_event_is_not_found(signed_in, case, ref):
    response = get(signed_in, case, f"events/{ref}")
    assert response.status_code == 404 and response.json()["code"] == "event_not_found"


@pytest.mark.parametrize("ref", ["abc", "1", "1:", ":1", "1:2:3", "1:a", "%2E%2E"])
def test_a_malformed_event_reference_is_refused(signed_in, case, ref):
    assert get(signed_in, case, f"events/{ref}").status_code in (404, 422)
    assert get(signed_in, case, f"events/{ref}").status_code != 200


def test_an_event_of_another_investigation_is_not_reachable(app, signed_in, case):
    other = analysed_case(app, signed_in, "Other case")
    assert get(signed_in, other, "events/2:1").status_code == 200
    assert get(signed_in, case, "events/2:1").status_code == 404
    assert get(signed_in, other, "events/1:1").status_code == 404


def test_a_missing_raw_record_is_reported(signed_in, case, settings):
    (settings.resolved_data_dir / "investigations" / str(case["id"]) / "raw" / "evidence-1.jsonl").unlink()
    response = get(signed_in, case, "events/1:1")
    assert response.status_code == 404 and response.json()["code"] == "raw_record_not_found"


# ---------------------------------------------------------------- impact


def test_the_impact_separates_observed_counts_from_the_derived_score(signed_in, case):
    (session,) = get(signed_in, case, "impact").json()["sessions"]
    assert session["session_id"] == SESSION
    categories = {c["category"]: c for c in session["categories"]}
    assert [c["category"] for c in session["categories"]] == ["files_affected", "network_activity", "process_activity", "unsupported_events"]
    files = categories["files_affected"]
    assert files["observed"]["basis"] == "observed" and files["observed"]["event_count"] == 10 and len(files["observed"]["affected_assets"]) == 10
    assert files["derived"]["basis"] == "derived" and files["derived"]["impact_score"] == 10 and "does not measure damage" in files["derived"]["definition"]
    assert len(files["observed"]["top_assets"]) == 5 and files["observed"]["top_assets"][0]["events"] == 1
    assert len(files["evidence"]["event_ids"]) == len(files["evidence"]["raw_event_refs"]) == 10
    assert (categories["process_activity"]["derived"]["impact_score"], categories["process_activity"]["observed"]["affected_assets"]) == (1, ["C:\\Test\\synthetic1.exe"])
    assert categories["network_activity"]["derived"]["impact_score"] == 0 and categories["unsupported_events"]["observed"]["event_count"] == 0


def test_the_activity_over_time_counts_every_event_once(signed_in, case):
    (session,) = get(signed_in, case, "impact").json()["sessions"]
    activity = session["activity"]
    assert activity["basis"] == "derived" and activity["bucket_seconds"] == 10
    buckets = activity["buckets"]
    assert sum(b["total"] for b in buckets) == 11 and sum(b["file_create"] for b in buckets) == 10 and sum(b["process_creation"] for b in buckets) == 1
    assert all(b["total"] == b["file_create"] + b["network_connection"] + b["process_creation"] for b in buckets)
    assert [b["start"] for b in buckets] == sorted(b["start"] for b in buckets)


# ---------------------------------------------------------------- RARF and report


def test_the_rarf_is_the_document_written_by_the_pipeline(signed_in, case, settings):
    response = get(signed_in, case, "rarf")
    assert response.status_code == 200 and validate_rarf(response.json()) == []
    path = settings.resolved_data_dir / "investigations" / str(case["id"]) / "processed" / "rarf" / f"RARF-{SESSION}.json"
    assert response.json() == json.loads(path.read_text(encoding="utf-8"))
    assert response.json()["attack_session"]["session_id"] == SESSION and len(response.json()["traceability"]["event_ids"]) == 11
    assert get(signed_in, case, "rarf", session=SESSION).json() == response.json()


def test_the_rarf_can_be_downloaded(signed_in, case):
    response = get(signed_in, case, "rarf", download="true")
    assert response.headers["Content-Disposition"] == f'attachment; filename="RARF-{SESSION}.json"'
    assert "Content-Disposition" not in get(signed_in, case, "rarf").headers


@pytest.mark.parametrize("path", ["rarf", "report"])
def test_an_unknown_session_is_not_found(signed_in, case, path):
    for name in ("RAVEN-SESSION-nothing", "../../registry", "*", "RARF-x"):
        response = get(signed_in, case, path, session=name)
        assert response.status_code == 404 and response.json()["code"] == "session_not_found"


def test_the_report_has_the_generation_time_and_nothing_else_changes(signed_in, case, settings):
    first = get(signed_in, case, "report").json()
    second = get(signed_in, case, "report").json()
    assert first["generated_at"].endswith("Z") and first["attack_session_id"] == 1 and first["session_id"] == SESSION
    assert {**first, "generated_at": None} == {**second, "generated_at": None}
    path = settings.resolved_data_dir / "investigations" / str(case["id"]) / "processed" / "report" / f"REPORT-{SESSION}.json"
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["generated_at"] is None and {**first, "generated_at": None} == stored
    assert validate_report(first, get(signed_in, case, "rarf").json()) == []


def test_missing_artifact_files_are_reported(signed_in, case, settings):
    root = settings.resolved_data_dir / "investigations" / str(case["id"]) / "processed"
    (root / "rarf" / f"RARF-{SESSION}.json").unlink()
    (root / "report" / f"REPORT-{SESSION}.json").unlink()
    assert get(signed_in, case, "rarf").json()["code"] == "rarf_not_found"
    assert get(signed_in, case, "report").json()["code"] == "report_not_found"


# ---------------------------------------------------------------- rules and dashboard


def test_the_shipped_rules(signed_in):
    body = signed_in.get("/api/rules").json()
    assert [r["rule_id"] for r in body["rules"]] == ["RAVEN-R001", "RAVEN-R002", "RAVEN-R003"]
    assert body["rules"][0]["steps"] == [{"event_type": "process_creation", "min_count": 1}, {"event_type": "file_create", "min_count": 5}]
    assert [(r["severity"], r["confidence"], r["time_window_seconds"]) for r in body["rules"]] == [("HIGH", 85, 60), ("MEDIUM", 75, 120), ("HIGH", 90, 120)]


def test_the_dashboard_of_an_empty_installation(signed_in):
    body = signed_in.get("/api/dashboard").json()
    assert body["totals"] == {"investigations": 0, "active_investigations": 0, "open_cases": 0, "evidence_items": 0, "sessions": 0, "high_severity_findings": 0}
    assert body["cases_by_severity"] == {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0, "none": 0}
    assert body["cases_by_status"] == {"open": 0, "active": 0, "closed": 0}
    assert (body["recent_investigations"], body["latest_session"], body["alerts"], body["recent_activity"], body["evidence_queue"]) == ([], None, [], [], [])


def test_the_dashboard_counts_real_records(app, signed_in, case):
    fresh = make_investigation(signed_in, "Waiting for evidence")
    assert upload_evtx(signed_in, fresh["id"], salt=99).status_code == 201
    body = signed_in.get("/api/dashboard").json()
    assert body["totals"] == {"investigations": 2, "active_investigations": 0, "open_cases": 2, "evidence_items": 2, "sessions": 1, "high_severity_findings": 2}
    assert body["cases_by_severity"] == {"HIGH": 1, "MEDIUM": 0, "LOW": 0, "INFO": 0, "none": 1}
    assert body["findings_by_severity"] == {"HIGH": 2, "MEDIUM": 0, "LOW": 0, "INFO": 0}
    assert body["evidence_by_status"] == {"uploaded": 1, "processing": 0, "ready": 1, "failed": 0}
    assert [i["id"] for i in body["recent_investigations"]] == [fresh["id"], case["id"]]
    assert body["latest_session"]["session_id"] == SESSION and [c["rule_id"] for c in body["latest_session"]["chain"]] == ["RAVEN-R001", "RAVEN-R003"]
    assert [a["group_id"] for a in body["alerts"]] == [R003_GROUP, R001_GROUP]
    assert [(q["filename"], q["status"], q["code"]) for q in body["evidence_queue"]] == [("Sysmon export.evtx", "uploaded", fresh["code"])]
    kinds = [a["kind"] for a in body["recent_activity"]]
    assert kinds.count("investigation_created") == 2 and kinds.count("evidence_uploaded") == 2 and kinds.count("analysis_completed") == 1
    assert [a["time"] for a in body["recent_activity"]] == sorted((a["time"] for a in body["recent_activity"]), reverse=True)


def test_the_dashboard_follows_the_status_of_a_case(signed_in, case):
    signed_in.patch(f"/api/investigations/{case['id']}", json={"status": "active"})
    body = signed_in.get("/api/dashboard").json()
    assert body["totals"]["active_investigations"] == 1 and body["totals"]["open_cases"] == 0
    assert body["cases_by_status"] == {"open": 0, "active": 1, "closed": 0}


def test_the_dashboard_shows_failed_evidence_in_the_queue(app, signed_in):
    from tests.synthetic import fake_loader

    investigation = make_investigation(signed_in)
    evidence = upload_evtx(signed_in, investigation["id"]).json()
    app.state.runs.loader = fake_loader(failing_ids=(evidence["id"],))
    signed_in.post(f"/api/investigations/{investigation['id']}/analysis")
    app.state.runs.wait(1, 60)
    body = signed_in.get("/api/dashboard").json()
    assert [(q["status"], "synthetic failure" in q["error"]) for q in body["evidence_queue"]] == [("failed", True)]
    assert body["evidence_by_status"]["failed"] == 1 and "analysis_failed" in [a["kind"] for a in body["recent_activity"]]


def test_two_investigations_never_show_each_others_data(app, signed_in, case):
    other = analysed_case(app, signed_in, "Other case")
    for target, expected_pid in ((case, "1001"), (other, "1002")):
        groups = get(signed_in, target, "detections").json()["groups"]
        assert {g["match_value"] for g in groups} == {expected_pid}
        assert {i["session_id"] for i in get(signed_in, target, "timeline").json()["items"]} != set()
    assert SESSION not in {i["session_id"] for i in get(signed_in, other, "timeline").json()["items"]}
    assert all(f"synthetic1.exe" not in i["description"] for i in get(signed_in, other, "timeline").json()["items"])


def test_reading_works_for_every_analyst(app, signed_in, case):
    with TestClient(app) as other:
        register_and_login(other, email="grace@example.com")
        assert other.get(f"/api/investigations/{case['id']}/detections").json()["total"] == 2
