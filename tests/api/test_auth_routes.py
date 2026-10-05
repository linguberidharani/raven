"""API tests: register, login, logout and me. A real application, a temporary registry."""

import pytest
from sqlalchemy import select, update

from raven.database.registry_models import User, UserSession
from tests.api.conftest import PASSWORD, make_settings, register_and_login, register_body
from fastapi.testclient import TestClient
from argon2 import PasswordHasher

from raven.api.main import create_app


def test_register_creates_an_account_and_returns_the_user_only(client):
    response = client.post("/api/auth/register", json=register_body())
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "name", "email", "organization", "created_at"}
    assert body["email"] == "ada@example.com" and body["name"] == "Ada Lovelace" and body["organization"] == "Analytical Engines"
    assert body["created_at"].endswith("Z")
    assert PASSWORD not in response.text and "password" not in response.text.lower()
    assert response.headers["Cache-Control"] == "no-store"


def test_register_does_not_sign_in(client):
    client.post("/api/auth/register", json=register_body())
    assert client.get("/api/auth/me").status_code == 401


def test_register_without_an_organization(client):
    body = register_body()
    del body["organization"]
    response = client.post("/api/auth/register", json=body)
    assert response.status_code == 201 and response.json()["organization"] is None


@pytest.mark.parametrize(
    "changes, field",
    [
        ({"password": "short"}, "password"),
        ({"email": "not-an-email"}, "email"),
        ({"name": "   "}, "name"),
        ({"organization": "x" * 101}, "organization"),
    ],
)
def test_register_rejects_bad_input(client, changes, field):
    response = client.post("/api/auth/register", json={**register_body(), **changes})
    assert response.status_code == 422
    assert any(item["loc"] == ["body", field] for item in response.json()["detail"])


def test_register_rejects_missing_and_unknown_fields(client):
    assert client.post("/api/auth/register", json={}).status_code == 422
    assert client.post("/api/auth/register", json=register_body(role="admin")).status_code == 422


def test_a_second_account_with_the_same_email_is_refused(client):
    assert client.post("/api/auth/register", json=register_body()).status_code == 201
    response = client.post("/api/auth/register", json=register_body("ADA@Example.com"))
    assert response.status_code == 409
    assert response.json()["code"] == "email_already_registered"


def test_login_sets_an_http_only_lax_cookie(client):
    response = register_and_login(client)
    assert set(response.json()) == {"id", "name", "email", "organization", "created_at"}
    cookie = response.headers["set-cookie"]
    assert cookie.startswith("raven_session=")
    lowered = cookie.lower()
    assert "httponly" in lowered and "samesite=lax" in lowered and "path=/" in lowered and "max-age=43200" in lowered
    assert "secure" not in lowered.replace("samesite", "")
    assert response.headers["Cache-Control"] == "no-store"


def test_the_cookie_is_secure_when_the_settings_say_so(tmp_path):
    application = create_app(make_settings(tmp_path, cookie_secure=True, session_hours=2), PasswordHasher(time_cost=1, memory_cost=8, parallelism=1))
    try:
        with TestClient(application, base_url="https://testserver") as test_client:
            response = register_and_login(test_client)
        lowered = response.headers["set-cookie"].lower()
        assert "secure" in lowered.replace("samesite", "") and "max-age=7200" in lowered
    finally:
        application.state.registry_factory.kw["bind"].dispose()


def test_login_accepts_the_email_in_any_case(client):
    client.post("/api/auth/register", json=register_body())
    assert client.post("/api/auth/login", json={"email": "ADA@EXAMPLE.COM", "password": PASSWORD}).status_code == 200


def test_a_wrong_password_and_an_unknown_email_look_the_same(client):
    client.post("/api/auth/register", json=register_body())
    wrong = client.post("/api/auth/login", json={"email": "ada@example.com", "password": "not the password"})
    unknown = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": PASSWORD})
    assert wrong.status_code == unknown.status_code == 401
    for response in (wrong, unknown):
        assert response.json()["code"] == "invalid_credentials" and response.json()["detail"] == "Email or password is not correct."
        assert "set-cookie" not in response.headers


def test_login_rejects_unknown_fields(client):
    assert client.post("/api/auth/login", json={"email": "a@example.com", "password": "x", "remember": True}).status_code == 422


def test_me_returns_the_signed_in_user(client):
    login = register_and_login(client)
    response = client.get("/api/auth/me")
    assert response.status_code == 200 and response.json() == login.json()


def test_me_without_a_cookie_is_refused(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated" and response.json()["detail"] == "Authentication required."


def test_a_made_up_cookie_is_refused(client):
    client.cookies.set("raven_session", "not-a-real-token")
    assert client.get("/api/auth/me").status_code == 401


def test_logout_ends_the_session_and_clears_the_cookie(client):
    register_and_login(client)
    response = client.post("/api/auth/logout")
    assert response.status_code == 204 and response.content == b""
    assert "max-age=0" in response.headers["set-cookie"].lower()
    assert client.get("/api/auth/me").status_code == 401


def test_logout_needs_a_session(client):
    assert client.post("/api/auth/logout").status_code == 401


def test_a_logged_out_token_cannot_be_used_again(client):
    register_and_login(client)
    token = client.cookies.get("raven_session")
    client.post("/api/auth/logout")
    client.cookies.set("raven_session", token)
    assert client.get("/api/auth/me").status_code == 401


def test_an_expired_session_is_refused(client, app):
    register_and_login(client)
    with app.state.registry_factory() as session:
        session.execute(update(UserSession).values(expires_at="2000-01-01T00:00:00.000Z"))
        session.commit()
    assert client.get("/api/auth/me").status_code == 401
    with app.state.registry_factory() as session:
        assert session.scalars(select(UserSession)).all() == []


def test_two_browsers_have_independent_sessions(app, client):
    register_and_login(client)
    with TestClient(app) as other:
        assert other.get("/api/auth/me").status_code == 401
        assert other.post("/api/auth/login", json={"email": "ada@example.com", "password": PASSWORD}).status_code == 200
        assert client.post("/api/auth/logout").status_code == 204
        assert other.get("/api/auth/me").status_code == 200


def test_the_account_is_stored_in_the_registry(client, app):
    client.post("/api/auth/register", json=register_body())
    with app.state.registry_factory() as session:
        (user,) = session.scalars(select(User)).all()
    assert user.email == "ada@example.com" and user.password_hash.startswith("$argon2id$")


# ---------------------------------------------------------------------------- forgot / reset password


class _FakeMailer:
    """Captures the email instead of sending it, so a test can read the reset link out of it."""

    def __init__(self):
        self.sent = []

    @property
    def configured(self):
        return True

    def send(self, *, to, subject, text_body, html_body=None):
        self.sent.append({"to": to, "subject": subject, "text_body": text_body})

    def token_of(self):
        body = self.sent[-1]["text_body"]
        line = next(line for line in body.splitlines() if line.startswith("http"))
        return line.split("token=", 1)[1]


def _app_with_mailer(tmp_path):
    from raven.api.main import create_app

    mailer = _FakeMailer()
    application = create_app(make_settings(tmp_path), PasswordHasher(time_cost=1, memory_cost=8, parallelism=1), mailer)
    return application, mailer


def test_forgot_password_answers_202_the_same_way_for_a_real_and_an_unknown_address(tmp_path):
    application, mailer = _app_with_mailer(tmp_path)
    try:
        with TestClient(application) as client:
            client.post("/api/auth/register", json=register_body())
            known = client.post("/api/auth/forgot-password", json={"email": "ada@example.com"})
            unknown = client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"})
        assert known.status_code == unknown.status_code == 202
        assert known.json() == unknown.json()
        assert known.headers["Cache-Control"] == "no-store"
        assert len(mailer.sent) == 1  # only the real address is actually emailed
        assert mailer.sent[0]["to"] == "ada@example.com"
    finally:
        application.state.registry_factory.kw["bind"].dispose()


def test_forgot_password_rejects_a_malformed_address(client):
    response = client.post("/api/auth/forgot-password", json={"email": "not-an-email"})
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_reset_password_end_to_end(tmp_path):
    application, mailer = _app_with_mailer(tmp_path)
    try:
        with TestClient(application) as client:
            client.post("/api/auth/register", json=register_body())
            client.post("/api/auth/forgot-password", json={"email": "ada@example.com"})
            token = mailer.token_of()

            reset = client.post("/api/auth/reset-password", json={"token": token, "password": "a brand new password"})
            assert reset.status_code == 200
            assert reset.json() == {"detail": "Your password has been updated. Sign in with your new password."}
            assert reset.headers["Cache-Control"] == "no-store"

            old = client.post("/api/auth/login", json={"email": "ada@example.com", "password": PASSWORD})
            assert old.status_code == 401
            new = client.post("/api/auth/login", json={"email": "ada@example.com", "password": "a brand new password"})
            assert new.status_code == 200
    finally:
        application.state.registry_factory.kw["bind"].dispose()


def test_reset_password_signs_out_every_existing_session(tmp_path):
    application, mailer = _app_with_mailer(tmp_path)
    try:
        with TestClient(application) as first, TestClient(application) as second:
            first.post("/api/auth/register", json=register_body())
            first.post("/api/auth/login", json={"email": "ada@example.com", "password": PASSWORD})
            second.post("/api/auth/login", json={"email": "ada@example.com", "password": PASSWORD})
            assert first.get("/api/auth/me").status_code == 200
            assert second.get("/api/auth/me").status_code == 200

            first.post("/api/auth/forgot-password", json={"email": "ada@example.com"})
            client_only = TestClient(application)
            client_only.post("/api/auth/reset-password", json={"token": mailer.token_of(), "password": "a brand new password"})

            assert first.get("/api/auth/me").status_code == 401
            assert second.get("/api/auth/me").status_code == 401
    finally:
        application.state.registry_factory.kw["bind"].dispose()


def test_reset_password_rejects_an_unknown_or_reused_token(tmp_path):
    application, mailer = _app_with_mailer(tmp_path)
    try:
        with TestClient(application) as client:
            unknown = client.post("/api/auth/reset-password", json={"token": "not-a-real-token", "password": "a brand new password"})
            assert unknown.status_code == 400
            assert unknown.json()["code"] == "invalid_reset_token"

            client.post("/api/auth/register", json=register_body())
            client.post("/api/auth/forgot-password", json={"email": "ada@example.com"})
            token = mailer.token_of()
            first_use = client.post("/api/auth/reset-password", json={"token": token, "password": "a brand new password"})
            assert first_use.status_code == 200
            second_use = client.post("/api/auth/reset-password", json={"token": token, "password": "yet another password"})
            assert second_use.status_code == 400
            assert second_use.json()["code"] == "invalid_reset_token"
    finally:
        application.state.registry_factory.kw["bind"].dispose()


def test_reset_password_rejects_a_password_that_breaks_the_rules(tmp_path):
    application, mailer = _app_with_mailer(tmp_path)
    try:
        with TestClient(application) as client:
            client.post("/api/auth/register", json=register_body())
            client.post("/api/auth/forgot-password", json={"email": "ada@example.com"})
            response = client.post("/api/auth/reset-password", json={"token": mailer.token_of(), "password": "short"})
        assert response.status_code == 422
        assert response.json()["code"] == "validation_error"
    finally:
        application.state.registry_factory.kw["bind"].dispose()


def test_forgot_password_does_not_leak_whether_email_sending_is_configured(client):
    """Even with no SMTP settings at all (the default test app), the request still answers 202."""
    client.post("/api/auth/register", json=register_body())
    response = client.post("/api/auth/forgot-password", json={"email": "ada@example.com"})
    assert response.status_code == 202
