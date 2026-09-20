"""Unit tests for normalized JSONL reading and writing. Synthetic data, temporary directories only."""

import json

import pytest

from raven.parsers.normalized_jsonl import (
    NormalizedEventError,
    read_normalized_jsonl,
    serialize_event,
    write_normalized_jsonl,
)
from raven.parsers.schema import NORMALIZED_FIELDS, STATUS_OK


def make_event(record_id=1, **changes):
    event = {name: None for name in NORMALIZED_FIELDS}
    event.update(
        raw_event_ref=f"1:{record_id}",
        event_id=11,
        event_type="file_create",
        timestamp="2026-09-13T08:39:49.545Z",
        computer="SYNTHETIC-LAB-HOST",
        normalization_status=STATUS_OK,
        file_path="C:\\Test\\a.txt",
    )
    event.update(changes)
    return event


def test_serialize_uses_the_fixed_field_order():
    scrambled = dict(reversed(list(make_event().items())))
    line = serialize_event(scrambled)
    assert list(json.loads(line)) == list(NORMALIZED_FIELDS)
    assert line.startswith('{"raw_event_ref":"1:1","event_id":11,')
    assert "\n" not in line


def test_round_trip_keeps_values_types_and_nulls(tmp_path):
    event = make_event(
        process_id=1224,
        port=47001,
        initiated=True,
        file_path="C:\\Users\\Ünïcödé \u2028 \U0001F600\\a.txt",
    )
    output = tmp_path / "out" / "n.jsonl"
    assert write_normalized_jsonl([event, make_event(2)], output) == 2
    back = list(read_normalized_jsonl(output))
    assert back[0] == event
    assert back[0]["initiated"] is True
    assert back[1]["process_id"] is None


def test_output_is_ascii_with_lf_line_ends(tmp_path):
    output = tmp_path / "n.jsonl"
    write_normalized_jsonl([make_event(file_path="Ünï \u2028 \U0001F600"), make_event(2)], output)
    content = output.read_bytes()
    assert content.isascii()
    assert b"\r" not in content
    assert content.count(b"\n") == 2


def test_writing_twice_gives_identical_bytes(tmp_path):
    events = [make_event(i) for i in range(1, 6)]
    write_normalized_jsonl(events, tmp_path / "a.jsonl")
    write_normalized_jsonl(iter(events), tmp_path / "b.jsonl")
    assert (tmp_path / "a.jsonl").read_bytes() == (tmp_path / "b.jsonl").read_bytes()


def test_an_invalid_event_writes_nothing(tmp_path):
    bad = make_event(2)
    bad["timestamp"] = "yesterday"
    with pytest.raises(NormalizedEventError, match="event 2 is invalid"):
        write_normalized_jsonl([make_event(), bad], tmp_path / "n.jsonl")
    assert list(tmp_path.iterdir()) == []


def test_a_failure_midway_keeps_an_existing_output(tmp_path):
    output = tmp_path / "n.jsonl"
    output.write_text("previous content\n", encoding="utf-8")

    def events():
        yield make_event()
        raise RuntimeError("source failed")

    with pytest.raises(RuntimeError):
        write_normalized_jsonl(events(), output)
    assert output.read_text(encoding="utf-8") == "previous content\n"
    assert [p.name for p in tmp_path.iterdir()] == ["n.jsonl"]


def test_read_reports_bad_lines_with_the_line_number(tmp_path):
    path = tmp_path / "n.jsonl"
    path.write_text(serialize_event(make_event()) + "\n{oops}\n", encoding="utf-8")
    with pytest.raises(NormalizedEventError, match="line 2: invalid JSON"):
        list(read_normalized_jsonl(path))
    path.write_text(serialize_event(make_event()) + "\n\n", encoding="utf-8")
    with pytest.raises(NormalizedEventError, match="line 2: empty line"):
        list(read_normalized_jsonl(path))
    path.write_text('{"event_id": 1}\n', encoding="utf-8")
    with pytest.raises(NormalizedEventError, match="line 1: missing field"):
        list(read_normalized_jsonl(path))


def test_read_accepts_crlf_line_ends(tmp_path):
    path = tmp_path / "n.jsonl"
    line = serialize_event(make_event())
    path.write_bytes((line + "\r\n" + line + "\r\n").encode("ascii"))
    assert len(list(read_normalized_jsonl(path))) == 2
