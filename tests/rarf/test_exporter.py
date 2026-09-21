"""Unit tests for exporting RARF files. Synthetic events, temporary directories only."""

import json

import pytest

from raven.rarf.builder import RarfError
from raven.rarf import exporter
from raven.rarf.exporter import export_rarf, main, rarf_text
from raven.rarf.schema import validate_rarf

from tests.rarf.conftest import prepare_workspace, rows_for


def test_one_file_per_session_named_after_the_session(factory, tmp_path):
    prepare_workspace(factory, rows_for(10, 0) + rows_for(20, 5000, first_number=100))
    exported = export_rarf(factory, tmp_path / "out")
    assert len(exported) == 2
    names = sorted(p.name for p in (tmp_path / "out").iterdir())
    assert names == sorted(f"RARF-{item.session_id}.json" for item in exported)
    assert all(name.startswith("RARF-RAVEN-SESSION-Dharani-") and name.endswith(".json") for name in names)


def test_the_files_are_valid_json_and_valid_rarf(factory, tmp_path):
    prepare_workspace(factory, rows_for(10, 0))
    (item,) = export_rarf(factory, tmp_path / "out")
    document = json.loads(item.path.read_text(encoding="utf-8"))
    assert document == item.document
    assert validate_rarf(document) == []


def test_the_text_is_deterministic_ascii_with_lf_line_ends(factory, tmp_path):
    prepare_workspace(factory, rows_for(10, 0))
    (item,) = export_rarf(factory, tmp_path / "out")
    content = item.path.read_bytes()
    assert content.isascii() and b"\r" not in content and content.endswith(b"}\n")
    assert content == rarf_text(item.document).encode("ascii")
    assert content.startswith(b'{\n  "rarf_version": "1.0",\n  "rarf_id": "RARF-RAVEN-SESSION-Dharani-')


def test_exporting_twice_gives_byte_identical_files(factory, tmp_path):
    prepare_workspace(factory, rows_for(10, 0))
    (first,) = export_rarf(factory, tmp_path / "a")
    (second,) = export_rarf(factory, tmp_path / "b")
    assert first.path.read_bytes() == second.path.read_bytes()
    export_rarf(factory, tmp_path / "a")
    assert first.path.read_bytes() == second.path.read_bytes()


def test_the_file_contains_no_generation_time(factory, tmp_path):
    prepare_workspace(factory, rows_for(10, 0))
    (item,) = export_rarf(factory, tmp_path / "out")
    assert "generated" not in item.path.read_text(encoding="utf-8")


def test_an_invalid_document_is_not_written(factory, tmp_path, monkeypatch):
    prepare_workspace(factory, rows_for(10, 0))
    monkeypatch.setattr(exporter, "validate_rarf", lambda document: ["something is wrong"])
    with pytest.raises(RarfError, match="not valid: something is wrong"):
        export_rarf(factory, tmp_path / "out")
    assert not (tmp_path / "out").exists() or list((tmp_path / "out").iterdir()) == []


def test_no_sessions_no_files(factory, tmp_path):
    assert export_rarf(factory, tmp_path / "out") == []


def test_main_prints_the_counts(factory, tmp_path, capsys):
    prepare_workspace(factory, rows_for(10, 0))
    assert main([str(tmp_path / "workspace" / "raven.db"), str(tmp_path / "out")]) == 0
    printed = capsys.readouterr().out
    assert "RARF files written: 1" in printed
    assert "  validation: valid" in printed
    assert "  timeline events: 11" in printed
    assert "  impact files_affected: score 3, events 10" in printed
    assert "event_ids 11, raw_event_refs 11, correlation_group_ids 2, timeline_event_ids 11, impact_analysis_ids 4" in printed
    assert "  sha256:" in printed


def test_main_reports_errors(tmp_path, capsys):
    assert main([str(tmp_path / "missing.db"), str(tmp_path / "out")]) == 1
    assert "ERROR" in capsys.readouterr().err
