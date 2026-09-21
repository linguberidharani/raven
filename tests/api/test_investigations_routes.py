"""API tests: investigations (create, list, read, update). A real application, a temporary registry and workspaces."""

import re
from datetime import datetime, timezone

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from raven.api.main import create_app
from tests.api.conftest import FAST_HASHER, make_investigation, register_and_login

YEAR = datetime.now(timezone.utc).year
KEYS = {"id", "code", "title", "description", "host", "status", "severity", "stage", "analysis_status", "analyst", "counts", "created_at", "updated_at"}


@pytest.fixture
def signed_in(client):
    register_and_login(client)
    return client


PROTECTED = [
    ("GET", "/api/investigations"),
    ("POST", "/api/investigations"),
    ("GET", "/api/investigations/1"),
    ("PATCH", "/api/investigations/1"),
    ("GET", "/api/investigations/1/evidence"),
    ("POST", "/api/investigations/1/evidence"),
    ("POST", "/api/investigations/1/analysis"),
    ("GET", "/api/investigations/1/analysis"),
]


@pytest.mark.parametrize("method, path", PROTECTED)
def test_every_investigation_route_needs_a_signed_in_user(client, method, path):
    response = client.request(method, path)
    assert response.status_code == 401 and response.json()["code"] == "not_authenticated"


def test_create_returns_the_investigation(signed_in, settings):
    body = make_investigation(signed_in, "Boot activity", description="Startup review", host="HOST-1")
    assert set(body) == KEYS
    assert re.fullmatch(rf"INV-{YEAR}-001", body["code"])
    assert (body["title"], body["description"], body["host"], body["status"]) == ("Boot activity", "Startup review", "HOST-1", "open")
    assert (body["severity"], body["stage"], body["analysis_status"]) == (None, None, None)
    assert body["counts"] == {"evidence": 0, "detections": 0, "sessions": 0, "timeline_events": 0}
    assert body["analyst"] == {"id": 1, "name": "Ada Lovelace"}
    assert body["created_at"].endswith("Z") and body["created_at"] == body["updated_at"]
    assert (settings.resolved_data_dir / "investigations" / str(body["id"]) / "evidence").is_dir()


def test_codes_count_up(signed_in):
    assert [make_investigation(signed_in, f"Case {n}")["code"][-3:] for n in range(3)] == ["001", "002", "003"]


@pytest.mark.parametrize(
    "body, field",
    [({}, "title"), ({"title": "  "}, "title"), ({"title": "x" * 201}, "title"), ({"title": "ok", "description": "x" * 5001}, "description"), ({"title": "ok", "host": "x" * 101}, "host")],
)
def test_create_rejects_bad_input(signed_in, body, field):
    response = signed_in.post("/api/investigations", json=body)
    assert response.status_code == 422 and any(item["loc"] == ["body", field] for item in response.json()["detail"])


def test_create_rejects_unknown_fields(signed_in):
    assert signed_in.post("/api/investigations", json={"title": "ok", "status": "closed"}).status_code == 422


def test_the_list_is_paged_newest_first(signed_in):
    for number in range(5):
        make_investigation(signed_in, f"Case {number}")
    body = signed_in.get("/api/investigations").json()
    assert set(body) == {"items", "total", "page", "page_size"} and (body["total"], body["page"], body["page_size"]) == (5, 1, 100)
    assert [item["title"] for item in body["items"]] == ["Case 4", "Case 3", "Case 2", "Case 1", "Case 0"]
    second = signed_in.get("/api/investigations", params={"page": 2, "page_size": 2}).json()
    assert [item["title"] for item in second["items"]] == ["Case 2", "Case 1"] and second["total"] == 5
    assert set(second["items"][0]) == KEYS


def test_the_list_filters(signed_in):
    a = make_investigation(signed_in, "Boot activity", description="Startup review")
    b = make_investigation(signed_in, "Lab burst")
    signed_in.patch(f"/api/investigations/{b['id']}", json={"status": "closed"})
    assert [i["id"] for i in signed_in.get("/api/investigations", params={"status": "closed"}).json()["items"]] == [b["id"]]
    assert [i["id"] for i in signed_in.get("/api/investigations", params={"q": "STARTUP"}).json()["items"]] == [a["id"]]
    assert signed_in.get("/api/investigations", params={"q": "nothing"}).json()["total"] == 0
    assert signed_in.get("/api/investigations", params={"severity": "HIGH"}).json() == {"items": [], "total": 0, "page": 1, "page_size": 100}


@pytest.mark.parametrize("params", [{"status": "paused"}, {"severity": "CRITICAL"}, {"page": 0}, {"page_size": 0}, {"page_size": 201}, {"q": "x" * 101}])
def test_the_list_rejects_bad_filters(signed_in, params):
    assert signed_in.get("/api/investigations", params=params).status_code == 422


def test_get_returns_one_investigation(signed_in):
    created = make_investigation(signed_in)
    assert signed_in.get(f"/api/investigations/{created['id']}").json() == created


def test_an_unknown_investigation_is_not_found(signed_in):
    response = signed_in.get("/api/investigations/999")
    assert response.status_code == 404 and response.json()["code"] == "investigation_not_found"


@pytest.mark.parametrize("bad", ["0", "-1", "abc", "1.5"])
def test_investigation_ids_in_paths_are_validated(signed_in, bad):
    assert signed_in.get(f"/api/investigations/{bad}").status_code == 422
    assert signed_in.get(f"/api/investigations/{bad}/evidence").status_code == 422
    assert signed_in.post(f"/api/investigations/{bad}/analysis").status_code == 422


def test_patch_changes_only_the_sent_fields(signed_in):
    created = make_investigation(signed_in, "Old", description="text", host="H")
    body = signed_in.patch(f"/api/investigations/{created['id']}", json={"title": "New", "description": None}).json()
    assert (body["title"], body["description"], body["host"], body["status"]) == ("New", None, "H", "open")
    assert body["updated_at"] >= created["updated_at"] and body["code"] == created["code"]
    body = signed_in.patch(f"/api/investigations/{created['id']}", json={"status": "active", "host": None}).json()
    assert (body["status"], body["host"], body["title"]) == ("active", None, "New")


@pytest.mark.parametrize("body", [{"status": "paused"}, {"status": None}, {"title": None}, {"title": " "}, {"code": "INV-1"}, {"analyst_id": 2}])
def test_patch_rejects_bad_input(signed_in, body):
    created = make_investigation(signed_in)
    assert signed_in.patch(f"/api/investigations/{created['id']}", json=body).status_code == 422


def test_patch_of_an_unknown_investigation_is_not_found(signed_in):
    assert signed_in.patch("/api/investigations/999", json={"title": "x"}).status_code == 404


def test_an_empty_patch_only_touches_the_update_time(signed_in):
    created = make_investigation(signed_in)
    body = signed_in.patch(f"/api/investigations/{created['id']}", json={}).json()
    assert {k: v for k, v in body.items() if k != "updated_at"} == {k: v for k, v in created.items() if k != "updated_at"}


def test_all_analysts_see_all_investigations_and_the_creator_is_recorded(app, signed_in):
    created = make_investigation(signed_in, "Shared case")
    with TestClient(app) as other:
        register_and_login(other, email="grace@example.com")
        listed = other.get("/api/investigations").json()
        assert [i["id"] for i in listed["items"]] == [created["id"]]
        assert listed["items"][0]["analyst"]["name"] == "Ada Lovelace"
        assert other.get(f"/api/investigations/{created['id']}").status_code == 200
        second = other.post("/api/investigations", json={"title": "Grace's case"}).json()
    assert second["analyst"]["id"] == 2
    assert {i["title"] for i in signed_in.get("/api/investigations").json()["items"]} == {"Shared case", "Grace's case"}


def test_investigations_are_isolated_between_applications(tmp_path):
    from tests.api.conftest import make_settings

    first = create_app(make_settings(tmp_path / "one"), PasswordHasher(**FAST_HASHER))
    second = create_app(make_settings(tmp_path / "two"), PasswordHasher(**FAST_HASHER))
    try:
        with TestClient(first) as a, TestClient(second) as b:
            register_and_login(a)
            register_and_login(b)
            make_investigation(a, "Only in one")
            assert b.get("/api/investigations").json()["total"] == 0
    finally:
        first.state.registry_factory.kw["bind"].dispose()
        second.state.registry_factory.kw["bind"].dispose()
