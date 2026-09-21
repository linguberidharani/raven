"""Unit tests for the settings. Temporary files only; RAVEN_* environment variables are cleared first."""

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from raven.config import PROJECT_ROOT, Settings, get_settings


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for name in list(os.environ):
        if name.startswith("RAVEN_"):
            monkeypatch.delenv(name)


def settings(**values):
    return Settings(_env_file=None, **values)


def test_defaults():
    s = settings()
    assert (s.env, s.host, s.port, s.log_level) == ("development", "127.0.0.1", 8000, "INFO")
    assert s.data_dir == Path("data")
    assert (s.max_upload_mb, s.session_hours, s.cookie_secure) == (200, 12, False)
    assert s.inbox_dir == Path("data/inbox") and s.inbox_poll_seconds == 5


def test_environment_variables_override_the_defaults(monkeypatch):
    monkeypatch.setenv("RAVEN_PORT", "9001")
    monkeypatch.setenv("RAVEN_SESSION_HOURS", "2")
    monkeypatch.setenv("RAVEN_COOKIE_SECURE", "true")
    s = settings()
    assert (s.port, s.session_hours, s.cookie_secure) == (9001, 2, True)


def test_the_env_file_is_read_and_the_environment_wins(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("RAVEN_PORT=8123\nRAVEN_LOG_LEVEL=debug\nUNRELATED=1\n", encoding="utf-8")
    from_file = Settings(_env_file=env_file)
    assert from_file.port == 8123 and from_file.log_level == "DEBUG"
    monkeypatch.setenv("RAVEN_PORT", "8999")
    assert Settings(_env_file=env_file).port == 8999


def test_the_log_level_is_case_insensitive_and_checked():
    assert settings(log_level="warning").log_level == "WARNING"
    with pytest.raises(ValidationError):
        settings(log_level="LOUD")


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_loopback_hosts_are_accepted(host):
    assert settings(host=host).host == host


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.5", "example.com"])
def test_other_hosts_are_rejected(host):
    with pytest.raises(ValidationError, match="loopback"):
        settings(host=host)


@pytest.mark.parametrize("field, value", [("port", 0), ("port", 70000), ("max_upload_mb", 0), ("session_hours", 0), ("env", "staging")])
def test_out_of_range_values_are_rejected(field, value):
    with pytest.raises(ValidationError):
        settings(**{field: value})


def test_paths_are_resolved_against_the_project_root(tmp_path):
    assert settings().resolved_data_dir == PROJECT_ROOT / "data"
    assert settings(data_dir=tmp_path).resolved_data_dir == tmp_path
    assert settings(data_dir=tmp_path).registry_path == tmp_path / "registry.db"


def test_the_inbox_folder_is_resolved_against_the_project_root(tmp_path):
    assert settings().resolved_inbox_dir == PROJECT_ROOT / "data" / "inbox"
    assert settings(inbox_dir=tmp_path / "in").resolved_inbox_dir == tmp_path / "in"


@pytest.mark.parametrize("value", [-1, 3601])
def test_the_poll_interval_is_checked(value):
    with pytest.raises(ValidationError):
        settings(inbox_poll_seconds=value)
    assert settings(inbox_poll_seconds=0).inbox_poll_seconds == 0


def test_derived_values():
    s = settings(max_upload_mb=3)
    assert s.max_upload_bytes == 3 * 1024 * 1024
    assert settings(env="development").docs_enabled is True
    assert settings(env="production").docs_enabled is False
    assert settings(env="test").docs_enabled is False


def test_get_settings_is_read_once():
    get_settings.cache_clear()
    assert get_settings() is get_settings()
    get_settings.cache_clear()
