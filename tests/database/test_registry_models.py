"""Unit tests for the registry database schema. Temporary directories only."""

import pytest
from sqlalchemy import insert, inspect, text
from sqlalchemy.exc import IntegrityError

from raven.database.registry_models import REGISTRY_TABLES, Investigation, User, UserSession
from raven.database.session import open_registry_database


@pytest.fixture
def factory(tmp_path):
    factory = open_registry_database(tmp_path / "data" / "registry.db")
    yield factory
    factory.kw["bind"].dispose()


def add_user(factory, email="a@example.com"):
    with factory.kw["bind"].begin() as connection:
        return connection.execute(
            insert(User).values(name="A", email=email, organization=None, password_hash="hash", created_at="2026-09-13T08:39:49.545Z")
        ).inserted_primary_key[0]


def test_the_six_tables_of_the_spec_exist(factory):
    assert set(inspect(factory.kw["bind"]).get_table_names()) == set(REGISTRY_TABLES)
    assert REGISTRY_TABLES == ("users", "sessions", "investigations", "evidence_sources", "analysis_runs", "collector_cursors")


def test_the_columns_follow_the_spec(factory):
    expected = {
        "users": ["id", "name", "email", "organization", "password_hash", "created_at"],
        "sessions": ["id", "user_id", "token_hash", "created_at", "expires_at"],
        "investigations": ["id", "code", "title", "description", "host", "status", "analyst_id", "created_at", "updated_at", "workspace_dir"],
        "evidence_sources": ["id", "investigation_id", "filename", "sha256", "size_bytes", "source_type", "status", "events_total", "error", "created_at", "ingested_at"],
        "analysis_runs": ["id", "investigation_id", "status", "stage", "stages_json", "error", "started_at", "finished_at"],
        "collector_cursors": ["id", "investigation_id", "source_name", "last_offset", "last_record_id", "updated_at"],
    }
    for table, names in expected.items():
        assert [c["name"] for c in inspect(factory.kw["bind"]).get_columns(table)] == names


def test_the_registry_file_and_folder_are_created(tmp_path):
    path = tmp_path / "a" / "b" / "registry.db"
    factory = open_registry_database(path)
    factory.kw["bind"].dispose()
    assert path.is_file()


def test_an_email_is_unique(factory):
    add_user(factory)
    with pytest.raises(IntegrityError):
        add_user(factory)


def test_a_token_hash_is_unique(factory):
    user_id = add_user(factory)
    row = dict(user_id=user_id, token_hash="t", created_at="a", expires_at="b")
    with factory.kw["bind"].begin() as connection:
        connection.execute(insert(UserSession).values(**row))
    with pytest.raises(IntegrityError):
        with factory.kw["bind"].begin() as connection:
            connection.execute(insert(UserSession).values(**row))


def test_foreign_keys_are_enforced(factory):
    with pytest.raises(IntegrityError):
        with factory.kw["bind"].begin() as connection:
            connection.execute(insert(UserSession).values(user_id=99, token_hash="x", created_at="a", expires_at="b"))
    with factory.kw["bind"].connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_an_investigation_status_is_checked(factory):
    user_id = add_user(factory)
    base = dict(code="INV-2026-001", title="t", analyst_id=user_id, created_at="a", updated_at="a", workspace_dir="w")
    with factory.kw["bind"].begin() as connection:
        connection.execute(insert(Investigation).values(status="open", **base))
    with pytest.raises(IntegrityError):
        with factory.kw["bind"].begin() as connection:
            connection.execute(insert(Investigation).values(status="paused", **{**base, "code": "INV-2026-002"}))


def test_opening_twice_keeps_the_data(tmp_path):
    path = tmp_path / "registry.db"
    first = open_registry_database(path)
    add_user(first)
    first.kw["bind"].dispose()
    second = open_registry_database(path)
    with second() as session:
        assert session.query(User).count() == 1
    second.kw["bind"].dispose()
