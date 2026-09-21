"""API tests: evidence upload and listing. Synthetic fake EVTX bytes, a temporary registry and workspaces."""

import hashlib

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from raven.api.main import create_app
from raven.services.evidence import EVTX_SIGNATURE
from tests.api.conftest import FAST_HASHER, make_investigation, make_settings, register_and_login, upload_evtx
from tests.synthetic import evtx_bytes

KEYS = {"id", "investigation_id", "filename", "sha256", "size_bytes", "source_type", "status", "events_total", "error", "created_at", "ingested_at"}


@pytest.fixture
def signed_in(client):
    register_and_login(client)
    return client


@pytest.fixture
def investigation(signed_in):
    return make_investigation(signed_in)


def test_an_upload_is_accepted_and_hashed(signed_in, investigation, settings):
    data = evtx_bytes(1)
    response = upload_evtx(signed_in, investigation["id"], data=data)
    assert response.status_code == 201
    body = response.json()
    assert set(body) == KEYS
    assert body["sha256"] == hashlib.sha256(data).hexdigest().upper() and body["size_bytes"] == len(data)
    assert (body["filename"], body["source_type"], body["status"], body["events_total"], body["error"], body["ingested_at"]) == (
        "Sysmon export.evtx", "evtx_upload", "uploaded", 0, None, None)
    stored = settings.resolved_data_dir / "investigations" / str(investigation["id"]) / "evidence" / f"{body['id']}.evtx"
    assert stored.read_bytes() == data


def test_the_list_shows_the_files_and_an_empty_breakdown_before_analysis(signed_in, investigation):
    first = upload_evtx(signed_in, investigation["id"], 1, "a.evtx").json()
    second = upload_evtx(signed_in, investigation["id"], 2, "b.evtx").json()
    body = signed_in.get(f"/api/investigations/{investigation['id']}/evidence").json()
    assert set(body) == {"items", "event_breakdown"} and body["event_breakdown"] == []
    assert [item["id"] for item in body["items"]] == [first["id"], second["id"]]
    assert signed_in.get(f"/api/investigations/{investigation['id']}").json()["counts"]["evidence"] == 2


def test_the_investigation_counts_the_evidence(signed_in, investigation):
    upload_evtx(signed_in, investigation["id"])
    assert signed_in.get(f"/api/investigations/{investigation['id']}").json()["counts"]["evidence"] == 1


@pytest.mark.parametrize("name, code", [("notes.txt", "invalid_file_type"), ("log.evtx.exe", "invalid_file_type"), ("evtx", "invalid_file_type")])
def test_only_evtx_names_are_accepted(signed_in, investigation, name, code):
    response = upload_evtx(signed_in, investigation["id"], name=name)
    assert response.status_code == 422 and response.json()["code"] == code


def test_a_file_that_is_not_an_evtx_file_is_refused(signed_in, investigation):
    response = upload_evtx(signed_in, investigation["id"], data=b"plain text pretending to be a log" * 200)
    assert response.status_code == 422 and response.json()["code"] == "invalid_evtx"
    assert signed_in.get(f"/api/investigations/{investigation['id']}/evidence").json()["items"] == []


def test_a_request_without_a_file_is_a_validation_error(signed_in, investigation):
    response = signed_in.post(f"/api/investigations/{investigation['id']}/evidence", data={"other": "x"})
    assert response.status_code == 422 and response.json()["code"] == "validation_error"
    assert signed_in.post(f"/api/investigations/{investigation['id']}/evidence", json={"file": "x"}).status_code == 422


def test_the_same_file_twice_is_refused(signed_in, investigation):
    assert upload_evtx(signed_in, investigation["id"], 5).status_code == 201
    response = upload_evtx(signed_in, investigation["id"], 5, name="copy.evtx")
    assert response.status_code == 409 and response.json()["code"] == "duplicate_evidence"


def test_an_unknown_investigation_is_not_found(signed_in):
    assert upload_evtx(signed_in, 999).status_code == 404
    assert signed_in.get("/api/investigations/999/evidence").status_code == 404


def test_the_uploaded_name_is_only_a_label(signed_in, investigation, settings):
    body = upload_evtx(signed_in, investigation["id"], name="..\\..\\..\\evil.evtx").json()
    assert body["filename"] == "evil.evtx"
    root = settings.resolved_data_dir
    assert not list(root.rglob("evil*"))
    assert [p.name for p in (root / "investigations" / str(investigation["id"]) / "evidence").iterdir()] == [f"{body['id']}.evtx"]


@pytest.fixture
def small_limit_client(tmp_path):
    app = create_app(make_settings(tmp_path, max_upload_mb=1), PasswordHasher(**FAST_HASHER))
    try:
        with TestClient(app) as client:
            register_and_login(client)
            yield client
    finally:
        app.state.registry_factory.kw["bind"].dispose()


def test_a_file_over_the_limit_is_refused(small_limit_client):
    investigation = make_investigation(small_limit_client)
    data = EVTX_SIGNATURE + bytes(1024 * 1024 + 100)
    response = upload_evtx(small_limit_client, investigation["id"], data=data)
    assert response.status_code == 413 and response.json()["code"] == "file_too_large"
    assert small_limit_client.get(f"/api/investigations/{investigation['id']}/evidence").json()["items"] == []


def test_a_request_far_over_the_limit_is_refused_before_it_is_read(small_limit_client):
    investigation = make_investigation(small_limit_client)
    data = EVTX_SIGNATURE + bytes(3 * 1024 * 1024)
    response = upload_evtx(small_limit_client, investigation["id"], data=data)
    assert response.status_code == 413 and response.json()["code"] == "payload_too_large"
    assert response.headers["X-Request-ID"] == response.json()["request_id"]


def test_a_file_at_the_limit_is_accepted(small_limit_client):
    investigation = make_investigation(small_limit_client)
    data = EVTX_SIGNATURE + bytes(1024 * 1024 - len(EVTX_SIGNATURE))
    assert upload_evtx(small_limit_client, investigation["id"], data=data).status_code == 201
