"""Shared fixtures for the API tests: a real application with a temporary registry and a cheap Argon2 setting."""

import os

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from raven.api.main import create_app
from raven.config import Settings

FAST_HASHER = dict(time_cost=1, memory_cost=8, parallelism=1)
PASSWORD = "correct horse battery"


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for name in list(os.environ):
        if name.startswith("RAVEN_"):
            monkeypatch.delenv(name)


def make_settings(tmp_path, **values):
    values.setdefault("env", "test")
    values.setdefault("inbox_dir", tmp_path / "inbox")
    values.setdefault("inbox_poll_seconds", 0)
    return Settings(_env_file=None, data_dir=tmp_path / "data", log_level="WARNING", **values)


@pytest.fixture
def settings(tmp_path):
    return make_settings(tmp_path)


@pytest.fixture
def app(settings):
    application = create_app(settings, password_hasher=PasswordHasher(**FAST_HASHER))
    yield application
    application.state.registry_factory.kw["bind"].dispose()


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


def register_body(email="ada@example.com", password=PASSWORD, **extra):
    return {"name": "Ada Lovelace", "email": email, "organization": "Analytical Engines", "password": password, **extra}


def register_and_login(client, email="ada@example.com", password=PASSWORD):
    assert client.post("/api/auth/register", json=register_body(email, password)).status_code == 201
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response


# ---------------------------------------------------------------- helpers for investigations, evidence and runs (S12)


def make_investigation(client, title="Boot activity", **extra):
    response = client.post("/api/investigations", json={"title": title, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def upload_evtx(client, investigation_id, salt=0, name="Sysmon export.evtx", data=None):
    from tests.synthetic import evtx_bytes

    content = evtx_bytes(salt) if data is None else data
    return client.post(
        f"/api/investigations/{investigation_id}/evidence",
        files={"file": (name, content, "application/octet-stream")},
    )


def run_analysis(app, client, investigation_id, timeout=60):
    """Start a run, wait for its worker thread and return the final run as the API shows it."""
    response = client.post(f"/api/investigations/{investigation_id}/analysis")
    assert response.status_code == 202, response.text
    assert app.state.runs.wait(response.json()["id"], timeout)
    final = client.get(f"/api/investigations/{investigation_id}/analysis")
    assert final.status_code == 200
    return final.json()


def analysed_case(app, client, title="Boot activity"):
    """An investigation with one synthetic evidence file and a completed analysis run (a fake loader replaces the EVTX reader)."""
    from tests.synthetic import fake_loader

    app.state.runs.loader = fake_loader()
    investigation = make_investigation(client, title)
    assert upload_evtx(client, investigation["id"], salt=investigation["id"]).status_code == 201
    run = run_analysis(app, client, investigation["id"])
    assert run["status"] == "completed", run
    return investigation
