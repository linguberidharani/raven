"""Unit tests for password reset by email. A fake mailer captures the composed email instead of sending it."""

from datetime import datetime, timedelta, timezone

import pytest
from argon2 import PasswordHasher
from sqlalchemy import select

from raven.database.registry_models import PasswordResetToken, User, UserSession
from raven.database.session import open_registry_database
from raven.services.auth import AuthError, AuthService
from raven.services.mailer import MailError
from raven.services.password_reset import PasswordResetService

FAST = dict(time_cost=1, memory_cost=8, parallelism=1)
OLD_PASSWORD = "correct horse battery"
NEW_PASSWORD = "new horse battery staple"


class FakeMailer:
    def __init__(self, fail=False):
        self.fail = fail
        self.sent = []

    @property
    def configured(self):
        return True

    def send(self, *, to, subject, text_body, html_body=None):
        if self.fail:
            raise MailError("simulated failure")
        self.sent.append({"to": to, "subject": subject, "text_body": text_body, "html_body": html_body})


class Clock:
    def __init__(self):
        self.now = datetime(2026, 9, 22, 8, 0, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def registry(tmp_path):
    factory = open_registry_database(tmp_path / "registry.db")
    with factory() as session:
        yield session


@pytest.fixture
def hasher():
    return PasswordHasher(**FAST)


@pytest.fixture
def auth(hasher, clock):
    return AuthService(hasher, session_hours=12, now=clock)


@pytest.fixture
def mailer():
    return FakeMailer()


@pytest.fixture
def service(mailer, hasher, clock):
    return PasswordResetService(mailer, hasher, hours=1, base_url="http://localhost:5173/", now=clock)


@pytest.fixture
def user(registry, auth):
    return auth.register(registry, name="Ada Lovelace", email="ada@example.com", organization=None, password=OLD_PASSWORD)


def reset_link_of(mailer):
    body = mailer.sent[0]["text_body"]
    line = next(line for line in body.splitlines() if line.startswith("http"))
    return line


def token_of(mailer):
    return reset_link_of(mailer).split("token=", 1)[1]


class TestRequestReset:
    def test_emails_a_working_link_for_a_real_account(self, service, registry, mailer, user):
        service.request_reset(registry, "ADA@Example.com")  # case and whitespace should not matter
        assert len(mailer.sent) == 1
        assert mailer.sent[0]["to"] == "ada@example.com"
        assert mailer.sent[0]["subject"] == "Reset your RAVEN password"
        assert reset_link_of(mailer).startswith("http://localhost:5173/reset-password?token=")
        assert "1 hour" in mailer.sent[0]["text_body"]
        assert "<a href=" in mailer.sent[0]["html_body"]

        rows = registry.scalars(select(PasswordResetToken)).all()
        assert len(rows) == 1
        assert rows[0].user_id == user.id
        assert rows[0].used_at is None
        # the stored value is a hash, never the token itself
        assert token_of(mailer) not in rows[0].token_hash

    def test_is_silent_for_an_address_with_no_account(self, service, registry, mailer):
        service.request_reset(registry, "nobody@example.com")
        assert mailer.sent == []
        assert registry.scalars(select(PasswordResetToken)).all() == []

    def test_does_not_raise_when_sending_the_email_fails(self, hasher, clock, registry, user):
        failing_mailer = FakeMailer(fail=True)
        service = PasswordResetService(failing_mailer, hasher, hours=1, now=clock)
        service.request_reset(registry, "ada@example.com")  # must not raise
        # the token still exists even though the email did not go out
        assert len(registry.scalars(select(PasswordResetToken)).all()) == 1

    def test_a_second_request_replaces_the_first_token(self, service, registry, mailer, user):
        service.request_reset(registry, "ada@example.com")
        first_token = token_of(mailer)
        mailer.sent.clear()
        service.request_reset(registry, "ada@example.com")
        second_token = token_of(mailer)
        assert first_token != second_token
        with pytest.raises(AuthError):
            service.reset_password(registry, first_token, NEW_PASSWORD)


class TestResetPassword:
    def test_sets_the_new_password_and_lets_the_user_sign_in_with_it(self, service, registry, mailer, user, auth, clock):
        service.request_reset(registry, "ada@example.com")
        token = token_of(mailer)
        service.reset_password(registry, token, NEW_PASSWORD)

        with pytest.raises(AuthError):
            auth.login(registry, email="ada@example.com", password=OLD_PASSWORD)
        signed_in_user, _ = auth.login(registry, email="ada@example.com", password=NEW_PASSWORD)
        assert signed_in_user.id == user.id

    def test_signs_the_account_out_everywhere(self, service, registry, mailer, user, auth, clock):
        auth.login(registry, email="ada@example.com", password=OLD_PASSWORD)
        auth.login(registry, email="ada@example.com", password=OLD_PASSWORD)
        assert len(registry.scalars(select(UserSession)).all()) == 2

        service.request_reset(registry, "ada@example.com")
        service.reset_password(registry, token_of(mailer), NEW_PASSWORD)
        assert registry.scalars(select(UserSession)).all() == []

    def test_the_token_can_be_used_only_once(self, service, registry, mailer, user):
        service.request_reset(registry, "ada@example.com")
        token = token_of(mailer)
        service.reset_password(registry, token, NEW_PASSWORD)
        with pytest.raises(AuthError) as excinfo:
            service.reset_password(registry, token, "another new password")
        assert excinfo.value.code == "invalid_reset_token"
        assert excinfo.value.status_code == 400

    def test_an_expired_token_is_refused(self, service, registry, mailer, user, clock):
        service.request_reset(registry, "ada@example.com")
        token = token_of(mailer)
        clock.advance(hours=1, minutes=1)
        with pytest.raises(AuthError) as excinfo:
            service.reset_password(registry, token, NEW_PASSWORD)
        assert excinfo.value.code == "invalid_reset_token"

    def test_an_unknown_token_is_refused(self, service, registry):
        with pytest.raises(AuthError) as excinfo:
            service.reset_password(registry, "not-a-real-token", NEW_PASSWORD)
        assert excinfo.value.code == "invalid_reset_token"

    def test_the_new_password_is_still_validated(self, service, registry, mailer, user):
        service.request_reset(registry, "ada@example.com")
        with pytest.raises(ValueError):
            service.reset_password(registry, token_of(mailer), "short")
