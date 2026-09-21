"""Unit tests for accounts and sessions. Temporary directories only; a cheap Argon2 setting keeps them fast."""

from datetime import datetime, timedelta, timezone

import pytest
from argon2 import PasswordHasher
from sqlalchemy import select

from raven.database.registry_models import User, UserSession
from raven.database.session import open_registry_database
from raven.services.auth import (
    AuthError,
    AuthService,
    hash_token,
    normalize_email,
    validate_email,
    validate_name,
    validate_organization,
    validate_password,
)

FAST = dict(time_cost=1, memory_cost=8, parallelism=1)
PASSWORD = "correct horse battery"


class Clock:
    def __init__(self):
        self.now = datetime(2026, 9, 13, 8, 0, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def service(clock):
    return AuthService(PasswordHasher(**FAST), session_hours=12, now=clock)


@pytest.fixture
def registry(tmp_path):
    factory = open_registry_database(tmp_path / "registry.db")
    with factory() as session:
        yield session
    factory.kw["bind"].dispose()


def register(service, registry, email="Ada@Example.com", password=PASSWORD, **kwargs):
    return service.register(registry, name=kwargs.get("name", "Ada"), email=email, organization=kwargs.get("organization"), password=password)


# ---------------------------------------------------------------- input rules


def test_names():
    assert validate_name("  Ada Lovelace ") == "Ada Lovelace"
    for bad in ("", "   ", "x" * 101):
        with pytest.raises(ValueError):
            validate_name(bad)


def test_organizations():
    assert validate_organization(None) is None
    assert validate_organization("   ") is None
    assert validate_organization(" Lab ") == "Lab"
    with pytest.raises(ValueError):
        validate_organization("x" * 101)


def test_emails_are_normalized_and_checked():
    assert normalize_email("  Ada@Example.COM ") == "ada@example.com"
    assert validate_email("Ada@Example.com") == "ada@example.com"
    for bad in ("", "ada", "ada@", "@example.com", "ada@example", "a b@example.com", "a@" + "x" * 250 + ".com"):
        with pytest.raises(ValueError):
            validate_email(bad)


def test_passwords():
    assert validate_password(PASSWORD) == PASSWORD
    for bad in ("short", "x" * 129, " " * 12):
        with pytest.raises(ValueError):
            validate_password(bad)
    assert validate_password("x" * 10) and validate_password("x" * 128)


# ---------------------------------------------------------------- registration


def test_registration_stores_a_hash_never_the_password(service, registry):
    user = register(service, registry, organization="Lab")
    assert user.email == "ada@example.com" and user.organization == "Lab" and user.created_at == "2026-09-13T08:00:00.000Z"
    assert user.password_hash.startswith("$argon2id$")
    assert PASSWORD not in user.password_hash
    assert PasswordHasher(**FAST).verify(user.password_hash, PASSWORD)


def test_the_same_password_gives_different_hashes(service, registry):
    a = register(service, registry, email="a@example.com")
    b = register(service, registry, email="b@example.com")
    assert a.password_hash != b.password_hash


def test_a_duplicate_email_is_refused_whatever_its_case(service, registry):
    register(service, registry)
    with pytest.raises(AuthError) as caught:
        register(service, registry, email="ADA@example.COM")
    assert (caught.value.code, caught.value.status_code) == ("email_already_registered", 409)
    assert len(registry.scalars(select(User)).all()) == 1


def test_registration_checks_its_input(service, registry):
    for kwargs in ({"password": "short"}, {"email": "nope"}, {"name": " "}):
        with pytest.raises(ValueError):
            register(service, registry, **kwargs)


# ---------------------------------------------------------------- sessions


def test_login_starts_a_session_and_stores_only_the_token_hash(service, registry, clock):
    user = register(service, registry)
    signed_in, token = service.login(registry, email="ADA@example.com", password=PASSWORD)
    assert signed_in.id == user.id
    (row,) = registry.scalars(select(UserSession)).all()
    assert row.token_hash == hash_token(token) and row.token_hash != token
    assert token not in (row.token_hash, row.created_at, row.expires_at)
    assert row.created_at == "2026-09-13T08:00:00.000Z" and row.expires_at == "2026-09-13T20:00:00.000Z"
    assert len(token) >= 40


def test_the_token_finds_the_user_until_it_expires(service, registry, clock):
    user = register(service, registry)
    _user, token = service.login(registry, email=user.email, password=PASSWORD)
    assert service.user_for_token(registry, token).id == user.id
    clock.advance(hours=11, minutes=59)
    assert service.user_for_token(registry, token) is not None
    clock.advance(minutes=1)
    assert service.user_for_token(registry, token) is None
    assert registry.scalars(select(UserSession)).all() == []


def test_unknown_or_empty_tokens_find_nobody(service, registry):
    register(service, registry)
    assert service.user_for_token(registry, "nonsense") is None
    assert service.user_for_token(registry, "") is None


def test_wrong_password_and_unknown_email_give_the_same_error(service, registry):
    register(service, registry)
    errors = []
    for email, password in (("ada@example.com", "wrong password!"), ("nobody@example.com", PASSWORD)):
        with pytest.raises(AuthError) as caught:
            service.login(registry, email=email, password=password)
        errors.append((caught.value.code, caught.value.detail, caught.value.status_code))
    assert errors[0] == errors[1] == ("invalid_credentials", "Email or password is not correct.", 401)
    assert registry.scalars(select(UserSession)).all() == []


def test_logout_deletes_the_session(service, registry):
    register(service, registry)
    _user, token = service.login(registry, email="ada@example.com", password=PASSWORD)
    service.logout(registry, token)
    assert service.user_for_token(registry, token) is None


def test_two_logins_make_two_independent_sessions(service, registry):
    register(service, registry)
    _u, first = service.login(registry, email="ada@example.com", password=PASSWORD)
    _u, second = service.login(registry, email="ada@example.com", password=PASSWORD)
    assert first != second
    service.logout(registry, first)
    assert service.user_for_token(registry, first) is None
    assert service.user_for_token(registry, second) is not None


def test_a_login_removes_the_expired_sessions_of_that_user(service, registry, clock):
    register(service, registry)
    service.login(registry, email="ada@example.com", password=PASSWORD)
    clock.advance(hours=13)
    service.login(registry, email="ada@example.com", password=PASSWORD)
    assert len(registry.scalars(select(UserSession)).all()) == 1


def test_a_password_hash_with_old_parameters_is_upgraded_at_login(registry, clock):
    old = AuthService(PasswordHasher(time_cost=1, memory_cost=8, parallelism=1), now=clock)
    user = register(old, registry)
    before = user.password_hash
    newer = AuthService(PasswordHasher(time_cost=2, memory_cost=16, parallelism=1), now=clock)
    newer.login(registry, email=user.email, password=PASSWORD)
    registry.refresh(user)
    assert user.password_hash != before and "t=2" in user.password_hash


def test_a_damaged_stored_hash_cannot_be_used_to_sign_in(service, registry):
    user = register(service, registry)
    user.password_hash = "not-a-hash"
    registry.commit()
    with pytest.raises(AuthError):
        service.login(registry, email=user.email, password=PASSWORD)
