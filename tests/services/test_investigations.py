"""Unit tests for investigations. Temporary directories only."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import insert

from raven.config import Settings
from raven.database.registry_models import User
from raven.database.session import open_registry_database
from raven.services.errors import ServiceError
from raven.services.investigations import (
    create_investigation,
    evidence_count,
    get_investigation,
    latest_run,
    list_investigations,
    update_investigation,
    validate_description,
    validate_host,
    validate_status,
    validate_title,
    workspace_facts,
)
from raven.services.workspace import Workspace


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, env="test", data_dir=tmp_path / "data")


@pytest.fixture
def registry(tmp_path):
    factory = open_registry_database(tmp_path / "registry.db")
    with factory() as session:
        session.execute(insert(User).values(name="Ada", email="ada@example.com", password_hash="h", created_at="2026-09-13T08:39:49.545Z"))
        session.commit()
        yield session
    factory.kw["bind"].dispose()


def make(registry, settings, title="Case", **kwargs):
    return create_investigation(registry, settings, analyst_id=1, title=title, **kwargs)


def test_validation():
    assert validate_title("  A title ") == "A title"
    for bad in ("", "  ", "x" * 201):
        with pytest.raises(ValueError):
            validate_title(bad)
    assert validate_description(None) is None and validate_description("  ") is None and validate_description(" text ") == "text"
    with pytest.raises(ValueError):
        validate_description("x" * 5001)
    assert validate_host(" HOST-1 ") == "HOST-1" and validate_host(" ") is None
    with pytest.raises(ValueError):
        validate_host("x" * 101)
    assert validate_status("closed") == "closed"
    with pytest.raises(ValueError):
        validate_status("paused")


def test_an_investigation_gets_a_code_a_status_and_a_workspace(registry, settings):
    inv = make(registry, settings, description="About", host="HOST-1", now=datetime(2026, 9, 21, 10, 0, tzinfo=timezone.utc))
    assert inv.code == "INV-2026-001" and inv.status == "open" and inv.analyst_id == 1
    assert (inv.title, inv.description, inv.host) == ("Case", "About", "HOST-1")
    assert inv.created_at == inv.updated_at == "2026-09-21T10:00:00.000Z"
    assert inv.workspace_dir == f"investigations/{inv.id}"
    root = settings.resolved_data_dir / "investigations" / str(inv.id)
    assert (root / "evidence").is_dir() and (root / "raw").is_dir() and (root / "processed").is_dir()


def test_codes_count_within_the_year(registry, settings):
    year_2026 = datetime(2026, 9, 21, tzinfo=timezone.utc)
    year_2027 = datetime(2027, 1, 2, tzinfo=timezone.utc)
    codes = [make(registry, settings, now=year_2026).code, make(registry, settings, now=year_2026).code, make(registry, settings, now=year_2027).code]
    assert codes == ["INV-2026-001", "INV-2026-002", "INV-2027-001"]


def test_a_code_is_not_reused(registry, settings):
    now = datetime(2026, 9, 21, tzinfo=timezone.utc)
    first, second = make(registry, settings, now=now), make(registry, settings, now=now)
    registry.delete(first)
    registry.commit()
    assert make(registry, settings, now=now).code == "INV-2026-003"
    assert second.code == "INV-2026-002"


def test_creation_checks_the_input(registry, settings):
    with pytest.raises(ValueError):
        make(registry, settings, title=" ")


def test_get_and_not_found(registry, settings):
    inv = make(registry, settings)
    assert get_investigation(registry, inv.id).code == inv.code
    with pytest.raises(ServiceError) as caught:
        get_investigation(registry, 999)
    assert (caught.value.status_code, caught.value.code) == (404, "investigation_not_found")


def test_list_is_newest_first_and_paged(registry, settings):
    for number in range(5):
        make(registry, settings, title=f"Case {number}")
    rows, total = list_investigations(registry)
    assert total == 5 and [r.title for r in rows] == [f"Case {n}" for n in (4, 3, 2, 1, 0)]
    rows, total = list_investigations(registry, page=2, page_size=2)
    assert total == 5 and [r.title for r in rows] == ["Case 2", "Case 1"]
    assert list_investigations(registry, page=9, page_size=2)[0] == []


def test_list_filters_by_status_and_text(registry, settings):
    a = make(registry, settings, title="Boot activity", description="Startup review")
    b = make(registry, settings, title="Lab burst")
    update_investigation(registry, b.id, {"status": "closed"})
    assert [r.id for r in list_investigations(registry, status="closed")[0]] == [b.id]
    assert [r.id for r in list_investigations(registry, q="BOOT")[0]] == [a.id]
    assert [r.id for r in list_investigations(registry, q="startup")[0]] == [a.id]
    assert [r.id for r in list_investigations(registry, q=a.code.lower())[0]] == [a.id]
    assert list_investigations(registry, q="nothing")[1] == 0


def test_text_search_treats_wildcards_as_plain_characters(registry, settings):
    make(registry, settings, title="100% sure")
    make(registry, settings, title="other")
    assert [r.title for r in list_investigations(registry, q="%")[0]] == ["100% sure"]
    assert list_investigations(registry, q="_")[1] == 0


def test_update_changes_only_the_given_fields(registry, settings):
    inv = make(registry, settings, description="old", host="H")
    updated = update_investigation(registry, inv.id, {"title": "New", "description": None}, now=datetime(2026, 9, 22, tzinfo=timezone.utc))
    assert (updated.title, updated.description, updated.host, updated.status) == ("New", None, "H", "open")
    assert updated.updated_at == "2026-09-22T00:00:00.000Z" and updated.created_at != updated.updated_at
    with pytest.raises(ValueError):
        update_investigation(registry, inv.id, {"status": "paused"})
    with pytest.raises(ServiceError):
        update_investigation(registry, 999, {"title": "x"})


def test_derived_facts_are_empty_before_an_analysis(tmp_path, registry, settings):
    inv = make(registry, settings)
    facts = workspace_facts(Workspace(settings.resolved_data_dir / "investigations" / str(inv.id)))
    assert (facts.severity, facts.detections, facts.sessions, facts.timeline_events) == (None, 0, 0, 0)
    assert latest_run(registry, inv.id) is None and evidence_count(registry, inv.id) == 0
    empty = Workspace(tmp_path / "nowhere")
    assert workspace_facts(empty).severity is None


def test_derived_facts_of_an_empty_workspace_database(tmp_path):
    workspace = Workspace(tmp_path / "w").ensure()
    factory = workspace.open_database()
    factory.kw["bind"].dispose()
    facts = workspace_facts(workspace)
    assert (facts.severity, facts.detections, facts.sessions, facts.timeline_events) == (None, 0, 0, 0)
