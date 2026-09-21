"""Unit tests for reading collector files. Temporary directories and SYNTHETIC records only."""

import json

import pytest

from raven.collectors.inbox import InboxError, main, read_new_records, valid_source_name
from tests.synthetic import raw_lines, synthetic_raw_records

RECORDS = synthetic_raw_records(1)


def write(path, text, mode="w"):
    with open(path, mode, encoding="utf-8", newline="") as handle:
        handle.write(text)


@pytest.mark.parametrize("name", ["sysmon-Dharani.jsonl", "a.jsonl", "S.Y_S-1.jsonl", "x" * 92 + ".jsonl"])
def test_plain_jsonl_names_are_valid(name):
    assert valid_source_name(name)


@pytest.mark.parametrize(
    "name",
    ["", ".jsonl", "log.txt", "log.jsonl.exe", "../log.jsonl", "a/b.jsonl", "a\\b.jsonl", "a b.jsonl", "-x.jsonl", "a..b.jsonl", "x" * 101 + ".jsonl", None, 5, "log.JSONL"],
)
def test_other_names_are_not(name):
    assert not valid_source_name(name)


def test_all_complete_lines_are_read_and_the_offset_moves_to_the_end(tmp_path):
    path = tmp_path / "s.jsonl"
    text = raw_lines(RECORDS)
    write(path, text)
    result = read_new_records(path, 0)
    assert [r["record_id"] for r in result.records] == list(range(1, 14))
    assert (result.rejected, result.rejected_count, result.new_offset) == ([], 0, len(text.encode()))


def test_only_the_bytes_after_the_offset_are_read(tmp_path):
    path = tmp_path / "s.jsonl"
    first, second = raw_lines(RECORDS[:4]), raw_lines(RECORDS[4:])
    write(path, first)
    one = read_new_records(path, 0)
    write(path, second, "a")
    two = read_new_records(path, one.new_offset)
    assert [r["record_id"] for r in one.records] == [1, 2, 3, 4] and [r["record_id"] for r in two.records] == list(range(5, 14))
    assert two.new_offset == len((first + second).encode())
    assert read_new_records(path, two.new_offset).records == []


def test_a_line_that_is_still_being_written_waits(tmp_path):
    path = tmp_path / "s.jsonl"
    text = raw_lines(RECORDS[:3])
    partial = raw_lines(RECORDS[3:4]).rstrip("\n")[:40]
    write(path, text + partial)
    first = read_new_records(path, 0)
    assert [r["record_id"] for r in first.records] == [1, 2, 3] and first.new_offset == len(text.encode())
    write(path, raw_lines(RECORDS[3:4]).rstrip("\n")[40:] + "\n", "a")
    second = read_new_records(path, first.new_offset)
    assert [r["record_id"] for r in second.records] == [4]


def test_a_file_with_only_a_partial_line_gives_nothing_yet(tmp_path):
    path = tmp_path / "s.jsonl"
    write(path, raw_lines(RECORDS[:1]).rstrip("\n"))
    result = read_new_records(path, 0)
    assert result.records == [] and result.new_offset == 0


def test_an_empty_file_gives_nothing(tmp_path):
    path = tmp_path / "s.jsonl"
    write(path, "")
    assert read_new_records(path, 0).records == []


def test_a_byte_order_mark_and_windows_line_ends_are_accepted(tmp_path):
    path = tmp_path / "s.jsonl"
    body = raw_lines(RECORDS[:3]).replace("\n", "\r\n")
    path.write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))
    result = read_new_records(path, 0)
    assert [r["record_id"] for r in result.records] == [1, 2, 3] and result.rejected_count == 0


def test_blank_lines_are_skipped_without_being_counted_as_rejected(tmp_path):
    path = tmp_path / "s.jsonl"
    write(path, "\n" + raw_lines(RECORDS[:2]) + "   \n\n")
    result = read_new_records(path, 0)
    assert len(result.records) == 2 and result.rejected_count == 0


def test_bad_lines_are_rejected_with_a_reason_and_do_not_stop_the_good_ones(tmp_path):
    path = tmp_path / "s.jsonl"
    good = raw_lines(RECORDS[:2])
    broken_json = "{oops\n"
    missing_field = json.dumps({k: v for k, v in RECORDS[2].items() if k != "raw_xml"}) + "\n"
    extra_field = json.dumps({**RECORDS[3], "extra": 1}) + "\n"
    not_an_object = "[1,2,3]\n"
    bad_bytes = b"\xff\xfe\xfa\n"
    path.write_bytes(good.encode() + broken_json.encode() + missing_field.encode() + extra_field.encode() + not_an_object.encode() + bad_bytes + raw_lines(RECORDS[4:5]).encode())
    result = read_new_records(path, 0)
    assert [r["record_id"] for r in result.records] == [1, 2, 5]
    assert result.rejected_count == 5
    assert "not valid JSON" in result.rejected[0] and "missing field: raw_xml" in result.rejected[1] and "unexpected field: extra" in result.rejected[2]
    assert "expected an object" in result.rejected[3] and "not valid UTF-8" in result.rejected[4]
    assert result.rejected[0].startswith(f"line at byte {len(good.encode())}:")


def test_only_the_first_rejected_messages_are_kept(tmp_path):
    path = tmp_path / "s.jsonl"
    write(path, "{bad\n" * 50)
    result = read_new_records(path, 0)
    assert result.rejected_count == 50 and len(result.rejected) == 20


def test_a_file_shorter_than_the_saved_offset_is_an_error(tmp_path):
    path = tmp_path / "s.jsonl"
    write(path, raw_lines(RECORDS[:2]))
    with pytest.raises(InboxError, match="smaller than the saved position"):
        read_new_records(path, 10**6)


def test_a_negative_offset_is_an_error(tmp_path):
    path = tmp_path / "s.jsonl"
    write(path, "")
    with pytest.raises(InboxError):
        read_new_records(path, -1)


def test_a_line_longer_than_the_chunk_is_an_error(tmp_path):
    path = tmp_path / "s.jsonl"
    write(path, "x" * 5000)
    with pytest.raises(InboxError, match="longer than"):
        read_new_records(path, 0, max_bytes=1000)


def test_a_chunk_that_ends_inside_a_line_leaves_that_line_for_the_next_read(tmp_path):
    path = tmp_path / "s.jsonl"
    text = raw_lines(RECORDS[:6])
    write(path, text)
    size = len(raw_lines(RECORDS[:3]).encode())
    first = read_new_records(path, 0, max_bytes=size + 5)
    assert [r["record_id"] for r in first.records] == [1, 2, 3]
    rest = read_new_records(path, first.new_offset)
    assert [r["record_id"] for r in rest.records] == [4, 5, 6]


def test_a_missing_file_is_an_error(tmp_path):
    with pytest.raises(OSError):
        read_new_records(tmp_path / "missing.jsonl", 0)


def test_main_reports_a_good_and_a_damaged_file(tmp_path, capsys):
    good = tmp_path / "good.jsonl"
    write(good, raw_lines(RECORDS))
    assert main([str(good)]) == 0
    printed = capsys.readouterr().out
    assert "valid records: 13" in printed and "rejected lines: 0" in printed and "record ids: 1 to 13" in printed
    bad = tmp_path / "bad.jsonl"
    write(bad, raw_lines(RECORDS[:2]) + "{oops\n")
    assert main([str(bad)]) == 2
    assert "rejected lines: 1" in capsys.readouterr().out
    assert main([str(tmp_path / "missing.jsonl")]) == 1
