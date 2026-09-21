"""API tests: authentication is required, and no plain password or token is stored, logged or returned."""

import logging

from argon2 import PasswordHasher
from fastapi import Depends
from fastapi.testclient import TestClient

from raven.api.dependencies import current_user
from raven.api.main import create_app
from raven.api.schemas.auth import RegisterRequest
from tests.api.conftest import FAST_HASHER, PASSWORD, make_settings, register_and_login, register_body

SECRET_PASSWORD = "S3cret-passphrase-for-tests"


def add_protected_route(app):
    @app.get("/api/protected-example", dependencies=[Depends(current_user)])
    def protected_example():
        return {"ok": True}


def test_a_route_that_depends_on_current_user_rejects_anonymous_requests(app):
    add_protected_route(app)
    with TestClient(app) as client:
        response = client.get("/api/protected-example")
        assert response.status_code == 401 and response.json()["code"] == "not_authenticated"
        register_and_login(client)
        assert client.get("/api/protected-example").json() == {"ok": True}
        client.post("/api/auth/logout")
        assert client.get("/api/protected-example").status_code == 401


def test_only_health_register_and_login_are_open(app):
    documented = set(app.openapi()["paths"])
    assert {"/api/health", "/api/auth/register", "/api/auth/login", "/api/auth/me", "/api/auth/logout"} <= documented
    with TestClient(app) as client:
        assert client.get("/api/auth/me").status_code == 401
        assert client.post("/api/auth/logout").status_code == 401
        assert client.get("/api/health").status_code == 200
        assert client.get("/health").status_code == 200
        assert client.post("/api/auth/login", json={"email": "a@example.com", "password": "x"}).status_code == 401
        assert client.post("/api/auth/register", json={}).status_code == 422


def test_the_password_is_never_stored_returned_or_logged(client, app, settings, caplog):
    caplog.set_level(logging.DEBUG)
    body = register_body(password=SECRET_PASSWORD)
    responses = [
        client.post("/api/auth/register", json=body),
        client.post("/api/auth/login", json={"email": body["email"], "password": SECRET_PASSWORD}),
        client.post("/api/auth/login", json={"email": body["email"], "password": SECRET_PASSWORD + "x"}),
        client.get("/api/auth/me"),
        client.post("/api/auth/register", json={**body, "password": "short"}),
    ]
    for response in responses:
        assert SECRET_PASSWORD not in response.text
        assert SECRET_PASSWORD not in str(dict(response.headers))
    assert SECRET_PASSWORD not in caplog.text
    app.state.registry_factory.kw["bind"].dispose()
    data = settings.registry_path.read_bytes()
    assert SECRET_PASSWORD.encode() not in data
    assert b"$argon2id$" in data


def test_the_session_token_is_stored_only_as_a_hash(client, app, settings):
    register_and_login(client)
    token = client.cookies.get("raven_session")
    assert len(token) >= 40
    app.state.registry_factory.kw["bind"].dispose()
    assert token.encode() not in settings.registry_path.read_bytes()


def test_the_stored_hash_belongs_to_the_password(client, app):
    from sqlalchemy import select

    from raven.database.registry_models import User

    client.post("/api/auth/register", json=register_body(password=SECRET_PASSWORD))
    with app.state.registry_factory() as session:
        stored = session.scalars(select(User.password_hash)).one()
    assert PasswordHasher(**FAST_HASHER).verify(stored, SECRET_PASSWORD)


def test_the_request_model_does_not_show_the_password():
    model = RegisterRequest(name="A", email="a@example.com", password=SECRET_PASSWORD)
    assert SECRET_PASSWORD not in repr(model) and SECRET_PASSWORD not in str(model) and SECRET_PASSWORD not in model.model_dump_json()


def test_applications_with_different_data_folders_are_isolated(tmp_path):
    first = create_app(make_settings(tmp_path / "one"), PasswordHasher(**FAST_HASHER))
    second = create_app(make_settings(tmp_path / "two"), PasswordHasher(**FAST_HASHER))
    try:
        with TestClient(first) as a, TestClient(second) as b:
            a.post("/api/auth/register", json=register_body())
            assert b.post("/api/auth/login", json={"email": "ada@example.com", "password": PASSWORD}).status_code == 401
            assert a.post("/api/auth/login", json={"email": "ada@example.com", "password": PASSWORD}).status_code == 200
    finally:
        first.state.registry_factory.kw["bind"].dispose()
        second.state.registry_factory.kw["bind"].dispose()


def test_the_real_argon2_defaults_are_used_when_no_hasher_is_given(tmp_path):
    application = create_app(make_settings(tmp_path))
    try:
        assert application.state.auth.hasher._parameters.type.name == "ID"
    finally:
        application.state.registry_factory.kw["bind"].dispose()
