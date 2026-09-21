"""Unit tests for the workspace layout. Temporary directories only."""

import pytest

from raven.services.errors import ServiceError
from raven.services.workspace import INVESTIGATIONS_FOLDER, Workspace, resolve_workspace, workspace_dir_name


def test_the_stored_folder_name_is_relative_with_forward_slashes():
    assert workspace_dir_name(7) == "investigations/7"
    assert INVESTIGATIONS_FOLDER == "investigations"


@pytest.mark.parametrize("bad", [0, -1, "1", None, True, 1.5])
def test_only_positive_whole_numbers_name_a_workspace(bad):
    with pytest.raises(ValueError):
        workspace_dir_name(bad)


def test_the_paths_of_a_workspace(tmp_path):
    workspace = Workspace(tmp_path / "investigations" / "3")
    root = workspace.root
    assert workspace.evidence_dir == root / "evidence" and workspace.raw_dir == root / "raw" and workspace.processed_dir == root / "processed"
    assert workspace.db_path == root / "raven.db"
    assert workspace.evidence_path(5) == root / "evidence" / "5.evtx"
    assert workspace.raw_path(5) == root / "raw" / "evidence-5.jsonl"
    assert workspace.normalized_path(5) == root / "processed" / "evidence-5.normalized.jsonl"
    assert workspace.combined_normalized_path == root / "processed" / "normalized.jsonl"
    assert workspace.deduplicated_path == root / "processed" / "deduplicated.jsonl"
    assert workspace.duplicates_path == root / "processed" / "duplicates.jsonl"
    assert workspace.rarf_dir == root / "processed" / "rarf" and workspace.report_dir == root / "processed" / "report"
    assert workspace.summary_path("ingest") == root / "processed" / "ingest.json"


def test_file_paths_are_built_from_numbers_only(tmp_path):
    workspace = Workspace(tmp_path)
    with pytest.raises(ValueError):
        workspace.evidence_path("../../etc/passwd")


def test_ensure_creates_the_three_folders_and_can_run_twice(tmp_path):
    workspace = Workspace(tmp_path / "w").ensure()
    workspace.ensure()
    assert all(p.is_dir() for p in (workspace.evidence_dir, workspace.raw_dir, workspace.processed_dir))


def test_the_database_is_created_in_the_workspace(tmp_path):
    workspace = Workspace(tmp_path / "w").ensure()
    factory = workspace.open_database()
    factory.kw["bind"].dispose()
    assert workspace.db_path.is_file()


def test_a_stored_folder_inside_the_investigations_folder_is_resolved(tmp_path):
    workspace = resolve_workspace(tmp_path, "investigations/4")
    assert workspace.root == (tmp_path / "investigations" / "4").resolve()


@pytest.mark.parametrize("stored", ["investigations", "investigations/..", "../outside", "investigations/../../outside", "other/1", "/etc", "C:/Windows"])
def test_a_stored_folder_outside_the_investigations_folder_is_refused(tmp_path, stored):
    with pytest.raises(ServiceError) as caught:
        resolve_workspace(tmp_path, stored)
    assert (caught.value.status_code, caught.value.code) == (500, "workspace_invalid")
