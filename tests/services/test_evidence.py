"""Unit tests for evidence upload and listing. Temporary directories only; SYNTHETIC fake EVTX bytes."""

import hashlib
import io

import pytest
from sqlalchemy import insert

from raven.config import Settings
from raven.database.registry_models import User
from raven.database.session import open_registry_database
from raven.services.errors import ServiceError
from raven.services.evidence import EVTX_SIGNATURE, clean_filename, event_breakdown, list_evidence, save_upload
from raven.services.investigations import create_investigation
from raven.services.workspace import Workspace
from tests.synthetic import evtx_bytes


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, env="test", data_dir=tmp_path / "data", max_upload_mb=1)


@pytest.fixture
def registry(tmp_path):
    factory = open_registry_database(tmp_path / "registry.db")
    with factory() as session:
        session.execute(insert(User).values(name="Ada", email="ada@example.com", password_hash="h", created_at="2026-09-13T08:39:49.545Z"))
        session.commit()
        yield session
    factory.kw["bind"].dispose()


@pytest.fixture
def investigation(registry, settings):
    return create_investigation(registry, settings, analyst_id=1, title="Case")


def upload(registry, settings, investigation, data=None, name="Sysmon export.evtx"):
    return save_upload(registry, settings, investigation.id, name, io.BytesIO(evtx_bytes() if data is None else data))


def workspace_of(settings, investigation):
    return Workspace(settings.resolved_data_dir / "investigations" / str(investigation.id))


# ---------------------------------------------------------------- file names


@pytest.mark.parametrize(
    "given, shown",
    [
        ("Sysmon export.evtx", "Sysmon export.evtx"),
        ("C:\\Users\\me\\Downloads\\log.EVTX", "log.EVTX"),
        ("../../etc/passwd.evtx", "passwd.evtx"),
        ("..\\..\\windows\\evil.evtx", "evil.evtx"),
        ("  spaced.evtx  ", "spaced.evtx"),
    ],
)
def test_only_the_last_part_of_a_name_is_kept(given, shown):
    assert clean_filename(given) == shown


@pytest.mark.parametrize("bad", [None, "", "   ", "dir/", "x" * 252 + ".evtx", "bad\x00name.evtx", "tab\tname.evtx"])
def test_unusable_names_are_refused(bad):
    with pytest.raises(ServiceError) as caught:
        clean_filename(bad)
    assert (caught.value.status_code, caught.value.code) == (422, "invalid_filename")


@pytest.mark.parametrize("bad", ["log.txt", "log.evtx.exe", "log", "evtx", "log.evt"])
def test_only_evtx_files_are_accepted(bad):
    with pytest.raises(ServiceError) as caught:
        clean_filename(bad)
    assert (caught.value.status_code, caught.value.code) == (422, "invalid_file_type")


# ---------------------------------------------------------------- upload


def test_an_upload_is_stored_hashed_and_recorded(registry, settings, investigation):
    data = evtx_bytes(1)
    evidence = upload(registry, settings, investigation, data)
    assert evidence.sha256 == hashlib.sha256(data).hexdigest().upper()
    assert evidence.size_bytes == len(data) and evidence.filename == "Sysmon export.evtx"
    assert (evidence.source_type, evidence.status, evidence.events_total, evidence.error, evidence.ingested_at) == ("evtx_upload", "uploaded", 0, None, None)
    stored = workspace_of(settings, investigation).evidence_path(evidence.id)
    assert stored.read_bytes() == data
    assert stored.name == f"{evidence.id}.evtx"


def test_the_uploaded_name_never_becomes_a_path(registry, settings, investigation):
    evidence = upload(registry, settings, investigation, name="..\\..\\escape.evtx")
    workspace = workspace_of(settings, investigation)
    assert evidence.filename == "escape.evtx"
    assert sorted(p.name for p in workspace.evidence_dir.iterdir()) == [f"{evidence.id}.evtx"]
    assert not list(settings.resolved_data_dir.rglob("escape*"))


def test_no_part_file_is_left_behind(registry, settings, investigation):
    upload(registry, settings, investigation)
    assert not list(workspace_of(settings, investigation).evidence_dir.glob("*.part"))


def test_the_same_content_twice_is_refused_but_other_content_is_fine(registry, settings, investigation):
    upload(registry, settings, investigation, evtx_bytes(1))
    with pytest.raises(ServiceError) as caught:
        upload(registry, settings, investigation, evtx_bytes(1), name="copy.evtx")
    assert (caught.value.status_code, caught.value.code) == (409, "duplicate_evidence")
    upload(registry, settings, investigation, evtx_bytes(2), name="other.evtx")
    assert len(list_evidence(registry, investigation.id)) == 2
    assert len(list(workspace_of(settings, investigation).evidence_dir.iterdir())) == 2


def test_the_same_content_in_another_investigation_is_allowed(registry, settings, investigation):
    other = create_investigation(registry, settings, analyst_id=1, title="Other")
    upload(registry, settings, investigation, evtx_bytes(1))
    assert upload(registry, settings, other, evtx_bytes(1)).investigation_id == other.id


def test_a_file_over_the_limit_is_refused_and_removed(registry, settings, investigation):
    data = EVTX_SIGNATURE + bytes(1024 * 1024 + 10)
    with pytest.raises(ServiceError) as caught:
        upload(registry, settings, investigation, data)
    assert (caught.value.status_code, caught.value.code) == (413, "file_too_large")
    assert list(workspace_of(settings, investigation).evidence_dir.iterdir()) == []
    assert list_evidence(registry, investigation.id) == []


def test_a_file_exactly_at_the_limit_is_accepted(registry, settings, investigation):
    data = EVTX_SIGNATURE + bytes(1024 * 1024 - len(EVTX_SIGNATURE))
    assert upload(registry, settings, investigation, data).size_bytes == 1024 * 1024


@pytest.mark.parametrize(
    "data",
    [b"", b"not an evtx file" * 400, EVTX_SIGNATURE, EVTX_SIGNATURE + bytes(100), b"ElfFil" + bytes(8192)],
    ids=["empty", "text", "signature only", "too short", "wrong signature"],
)
def test_a_file_that_is_not_an_evtx_file_is_refused(registry, settings, investigation, data):
    with pytest.raises(ServiceError) as caught:
        upload(registry, settings, investigation, data)
    assert (caught.value.status_code, caught.value.code) == (422, "invalid_evtx")
    assert list(workspace_of(settings, investigation).evidence_dir.iterdir()) == []
    assert list_evidence(registry, investigation.id) == []


def test_an_upload_for_an_unknown_investigation_is_refused(registry, settings):
    with pytest.raises(ServiceError) as caught:
        save_upload(registry, settings, 999, "a.evtx", io.BytesIO(evtx_bytes()))
    assert caught.value.status_code == 404


def test_an_upload_updates_the_investigation_time(registry, settings, investigation):
    before = investigation.updated_at
    evidence = upload(registry, settings, investigation)
    registry.refresh(investigation)
    assert investigation.updated_at == evidence.created_at and investigation.updated_at >= before


def test_the_list_is_in_upload_order(registry, settings, investigation):
    a = upload(registry, settings, investigation, evtx_bytes(1), name="a.evtx")
    b = upload(registry, settings, investigation, evtx_bytes(2), name="b.evtx")
    assert [e.id for e in list_evidence(registry, investigation.id)] == [a.id, b.id]
    with pytest.raises(ServiceError):
        list_evidence(registry, 999)


def test_the_event_breakdown_is_empty_without_events(tmp_path):
    assert event_breakdown(Workspace(tmp_path / "nowhere")) == []
    workspace = Workspace(tmp_path / "w").ensure()
    workspace.open_database().kw["bind"].dispose()
    assert event_breakdown(workspace) == []
