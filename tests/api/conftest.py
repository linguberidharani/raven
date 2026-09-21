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
