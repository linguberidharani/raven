"""Unit tests for the helpers of the read layer. Temporary directories and SYNTHETIC data only."""

import json
import sqlite3

import pytest

from raven.services.readers import (
    _bucket_seconds,
    _process_tree,
    artifact_path,
    group_match_value,
    raw_record,
    read_session,
)
from raven.services.workspace import Workspace


def test_group_match_value():
    assert group_match_value("RAVEN-R001:1224:2026-09-13T08:39:49.695Z") == "1224"
    assert group_match_value("RAVEN-R003:4:2026-09-13T08:39:49.545Z") == "4"
    assert group_match_value("nonsense") == ""


@pytest.mark.parametrize("span, size", [(0, 10), (200, 10), (4000, 10), (4001, 60), (24000, 60), (24001, 600), (240000, 600), (240001, 3600), (10**7, 3600)])
def test_bucket_sizes_keep_the_chart_small(span, size):
    assert _bucket_seconds(span) == size


def make_event(event_id, guid, pid, image, event_type, timestamp, parent=None):
    event = {
        "id": event_id, "process_guid": guid, "process_id": pid, "process_name": image, "user": "U", "event_type": event_type,
        "timestamp": timestamp, "parent_process_guid": None, "parent_process_id": None, "parent_process_name": None,
    }
    if parent:
        event.update(parent_process_guid=parent[0], parent_process_id=parent[1], parent_process_name=parent[2])
    return event


def test_the_process_tree_links_children_to_parents_and_adds_parents_as_stubs():
    events = [
        make_event(1, "{c}", 20, "child.exe", "process_creation", "2026-09-13T08:00:02.000Z", parent=("{p}", 10, "parent.exe")),
        make_event(2, "{c}", 20, "child.exe", "file_create", "2026-09-13T08:00:03.000Z"),
        make_event(3, "{s}", 4, "System", "file_create", "2026-09-13T08:00:01.000Z"),
        make_event(4, "{c}", 20, "child.exe", "file_create", "2026-09-13T08:00:04.000Z"),
    ]
    tree = _process_tree(events, {1: ["g1"], 2: ["g1", "g2"], 3: ["g3"], 4: ["g2"]})
    nodes = {n["process_guid"]: n for n in tree["nodes"]}
    assert set(nodes) == {"{c}", "{p}", "{s}"}
    assert nodes["{c}"]["event_counts"] == {"process_creation": 1, "file_create": 2} and nodes["{c}"]["group_ids"] == ["g1", "g2"]
    assert nodes["{c}"]["parent_process_guid"] == "{p}" and nodes["{c}"]["in_session"] is True
    assert nodes["{p}"]["in_session"] is False and nodes["{p}"]["image"] == "parent.exe" and nodes["{p}"]["process_id"] == 10
    assert nodes["{p}"]["child_guids"] == ["{c}"] and nodes["{p}"]["first_seen"] is None
    assert nodes["{s}"]["parent_process_guid"] is None and nodes["{s}"]["in_session"] is True
    assert set(tree["roots"]) == {"{p}", "{s}"}
    assert all(n["basis"] == "observed" for n in tree["nodes"])
    assert [n["process_guid"] for n in tree["nodes"]][0] == "{s}"  # seen first; stubs come last


def test_events_without_a_process_guid_are_left_out_of_the_tree():
    events = [make_event(1, None, None, None, "file_create", "2026-09-13T08:00:01.000Z")]
    assert _process_tree(events, {}) == {"nodes": [], "roots": []}


def test_a_process_that_is_its_own_known_parent_is_not_a_root():
    events = [
        make_event(1, "{p}", 10, "parent.exe", "process_creation", "2026-09-13T08:00:01.000Z"),
        make_event(2, "{c}", 20, "child.exe", "process_creation", "2026-09-13T08:00:02.000Z", parent=("{p}", 10, "parent.exe")),
    ]
    tree = _process_tree(events, {})
    assert tree["roots"] == ["{p}"]
    assert [n for n in tree["nodes"] if n["process_guid"] == "{p}"][0]["child_guids"] == ["{c}"]


def write_raw(path, ids):
    path.write_text("".join(json.dumps({"event_id": 11, "time_created": "t", "computer": "c", "record_id": i, "event_data": {}, "raw_xml": "<x/>"}, separators=(",", ":")) + "\n" for i in ids), encoding="utf-8")


def test_a_raw_record_is_found_by_its_exact_record_id(tmp_path):
    path = tmp_path / "raw.jsonl"
    write_raw(path, [1, 11, 111, 1000])
    assert raw_record(path, 1)["record_id"] == 1
    assert raw_record(path, 11)["record_id"] == 11
    assert raw_record(path, 111)["record_id"] == 111
    assert raw_record(path, 2) is None
    assert raw_record(path, 10) is None


def test_a_missing_raw_file_gives_none(tmp_path):
    assert raw_record(tmp_path / "missing.jsonl", 1) is None


def test_a_workspace_without_a_database_gives_no_session(tmp_path):
    with read_session(Workspace(tmp_path / "w")) as session:
        assert session is None


def test_the_read_session_cannot_write(tmp_path):
    workspace = Workspace(tmp_path / "w").ensure()
    workspace.open_database().kw["bind"].dispose()
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    with read_session(workspace) as session:
        assert session.execute(text("SELECT COUNT(*) FROM events")).scalar() == 0
        with pytest.raises(OperationalError):
            session.execute(text("DELETE FROM events"))
    connection = sqlite3.connect(workspace.db_path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
    finally:
        connection.close()


def test_an_artifact_is_only_found_by_comparing_names(tmp_path):
    folder = tmp_path / "rarf"
    folder.mkdir()
    (folder / "RARF-SESSION-A.json").write_text("{}", encoding="utf-8")
    assert artifact_path(folder, "RARF", "SESSION-A") == folder / "RARF-SESSION-A.json"
    assert artifact_path(folder, "RARF", "SESSION-B") is None
    assert artifact_path(folder, "RARF", "../SESSION-A") is None
    assert artifact_path(folder, "RARF", "*") is None
    assert artifact_path(tmp_path / "missing", "RARF", "SESSION-A") is None
