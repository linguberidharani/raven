"""API tests: request IDs and the error format. A real application, a temporary registry."""

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import register_body


def test_every_response_has_a_request_id(client):
    response = client.get("/api/health")
    assert len(response.headers["X-Request-ID"]) == 32


def test_a_valid_client_request_id_is_used(client):
    response = client.get("/api/health", headers={"X-Request-ID": "abc-123_XYZ.9"})
    assert response.headers["X-Request-ID"] == "abc-123_XYZ.9"


@pytest.mark.parametrize("bad", ["", "has space", "x" * 65, "semi;colon", "new\tline"])
def test_an_unusable_client_request_id_is_replaced(client, bad):
    response = client.get("/api/health", headers={"X-Request-ID": bad})
    assert response.headers["X-Request-ID"] != bad and len(response.headers["X-Request-ID"]) == 32


def test_two_requests_get_different_ids(client):
    assert client.get("/api/health").headers["X-Request-ID"] != client.get("/api/health").headers["X-Request-ID"]


def test_an_unknown_route_uses_the_error_format(client):
    response = client.get("/api/nothing-here", headers={"X-Request-ID": "req-1"})
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found", "code": "not_found", "request_id": "req-1"}
    assert response.headers["X-Request-ID"] == "req-1"


def test_a_wrong_method_uses_the_error_format(client):
    response = client.get("/api/auth/login")
    assert response.status_code == 405
    body = response.json()
    assert body["code"] == "method_not_allowed" and set(body) == {"detail", "code", "request_id"}
    assert body["request_id"] == response.headers["X-Request-ID"]


def test_a_validation_error_lists_the_fields_without_echoing_the_input(client):
    body = register_body(password="short")
    response = client.post("/api/auth/register", json=body)
    assert response.status_code == 422
    data = response.json()
    assert data["code"] == "validation_error" and data["request_id"] == response.headers["X-Request-ID"]
    assert {"loc": ["body", "password"], "msg": "password must have 10 to 128 characters"} in data["detail"]
    assert "short" not in response.text.replace("password must have", "")
    assert all(set(item) == {"loc", "msg"} for item in data["detail"])


def test_an_invalid_json_body_is_a_validation_error(client):
    response = client.post("/api/auth/login", content="{not json", headers={"Content-Type": "application/json"})
    assert response.status_code == 422 and response.json()["code"] == "validation_error"


def test_an_unexpected_failure_is_a_clean_500(app):
    @app.get("/api/boom")
    def boom():
        raise RuntimeError("secret internal detail")

    with TestClient(app, raise_server_exceptions=False) as test_client:
        response = test_client.get("/api/boom", headers={"X-Request-ID": "req-500"})
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error", "code": "internal_error", "request_id": "req-500"}
    assert response.headers["X-Request-ID"] == "req-500"
    assert "secret internal detail" not in response.text


def test_responses_are_not_sniffed(client):
    assert client.get("/api/health").headers["X-Content-Type-Options"] == "nosniff"


def test_request_lines_are_logged_with_the_request_id_and_no_secrets(client, caplog):
    import logging

    caplog.set_level(logging.INFO, logger="raven.api")
    client.post("/api/auth/login", json={"email": "x@example.com", "password": "very secret password"}, headers={"X-Request-ID": "log-1"})
    lines = [r.getMessage() for r in caplog.records if r.name == "raven.api"]
    assert any("request_id=log-1 POST /api/auth/login -> 401" in line for line in lines)
    assert not any("very secret password" in line for line in lines)
