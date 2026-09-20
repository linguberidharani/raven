"""Unit tests for raw JSONL reading and writing. Synthetic data, temporary directories only."""

import json

import pytest

from raven.collectors.raw_jsonl import (
    RawRecordError,
    main,
    read_raw_jsonl,
    serialize_record,
    sha256_file,
    summarize_raw_jsonl,
    write_raw_jsonl,
)
from raven.collectors.raw_schema import RAW_FIELDS


def make_record(record_id=1, event_id=1, computer="SYNTHETIC-LAB-HOST", stamp="2020-01-01 00:00:00.000000+00:00", **data):
    return {
        "event_id": event_id,
        "time_created": stamp,
        "computer": computer,
        "record_id": record_id,
        "event_data": data or {"Image": "C:\\Test\\synthetic.exe"},
        "raw_xml": f"<Event>{record_id}</Event>",
    }


def test_serialize_uses_the_fixed_field_order_and_compact_separators():
    scrambled = dict(reversed(list(make_record().items())))
    line = serialize_record(scrambled)
    assert list(json.loads(line)) == list(RAW_FIELDS)
    assert line.startswith('{"event_id":1,"time_created":')
    assert ", " not in line.split('"raw_xml"')[0]
    assert "\n" not in line


def test_round_trip_keeps_every_value(tmp_path):
    tricky = make_record(
        Text="Ünïcödé \u2028 \U0001F600 tab\t newline\n carriage\r quote\" backslash\\",
        Empty="",
    )
    tricky["raw_xml"] = "<Event>line one\nline two\r\n</Event>\n"
    output = tmp_path / "out" / "raw.jsonl"
    assert write_raw_jsonl([tricky, make_record(record_id=2)], output) == 2
    assert list(read_raw_jsonl(output))[0] == tricky
    assert len(list(read_raw_jsonl(output))) == 2


def test_output_is_ascii_with_lf_line_ends_and_one_line_per_record(tmp_path):
    output = tmp_path / "raw.jsonl"
    record = make_record(Text="Ünï \u2028 \U0001F600")
    record["raw_xml"] = "a\r\nb\nc"
    write_raw_jsonl([record, make_record(record_id=2)], output)
    content = output.read_bytes()
    assert content.isascii()
    assert b"\r" not in content
    assert content.count(b"\n") == 2
    assert content.endswith(b"\n")


def test_writing_twice_gives_identical_bytes(tmp_path):
    records = [make_record(record_id=i) for i in range(1, 6)]
    first, second = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    write_raw_jsonl(records, first)
    write_raw_jsonl(iter(records), second)
    assert first.read_bytes() == second.read_bytes()
    assert sha256_file(first) == sha256_file(second)


def test_an_invalid_record_writes_nothing(tmp_path):
    output = tmp_path / "raw.jsonl"
    bad = make_record(record_id=2)
    del bad["raw_xml"]
    with pytest.raises(RawRecordError, match="record 2 is invalid"):
        write_raw_jsonl([make_record(), bad], output)
    assert list(tmp_path.iterdir()) == []


def test_a_failure_midway_leaves_an_existing_output_untouched(tmp_path):
    output = tmp_path / "raw.jsonl"
    output.write_text("previous content\n", encoding="utf-8")

    def records():
        yield make_record()
        raise RuntimeError("source failed")

    with pytest.raises(RuntimeError, match="source failed"):
        write_raw_jsonl(records(), output)
    assert output.read_text(encoding="utf-8") == "previous content\n"
    assert [p.name for p in tmp_path.iterdir()] == ["raw.jsonl"]


def test_an_existing_output_is_replaced_on_success(tmp_path):
    output = tmp_path / "raw.jsonl"
    output.write_text("old\n", encoding="utf-8")
    write_raw_jsonl([make_record()], output)
    assert len(list(read_raw_jsonl(output))) == 1


def test_read_reports_invalid_json_with_the_line_number(tmp_path):
    path = tmp_path / "raw.jsonl"
    path.write_text(serialize_record(make_record()) + "\n{not json}\n", encoding="utf-8")
    with pytest.raises(RawRecordError, match="line 2: invalid JSON"):
        list(read_raw_jsonl(path))


def test_read_reports_an_empty_line(tmp_path):
    path = tmp_path / "raw.jsonl"
    path.write_text(serialize_record(make_record()) + "\n\n", encoding="utf-8")
    with pytest.raises(RawRecordError, match="line 2: empty line"):
        list(read_raw_jsonl(path))


def test_read_reports_an_invalid_record(tmp_path):
    path = tmp_path / "raw.jsonl"
    path.write_text('{"event_id": 1}\n', encoding="utf-8")
    with pytest.raises(RawRecordError, match="line 1: missing field"):
        list(read_raw_jsonl(path))


def test_read_accepts_crlf_line_ends(tmp_path):
    path = tmp_path / "raw.jsonl"
    line = serialize_record(make_record())
    path.write_bytes((line + "\r\n" + line + "\r\n").encode("ascii"))
    assert len(list(read_raw_jsonl(path))) == 2


def test_sha256_of_a_known_value(tmp_path):
    path = tmp_path / "abc.bin"
    path.write_bytes(b"abc")
    assert sha256_file(path) == "BA7816BF8F01CFEA414140DE5DAE2223B00361A396177A9CB410FF61F20015AD"


def test_summary_counts(tmp_path):
    path = tmp_path / "raw.jsonl"
    write_raw_jsonl(
        [
            make_record(1, event_id=1, stamp="2020-01-01 00:00:02.000000+00:00"),
            make_record(2, event_id=11, stamp="2020-01-01 00:00:01.000000+00:00"),
            make_record(3, event_id=11, computer="OTHER", stamp="2020-01-01 00:00:03.000000+00:00"),
            make_record(3, event_id=5, stamp="2020-01-01 00:00:04.000000+00:00"),
        ],
        path,
    )
    summary = summarize_raw_jsonl(path)
    assert summary == {
        "records": 4,
        "unique_record_ids": 3,
        "event_id_counts": {1: 1, 5: 1, 11: 2},
        "computers": ["OTHER", "SYNTHETIC-LAB-HOST"],
        "first_time_created": "2020-01-01 00:00:01.000000+00:00",
        "last_time_created": "2020-01-01 00:00:04.000000+00:00",
    }


def test_main_prints_the_counts(tmp_path, capsys):
    path = tmp_path / "raw.jsonl"
    write_raw_jsonl([make_record(1, event_id=1), make_record(2, event_id=11)], path)
    assert main([str(path)]) == 0
    printed = capsys.readouterr().out
    assert "records:            2" in printed
    assert "event 1: 1" in printed
    assert "event 11: 1" in printed
    assert sha256_file(path) in printed


def test_main_reports_an_invalid_file(tmp_path, capsys):
    path = tmp_path / "raw.jsonl"
    path.write_text("nonsense\n", encoding="utf-8")
    assert main([str(path)]) == 1
    assert "ERROR" in capsys.readouterr().err
    assert main([str(tmp_path / "missing.jsonl")]) == 1
