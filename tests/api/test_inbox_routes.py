"""API tests: inbox and collector endpoints. SYNTHETIC records, a temporary registry, workspaces and inbox."""

import pytest

from tests.api.conftest import make_investigation, register_and_login, upload_evtx
from tests.synthetic import fake_loader, raw_lines, synthetic_raw_records

RECORDS = synthetic_raw_records(1)
NAME = "sysmon-LAB.jsonl"
SESSION_PREFIX = "RAVEN-SESSION-SYNTHETIC-LAB-HOST-"


@pytest.fixture
def signed_in(client):
    register_and_login(client)
    return client


@pytest.fixture
def investigation(signed_in):
    return make_investigation(signed_in, "Live case")


def drop(settings, records, name=NAME):
    settings.resolved_inbox_dir.mkdir(parents=True, exist_ok=True)
    with open(settings.resolved_inbox_dir / name, "a", encoding="utf-8", newline="") as handle:
        handle.write(raw_lines(records))


def wait_for_run(app, signed_in, investigation_id):
    run = signed_in.get(f"/api/investigations/{investigation_id}/analysis").json()
    assert run is not None and app.state.runs.wait(run["id"], 60)
    return signed_in.get(f"/api/investigations/{investigation_id}/analysis").json()


PROTECTED = [
    ("GET", "/api/inbox"),
    ("POST", "/api/inbox/poll"),
    ("GET", "/api/investigations/1/collector"),
    ("POST", "/api/investigations/1/collector"),
]


@pytest.mark.parametrize("method, path", PROTECTED)
def test_every_inbox_route_needs_a_signed_in_user(client, method, path):
    response = client.request(method, path)
    assert response.status_code == 401 and response.json()["code"] == "not_authenticated"


def test_the_inbox_lists_files_and_their_links(signed_in, investigation, settings):
    assert signed_in.get("/api/inbox").json() == {"items": []}
    drop(settings, RECORDS[:2])
    drop(settings, RECORDS[:1], "second.jsonl")
    assert signed_in.post(f"/api/investigations/{investigation['id']}/collector", json={"source_name": "second.jsonl"}).status_code == 201
    items = signed_in.get("/api/inbox").json()["items"]
    assert [i["source_name"] for i in items] == ["second.jsonl", NAME]
    assert set(items[0]) == {"source_name", "size_bytes", "modified_at", "investigation_id", "investigation_code"}
    assert (items[0]["investigation_id"], items[0]["investigation_code"]) == (investigation["id"], investigation["code"])
    assert (items[1]["investigation_id"], items[1]["investigation_code"]) == (None, None)


def test_linking_a_file_makes_a_collector_evidence_source(signed_in, investigation, settings):
    drop(settings, RECORDS[:3])
    response = signed_in.post(f"/api/investigations/{investigation['id']}/collector", json={"source_name": NAME})
    assert response.status_code == 201
    body = response.json()
    assert (body["source_type"], body["filename"], body["status"], body["events_total"], body["size_bytes"]) == ("vm_collector", NAME, "uploaded", 0, 0)
    assert len(body["sha256"]) == 64
    listing = signed_in.get(f"/api/investigations/{investigation['id']}/collector").json()
    assert listing == {"items": [{"source_name": NAME, "evidence_id": body["id"], "last_offset": 0, "last_record_id": None,
                                 "updated_at": listing["items"][0]["updated_at"], "status": "uploaded", "events_total": 0, "error": None}]}
    assert signed_in.get(f"/api/investigations/{investigation['id']}/evidence").json()["items"][0]["source_type"] == "vm_collector"
    assert signed_in.get(f"/api/investigations/{investigation['id']}").json()["counts"]["evidence"] == 1


@pytest.mark.parametrize("name", ["../x.jsonl", "a b.jsonl", "notes.txt", "a/b.jsonl", ".jsonl", ""])
def test_a_bad_source_name_is_a_validation_error(signed_in, investigation, name):
    response = signed_in.post(f"/api/investigations/{investigation['id']}/collector", json={"source_name": name})
    assert response.status_code == 422 and response.json()["code"] == "validation_error"


def test_linking_errors(signed_in, investigation, settings):
    base = f"/api/investigations/{investigation['id']}/collector"
    assert signed_in.post(base, json={"source_name": "missing.jsonl"}).json()["code"] == "inbox_file_not_found"
    assert signed_in.post("/api/investigations/999/collector", json={"source_name": "missing.jsonl"}).status_code == 404
    assert signed_in.post(base, json={}).status_code == 422 and signed_in.post(base, json={"source_name": NAME, "x": 1}).status_code == 422
    drop(settings, RECORDS[:1])
    assert signed_in.post(base, json={"source_name": NAME}).status_code == 201
    other = make_investigation(signed_in, "Other")
    again = signed_in.post(f"/api/investigations/{other['id']}/collector", json={"source_name": NAME})
    assert again.status_code == 409 and again.json()["code"] == "source_already_linked"
    assert signed_in.get("/api/investigations/999/collector").status_code == 404


def test_polling_takes_over_the_records_and_starts_an_analysis(app, signed_in, investigation, settings):
    app.state.runs.loader = fake_loader()
    drop(settings, RECORDS[:4])
    signed_in.post(f"/api/investigations/{investigation['id']}/collector", json={"source_name": NAME})
    body = signed_in.post("/api/inbox/poll").json()
    (result,) = body["results"]
    assert set(result) == {"source_name", "investigation_id", "records_added", "rejected", "offset", "error", "skipped"}
    assert (result["source_name"], result["records_added"], result["rejected"], result["error"], result["skipped"]) == (NAME, 4, 0, None, None)
    assert body["analyses_started"] == [investigation["id"]]
    run = wait_for_run(app, signed_in, investigation["id"])
    assert run["status"] == "completed" and run["stages"][0]["summary"]["records"] == 4
    source = signed_in.get(f"/api/investigations/{investigation['id']}/collector").json()["items"][0]
    assert (source["status"], source["events_total"], source["last_record_id"], source["last_offset"]) == ("ready", 4, 4, result["offset"])


def test_later_records_appear_in_the_investigation_after_the_next_poll(app, signed_in, investigation, settings):
    base = f"/api/investigations/{investigation['id']}"
    drop(settings, RECORDS[:4])
    signed_in.post(base + "/collector", json={"source_name": NAME})
    signed_in.post("/api/inbox/poll")
    wait_for_run(app, signed_in, investigation["id"])
    assert signed_in.get(base + "/timeline").json()["total"] == 0 and signed_in.get(base + "/detections").json()["total"] == 0

    drop(settings, RECORDS[4:])
    assert signed_in.post("/api/inbox/poll").json()["analyses_started"] == [investigation["id"]]
    wait_for_run(app, signed_in, investigation["id"])
    assert signed_in.get(base + "/timeline").json()["total"] == 11
    detections = signed_in.get(base + "/detections").json()
    assert detections["total"] == 2 and detections["counts"]["by_severity"] == {"HIGH": 2}
    header = signed_in.get(base).json()
    assert (header["severity"], header["counts"]["sessions"], header["counts"]["timeline_events"], header["analysis_status"]) == ("HIGH", 1, 11, "completed")
    assert signed_in.get(base + "/events/1:1").json()["raw"]["record_id"] == 1
    assert signed_in.get(base + "/collector").json()["items"][0]["events_total"] == 13
    assert signed_in.post("/api/inbox/poll").json()["analyses_started"] == []


def test_a_poll_reports_bad_lines_and_files_that_cannot_be_read(signed_in, investigation, settings):
    drop(settings, RECORDS[:2])
    with open(settings.resolved_inbox_dir / NAME, "a", encoding="utf-8", newline="") as handle:
        handle.write("{oops\n")
    signed_in.post(f"/api/investigations/{investigation['id']}/collector", json={"source_name": NAME})
    (result,) = signed_in.post("/api/inbox/poll").json()["results"]
    assert (result["records_added"], result["rejected"]) == (2, 1)
    source = signed_in.get(f"/api/investigations/{investigation['id']}/collector").json()["items"][0]
    assert source["error"].startswith("1 invalid line(s) were skipped")
    (settings.resolved_inbox_dir / NAME).unlink()


def test_a_poll_with_nothing_linked_is_empty(signed_in, settings):
    drop(settings, RECORDS[:2], "stranger.jsonl")
    assert signed_in.post("/api/inbox/poll").json() == {"results": [], "analyses_started": []}


def test_the_dashboard_shows_the_collector_data(app, signed_in, investigation, settings):
    drop(settings, RECORDS)
    signed_in.post(f"/api/investigations/{investigation['id']}/collector", json={"source_name": NAME})
    signed_in.post("/api/inbox/poll")
    wait_for_run(app, signed_in, investigation["id"])
    dashboard = signed_in.get("/api/dashboard").json()
    assert dashboard["totals"]["evidence_items"] == 1 and dashboard["totals"]["sessions"] == 1
    assert dashboard["evidence_by_status"]["ready"] == 1 and dashboard["latest_session"]["session_id"].startswith(SESSION_PREFIX)


def test_an_uploaded_file_and_a_collector_source_work_in_the_same_investigation(app, signed_in, investigation, settings):
    app.state.runs.loader = fake_loader(seed_of=lambda evidence_id: 2)
    base = f"/api/investigations/{investigation['id']}"
    assert upload_evtx(signed_in, investigation["id"]).status_code == 201
    drop(settings, RECORDS)
    signed_in.post(base + "/collector", json={"source_name": NAME})
    signed_in.post("/api/inbox/poll")
    wait_for_run(app, signed_in, investigation["id"])
    assert {i["source_type"] for i in signed_in.get(base + "/evidence").json()["items"]} == {"evtx_upload", "vm_collector"}
    assert signed_in.get(base).json()["counts"]["sessions"] == 2
