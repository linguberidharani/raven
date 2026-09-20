"""Unit tests for the shared atomic file helpers. Temporary directories only."""

import pytest

from raven.fileio import write_lines_atomic, write_text_atomic


def test_lines_are_written_with_lf_and_counted(tmp_path):
    path = tmp_path / "deep" / "out.txt"
    assert write_lines_atomic(path, ["a", "b", "c"]) == 3
    assert path.read_bytes() == b"a\nb\nc\n"


def test_no_lines_gives_an_empty_file(tmp_path):
    path = tmp_path / "out.txt"
    assert write_lines_atomic(path, []) == 0
    assert path.read_bytes() == b""


def test_a_failure_keeps_the_previous_file_and_leaves_no_temporary_file(tmp_path):
    path = tmp_path / "out.txt"
    path.write_text("previous\n", encoding="utf-8")

    def lines():
        yield "new"
        raise RuntimeError("source failed")

    with pytest.raises(RuntimeError):
        write_lines_atomic(path, lines())
    assert path.read_text(encoding="utf-8") == "previous\n"
    assert [p.name for p in tmp_path.iterdir()] == ["out.txt"]


def test_text_is_written_as_utf8_with_lf(tmp_path):
    path = tmp_path / "x" / "out.txt"
    write_text_atomic(path, "line one\nÜnï\n")
    assert path.read_bytes() == "line one\nÜnï\n".encode("utf-8")
    assert [p.name for p in path.parent.iterdir()] == ["out.txt"]
