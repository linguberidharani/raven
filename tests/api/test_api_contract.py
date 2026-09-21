"""Contract tests: the API answers with exactly the shapes written in docs/api-contract.md.

Part 1 compares the key structure of real responses with the documented shapes. Part 2 checks that every endpoint of
the application is documented (and every documented endpoint exists).
"""

import re
from pathlib import Path

import pytest

from tests.api.conftest import analysed_case, register_and_login

DOC = Path(__file__).resolve().parents[2] / "docs" / "api-contract.md"
SESSION_KEYS = {
    "session_id", "computer", "start_time", "end_time", "duration_ms", "severity", "confidence", "description", "group_count", "rule_ids", "chain", "process_tree",
}


def shape(value):
    """The key structure of a JSON value: dictionaries by their keys, lists by their first element."""
    if isinstance(value, dict):
        return {key: shape(item) for key, item in value.items()}
    if isinstance(value, list):
        return [shape(value[0])] if value else []
    return None


INVESTIGATION = {
    "id": None, "code": None, "title": None, "description": None, "host": None, "status": None, "severity": None, "stage": None, "analysis_status": None,
    "analyst": {"id": None, "name": None}, "counts": {"evidence": None, "detections": None, "sessions": None, "timeline_events": None},
    "created_at": None, "updated_at": None,
}
EVIDENCE_REFS = {"event_ids": [None], "raw_event_refs": [None]}
GROUP = {
    "group_id": None, "rule_id": None, "rule_name": None, "severity": None, "confidence": None, "match_key": None, "match_value": None,
    "time_window_seconds": None, "window_start": None, "window_end": None, "event_count": None,
    "why": {"basis": None, "text": None, "steps": [{"event_type": None, "required": None, "found": None}]},
    "interpretation": {"basis": None, "text": None}, "evidence": EVIDENCE_REFS,
}
RULE = {
    "rule_id": None, "rule_name": None, "description": None, "severity": None, "confidence": None, "match_key": None, "time_window_seconds": None,
    "steps": [{"event_type": None, "min_count": None}], "enabled": None, "groups": None,
}
NODE = {
    "process_guid": None, "process_id": None, "image": None, "user": None, "parent_process_guid": None, "parent_process_id": None, "parent_image": None,
    "first_seen": None, "last_seen": None, "event_counts": {"process_creation": None}, "group_ids": [None], "in_session": None, "basis": None, "child_guids": [None],
}
CATEGORY = {
    "category": None, "impact_analysis_id": None,
    "observed": {"basis": None, "event_count": None, "affected_assets": [None], "top_assets": [{"asset": None, "events": None}], "details": {}},
    "derived": {"basis": None, "impact_score": None, "definition": None}, "evidence": EVIDENCE_REFS,
}


@pytest.fixture
def analysed(app, client):
    register_and_login(client)
    return analysed_case(app, client)


def test_the_dashboard_shape(client, analysed):
    body = client.get("/api/dashboard").json()
    body["recent_investigations"] = body["recent_investigations"][:1]
    body["evidence_queue"] = [{"id": 1, "investigation_id": 1, "code": "c", "filename": "f", "status": "s", "size_bytes": 1, "error": None, "created_at": "t"}]
    got = shape(body)
    assert set(got) == {
        "totals", "cases_by_severity", "cases_by_status", "findings_by_severity", "evidence_by_status", "recent_investigations", "latest_session",
        "alerts", "recent_activity", "evidence_queue",
    }
    assert set(got["totals"]) == {"investigations", "active_investigations", "open_cases", "evidence_items", "sessions", "high_severity_findings"}
    assert set(got["cases_by_severity"]) == {"HIGH", "MEDIUM", "LOW", "INFO", "none"} and set(got["cases_by_status"]) == {"open", "active", "closed"}
    assert set(got["findings_by_severity"]) == {"HIGH", "MEDIUM", "LOW", "INFO"} and set(got["evidence_by_status"]) == {"uploaded", "processing", "ready", "failed"}
    assert got["recent_investigations"] == [INVESTIGATION]
    assert set(got["latest_session"]) == {"investigation_id", "code", "session_id", "start_time", "end_time", "severity", "chain"}
    assert set(got["latest_session"]["chain"][0]) == {"rule_id", "rule_name", "severity", "groups", "first_start"}
    assert set(got["alerts"][0]) == {"investigation_id", "code", "group_id", "rule_id", "rule_name", "severity", "window_start", "event_count"}
    assert set(got["recent_activity"][0]) == {"time", "kind", "investigation_id", "code", "text"}
    assert set(got["evidence_queue"][0]) == {"id", "investigation_id", "code", "filename", "status", "size_bytes", "error", "created_at"}


def test_the_rules_shape(client):
    register_and_login(client)
    got = shape(client.get("/api/rules").json())
    assert got == {"rules": [{"rule_id": None, "rule_name": None, "description": None, "steps": [{"event_type": None, "min_count": None}], "match_key": None, "time_window_seconds": None, "severity": None, "confidence": None}]}


def test_the_detections_shape(client, analysed):
    got = shape(client.get(f"/api/investigations/{analysed['id']}/detections").json())
    assert set(got) == {"analysed", "rules", "counts", "groups", "total", "page", "page_size"}
    assert got["rules"] == [RULE] and got["groups"] == [GROUP]
    assert set(got["counts"]) == {"total_groups", "by_rule", "by_severity"}


def test_the_reconstruction_shape(client, analysed):
    got = shape(client.get(f"/api/investigations/{analysed['id']}/reconstruction").json())
    assert set(got) == {"sessions"}
    (session,) = got["sessions"]
    assert set(session) == SESSION_KEYS
    (chain,) = session["chain"]
    assert set(chain) == {"group_id", "rule_id", "rule_name", "severity", "match_value", "start_time", "end_time", "event_count", "events", "interpretation"}
    assert chain["events"] == [{"event_id": None, "raw_event_ref": None, "timestamp": None, "event_type": None, "description": None}]
    assert set(session["process_tree"]) == {"nodes", "roots"} and set(session["process_tree"]["nodes"][0]) == set(NODE)


def test_the_timeline_shape(client, analysed):
    got = shape(client.get(f"/api/investigations/{analysed['id']}/timeline").json())
    assert set(got) == {"items", "total", "page", "page_size"}
    assert set(got["items"][0]) == {
        "timeline_event_id", "session_id", "sequence_number", "timestamp", "description", "computer", "event_type", "event_id", "sysmon_event_id",
        "raw_event_ref", "basis", "groups",
    }
    assert got["items"][0]["groups"] == [{"group_id": None, "rule_id": None, "basis": None}]


def test_the_event_shape(client, analysed):
    got = shape(client.get(f"/api/investigations/{analysed['id']}/events/1:1").json())
    assert set(got) == {"raw_event_ref", "event", "raw", "raw_xml", "groups", "timeline"}
    assert set(got["raw"]) == {"event_id", "time_created", "computer", "record_id", "event_data"}
    assert set(got["timeline"]) == {"session_id", "sequence_number", "description"}
    assert set(got["event"]) == {
        "id", "raw_event_ref", "event_id", "event_type", "timestamp", "computer", "process_guid", "process_id", "process_name", "parent_process_guid",
        "parent_process_id", "parent_process_name", "command_line", "parent_command_line", "user", "integrity_level", "hash_sha256", "hash_md5",
        "hash_imphash", "hashes_raw", "ip_address", "port", "source_ip", "source_port", "protocol", "initiated", "file_path", "normalization_status",
    }


def test_the_impact_shape(client, analysed):
    got = shape(client.get(f"/api/investigations/{analysed['id']}/impact").json())
    assert set(got) == {"sessions"}
    (session,) = got["sessions"]
    assert set(session) == {"session_id", "categories", "activity"}
    assert set(session["categories"][0]) == set(CATEGORY) and session["categories"][0]["derived"] == CATEGORY["derived"]
    assert set(session["categories"][0]["observed"]) == set(CATEGORY["observed"])
    assert set(session["activity"]) == {"basis", "bucket_seconds", "buckets"}
    assert set(session["activity"]["buckets"][0]) == {"start", "file_create", "network_connection", "process_creation", "total"}


def test_the_rarf_and_report_shapes(client, analysed):
    rarf = client.get(f"/api/investigations/{analysed['id']}/rarf").json()
    assert list(rarf) == ["rarf_version", "rarf_id", "attack_session", "detection", "timeline", "impact", "traceability"]
    report = client.get(f"/api/investigations/{analysed['id']}/report").json()
    assert list(report) == ["report_title", "attack_session_id", "session_id", "generated_at", "sections"]
    assert [s["section_id"] for s in report["sections"]] == [
        "executive_summary", "session_overview", "detection_evidence", "timeline_summary", "impact_analysis", "evidence_traceability", "confidence_limitations"]


# ---------------------------------------------------------------- the document lists every endpoint


def documented_endpoints():
    text = DOC.read_text(encoding="utf-8")
    found = set()
    for method, path in re.findall(r"^### (GET|POST|PATCH|PUT|DELETE) (/\S+)\s*$", text, flags=re.MULTILINE):
        found.add((method, re.sub(r"\{[^}]+\}", "{}", path)))
    return found


def implemented_endpoints(app):
    found = set()
    for path, methods in app.openapi()["paths"].items():
        for method in methods:
            found.add((method.upper(), re.sub(r"\{[^}]+\}", "{}", path)))
    return found


def test_every_endpoint_is_documented_and_every_documented_endpoint_exists(app):
    documented = documented_endpoints()
    implemented = implemented_endpoints(app) | {("GET", "/health")}  # the legacy path is left out of the OpenAPI schema
    assert implemented - documented == set(), "endpoints without documentation"
    assert documented - implemented == set(), "documented endpoints that do not exist"
    assert len(documented) >= 21


def test_the_document_names_the_error_codes_the_api_uses():
    text = DOC.read_text(encoding="utf-8")
    for code in (
        "not_authenticated", "invalid_credentials", "email_already_registered", "validation_error", "investigation_not_found", "duplicate_evidence",
        "no_evidence", "analysis_already_running", "file_too_large", "payload_too_large", "invalid_file_type", "invalid_filename", "invalid_evtx",
        "not_analysed", "session_not_found", "rarf_not_found", "report_not_found", "event_not_found", "raw_record_not_found", "internal_error",
        "inbox_file_not_found", "source_already_linked", "invalid_source_name",
    ):
        assert f"`{code}`" in text, code


def test_the_inbox_shapes(app, client, tmp_path):
    from tests.api.conftest import make_investigation
    from tests.synthetic import raw_lines, synthetic_raw_records

    register_and_login(client)
    investigation = make_investigation(client)
    inbox = app.state.settings.resolved_inbox_dir
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / "s.jsonl").write_text(raw_lines(synthetic_raw_records(1)[:2]), encoding="utf-8")
    listing = shape(client.get("/api/inbox").json())
    assert listing == {"items": [{"source_name": None, "size_bytes": None, "modified_at": None, "investigation_id": None, "investigation_code": None}]}
    linked = client.post(f"/api/investigations/{investigation['id']}/collector", json={"source_name": "s.jsonl"})
    assert set(linked.json()) == {"id", "investigation_id", "filename", "sha256", "size_bytes", "source_type", "status", "events_total", "error", "created_at", "ingested_at"}
    sources = shape(client.get(f"/api/investigations/{investigation['id']}/collector").json())
    assert sources == {"items": [{"source_name": None, "evidence_id": None, "last_offset": None, "last_record_id": None, "updated_at": None, "status": None, "events_total": None, "error": None}]}
    polled = shape(client.post("/api/inbox/poll").json())
    assert set(polled) == {"results", "analyses_started"}
    assert set(polled["results"][0]) == {"source_name", "investigation_id", "records_added", "rejected", "offset", "error", "skipped"}
    app.state.runs.wait(1, 60)
