"""Unit tests for deduplication. Synthetic events, temporary directories only."""

import json

import pytest

from raven.parsers.deduplicate import (
    FINGERPRINT_FIELDS,
    DedupResult,
    count_duplicate_fingerprints,
    deduplicate,
    fingerprint,
    main,
)
from raven.parsers.normalized_jsonl import read_normalized_jsonl, write_normalized_jsonl
from raven.parsers.schema import NORMALIZED_FIELDS, STATUS_OK, STATUS_UNSUPPORTED


def make_event(record_id, **changes):
    event = {name: None for name in NORMALIZED_FIELDS}
    event.update(
        raw_event_ref=f"1:{record_id}",
        event_id=11,
        event_type="file_create",
        timestamp="2026-09-13T08:39:49.545Z",
        computer="SYNTHETIC-LAB-HOST",
        normalization_status=STATUS_OK,
        process_id=1224,
        process_name="C:\\Test\\synthetic.exe",
        file_path="C:\\Test\\a.txt",
    )
    event.update(changes)
    return event


def unsupported(record_id, timestamp="2026-09-13T08:39:49.545Z", event_id=5):
    return make_event(
        record_id,
        event_id=event_id,
        event_type="unsupported",
        normalization_status=STATUS_UNSUPPORTED,
        timestamp=timestamp,
        process_id=None,
        process_name=None,
        file_path=None,
    )


def write(tmp_path, events, name="normalized.jsonl"):
    path = tmp_path / name
    write_normalized_jsonl(events, path)
    return path


# ---------------------------------------------------------------- fingerprint


def test_the_fingerprint_uses_the_26_fields_other_than_raw_event_ref():
    assert len(FINGERPRINT_FIELDS) == 26
    assert "raw_event_ref" not in FINGERPRINT_FIELDS
    assert FINGERPRINT_FIELDS == tuple(name for name in NORMALIZED_FIELDS if name != "raw_event_ref")


def test_a_known_fingerprint_value():
    event = {name: None for name in NORMALIZED_FIELDS}
    event.update(raw_event_ref="1:1", event_id=5, event_type="unsupported", timestamp="2026-01-01T00:00:00.000Z",
                 computer="H", normalization_status="UNSUPPORTED_EVENT_ID")
    # sha256 of the compact JSON list of the 26 values, in field order; recomputed here on purpose
    import hashlib

    values = [event[name] for name in FINGERPRINT_FIELDS]
    text = json.dumps(values, separators=(",", ":"))
    assert fingerprint(event) == hashlib.sha256(text.encode()).hexdigest().upper()
    assert len(fingerprint(event)) == 64


def test_the_reference_does_not_change_the_fingerprint():
    assert fingerprint(make_event(1)) == fingerprint(make_event(2))


@pytest.mark.parametrize(
    "field, value",
    [
        ("timestamp", "2026-09-13T08:39:49.546Z"),
        ("event_id", 3),
        ("process_id", 1225),
        ("file_path", "C:\\Test\\b.txt"),
        ("computer", "OTHER"),
        ("user", "SYNTHETIC\\tester"),
        ("initiated", False),
        ("normalization_status", "INVALID_EVENT_DATA"),
    ],
)
def test_any_other_field_changes_the_fingerprint(field, value):
    assert fingerprint(make_event(1)) != fingerprint(make_event(1, **{field: value}))


def test_null_false_true_and_zero_are_different_values():
    prints = {
        fingerprint(make_event(1)),  # initiated and port are null
        fingerprint(make_event(1, initiated=False)),
        fingerprint(make_event(1, initiated=True)),
        fingerprint(make_event(1, port=0)),
    }
    assert len(prints) == 4


# ---------------------------------------------------------------- deduplicate


def test_duplicates_are_removed_and_the_first_event_is_kept(tmp_path):
    events = [make_event(1), make_event(2, file_path="C:\\Test\\b.txt"), make_event(3), make_event(4), make_event(5, file_path="C:\\Test\\b.txt")]
    source = write(tmp_path, events)
    output = tmp_path / "out" / "dedup.jsonl"
    result = deduplicate(source, output)
    assert result == DedupResult(5, 2, 3)
    assert result == (5, 2, 3)
    assert [e["raw_event_ref"] for e in read_normalized_jsonl(output)] == ["1:1", "1:2"]


def test_the_order_of_the_first_occurrences_is_kept(tmp_path):
    events = [make_event(1, process_id=3), make_event(2, process_id=1), make_event(3, process_id=3), make_event(4, process_id=2)]
    output = tmp_path / "d.jsonl"
    deduplicate(write(tmp_path, events), output)
    assert [e["process_id"] for e in read_normalized_jsonl(output)] == [3, 1, 2]


def test_unsupported_events_with_the_same_id_and_time_are_duplicates_but_others_are_not(tmp_path):
    events = [
        unsupported(1),
        unsupported(2),
        unsupported(3, timestamp="2026-09-13T08:39:49.546Z"),
        unsupported(4, event_id=4),
    ]
    output = tmp_path / "d.jsonl"
    result = deduplicate(write(tmp_path, events), output)
    assert result == (4, 3, 1)


def test_the_duplicates_file_records_every_removal(tmp_path):
    events = [make_event(1), make_event(2), make_event(3, process_id=9), make_event(4)]
    output, side = tmp_path / "d.jsonl", tmp_path / "dups.jsonl"
    deduplicate(write(tmp_path, events), output, side)
    rows = [json.loads(line) for line in side.read_text(encoding="utf-8").splitlines()]
    assert [(r["removed_ref"], r["kept_ref"]) for r in rows] == [("1:2", "1:1"), ("1:4", "1:1")]
    assert all(r["fingerprint"] == fingerprint(make_event(1)) for r in rows)


def test_no_duplicates_gives_an_empty_duplicates_file_and_identical_events(tmp_path):
    events = [make_event(1), make_event(2, process_id=2)]
    source = write(tmp_path, events)
    output, side = tmp_path / "d.jsonl", tmp_path / "dups.jsonl"
    assert deduplicate(source, output, side) == (2, 2, 0)
    assert output.read_bytes() == source.read_bytes()
    assert side.read_bytes() == b""


def test_deduplicating_twice_changes_nothing(tmp_path):
    source = write(tmp_path, [make_event(1), make_event(2), make_event(3, process_id=2)])
    once, twice = tmp_path / "once.jsonl", tmp_path / "twice.jsonl"
    deduplicate(source, once)
    assert deduplicate(once, twice) == (2, 2, 0)
    assert once.read_bytes() == twice.read_bytes()


def test_the_same_input_gives_identical_output_files(tmp_path):
    source = write(tmp_path, [make_event(i, process_id=i % 3) for i in range(1, 20)])
    first, second = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    deduplicate(source, first)
    deduplicate(source, second)
    assert first.read_bytes() == second.read_bytes()


def test_no_duplicate_fingerprints_remain(tmp_path):
    source = write(tmp_path, [make_event(i, process_id=i % 4) for i in range(1, 30)])
    output = tmp_path / "d.jsonl"
    deduplicate(source, output)
    assert count_duplicate_fingerprints(source) == 25
    assert count_duplicate_fingerprints(output) == 0


def test_missing_input(tmp_path):
    with pytest.raises(FileNotFoundError):
        deduplicate(tmp_path / "missing.jsonl", tmp_path / "out.jsonl")


def test_paths_must_differ(tmp_path):
    source = write(tmp_path, [make_event(1)])
    with pytest.raises(ValueError, match="must all differ"):
        deduplicate(source, source)
    with pytest.raises(ValueError, match="must all differ"):
        deduplicate(source, tmp_path / "out.jsonl", tmp_path / "out.jsonl")


def test_an_invalid_input_stops_the_run_and_keeps_previous_outputs(tmp_path):
    source = tmp_path / "bad.jsonl"
    source.write_text('{"event_id": 1}\n', encoding="utf-8")
    output, side = tmp_path / "d.jsonl", tmp_path / "dups.jsonl"
    output.write_text("previous\n", encoding="utf-8")
    with pytest.raises(ValueError):
        deduplicate(source, output, side)
    assert output.read_text(encoding="utf-8") == "previous\n"
    assert not side.exists()


def test_main_prints_the_counts(tmp_path, capsys):
    source = write(tmp_path, [make_event(1), make_event(2), unsupported(3), unsupported(4), make_event(5, process_id=2)])
    output, side = tmp_path / "d.jsonl", tmp_path / "dups.jsonl"
    assert main([str(source), str(output), "--duplicates", str(side)]) == 0
    printed = capsys.readouterr().out
    assert "input events:                5" in printed
    assert "unique events:               3" in printed
    assert "duplicates removed:          2" in printed
    assert "duplicate fingerprints left: 0" in printed
    assert "kept OK: 2" in printed
    assert "kept UNSUPPORTED_EVENT_ID: 1" in printed
    assert "removed OK: 1" in printed
    assert "removed UNSUPPORTED_EVENT_ID: 1" in printed


def test_main_reports_errors(tmp_path, capsys):
    assert main([str(tmp_path / "missing.jsonl"), str(tmp_path / "out.jsonl")]) == 1
    assert "ERROR" in capsys.readouterr().err
