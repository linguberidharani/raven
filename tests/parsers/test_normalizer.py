"""Unit tests for the normalizer.

All raw records below are SYNTHETIC test data built in this file. They are not real telemetry.
Only temporary directories are used.
"""

import pytest

from raven.collectors.raw_jsonl import write_raw_jsonl
from raven.parsers.normalized_jsonl import read_normalized_jsonl
from raven.parsers.normalizer import NormalizationError, main, normalize_all, normalize_record
from raven.parsers.schema import (
    NORMALIZED_FIELDS,
    STATUS_INVALID,
    STATUS_OK,
    STATUS_UNSUPPORTED,
    validate_normalized_event,
)

SHA256 = "AB" * 32
MD5 = "CD" * 16
IMPHASH = "EF" * 16


def make_raw(event_id, record_id, data, time_created="2026-09-13 08:39:49.700000+00:00", computer="SYNTHETIC-LAB-HOST"):
    return {
        "event_id": event_id,
        "time_created": time_created,
        "computer": computer,
        "record_id": record_id,
        "event_data": data,
        "raw_xml": f"<Event>{record_id}</Event>",
    }


PROCESS_DATA = {
    "RuleName": "-",
    "UtcTime": "2026-09-13 08:39:49.545",
    "ProcessGuid": "{00000000-0000-0000-0000-000000000001}",
    "ProcessId": "1224",
    "Image": "C:\\Test\\synthetic.exe",
    "CommandLine": '"C:\\Test\\synthetic.exe" --flag',
    "User": "SYNTHETIC\\tester",
    "IntegrityLevel": "Medium",
    "Hashes": f"SHA256={SHA256},MD5={MD5},IMPHASH={IMPHASH}",
    "ParentProcessGuid": "{00000000-0000-0000-0000-000000000002}",
    "ParentProcessId": "900",
    "ParentImage": "C:\\Test\\parent.exe",
    "ParentCommandLine": "parent.exe",
}
NETWORK_DATA = {
    "UtcTime": "2026-09-13 08:39:50.250",
    "ProcessGuid": "{00000000-0000-0000-0000-000000000001}",
    "ProcessId": "1224",
    "Image": "C:\\Test\\synthetic.exe",
    "User": "SYNTHETIC\\tester",
    "Protocol": "tcp",
    "Initiated": "true",
    "SourceIp": "10.0.2.15",
    "SourcePort": "49674",
    "DestinationIp": "127.0.0.1",
    "DestinationPort": "47001",
}
FILE_DATA = {
    "UtcTime": "2026-09-13 08:39:51.005",
    "ProcessGuid": "{00000000-0000-0000-0000-000000000001}",
    "ProcessId": "1224",
    "Image": "C:\\Test\\synthetic.exe",
    "TargetFilename": "C:\\Test\\burst_0001.raventest",
    "User": "SYNTHETIC\\tester",
}


def test_process_creation_mapping():
    event = normalize_record(make_raw(1, 42, PROCESS_DATA), 7)
    assert list(event) == list(NORMALIZED_FIELDS)
    assert event["raw_event_ref"] == "7:42"
    assert event["event_id"] == 1
    assert event["event_type"] == "process_creation"
    assert event["timestamp"] == "2026-09-13T08:39:49.545Z"
    assert event["computer"] == "SYNTHETIC-LAB-HOST"
    assert event["process_guid"] == "{00000000-0000-0000-0000-000000000001}"
    assert event["process_id"] == 1224
    assert event["process_name"] == "C:\\Test\\synthetic.exe"
    assert event["parent_process_guid"] == "{00000000-0000-0000-0000-000000000002}"
    assert event["parent_process_id"] == 900
    assert event["parent_process_name"] == "C:\\Test\\parent.exe"
    assert event["command_line"] == '"C:\\Test\\synthetic.exe" --flag'
    assert event["parent_command_line"] == "parent.exe"
    assert event["user"] == "SYNTHETIC\\tester"
    assert event["integrity_level"] == "Medium"
    assert event["hash_sha256"] == SHA256
    assert event["hash_md5"] == MD5
    assert event["hash_imphash"] == IMPHASH
    assert event["hashes_raw"] == PROCESS_DATA["Hashes"]
    assert event["normalization_status"] == STATUS_OK
    for field in ("ip_address", "port", "source_ip", "source_port", "protocol", "initiated", "file_path"):
        assert event[field] is None
    assert validate_normalized_event(event) == []


def test_network_connection_mapping():
    event = normalize_record(make_raw(3, 43, NETWORK_DATA), 1)
    assert event["event_type"] == "network_connection"
    assert event["timestamp"] == "2026-09-13T08:39:50.250Z"
    assert event["ip_address"] == "127.0.0.1"
    assert event["port"] == 47001
    assert event["source_ip"] == "10.0.2.15"
    assert event["source_port"] == 49674
    assert event["protocol"] == "tcp"
    assert event["initiated"] is True
    assert event["process_id"] == 1224
    assert event["process_name"] == "C:\\Test\\synthetic.exe"
    for field in ("parent_process_guid", "parent_process_id", "command_line", "hashes_raw", "hash_sha256", "file_path"):
        assert event[field] is None
    assert event["normalization_status"] == STATUS_OK
    assert validate_normalized_event(event) == []


def test_initiated_false():
    data = dict(NETWORK_DATA, Initiated="false")
    assert normalize_record(make_raw(3, 1, data), 1)["initiated"] is False


def test_file_create_mapping():
    event = normalize_record(make_raw(11, 44, FILE_DATA), 1)
    assert event["event_type"] == "file_create"
    assert event["file_path"] == "C:\\Test\\burst_0001.raventest"
    assert event["process_name"] == "C:\\Test\\synthetic.exe"
    assert event["user"] == "SYNTHETIC\\tester"
    for field in ("ip_address", "port", "parent_process_id", "command_line", "hashes_raw"):
        assert event[field] is None
    assert event["normalization_status"] == STATUS_OK
    assert validate_normalized_event(event) == []


@pytest.mark.parametrize("event_id", [4, 5, 16, 255, 2, 22])
def test_unsupported_events_keep_only_identity_fields(event_id):
    raw = make_raw(event_id, 99, {"UtcTime": "2026-09-13 08:39:52.000", "Image": "C:\\Test\\x.exe", "ProcessId": "5"})
    event = normalize_record(raw, 3)
    assert event["event_type"] == "unsupported"
    assert event["normalization_status"] == STATUS_UNSUPPORTED
    assert event["raw_event_ref"] == "3:99"
    assert event["event_id"] == event_id
    assert event["timestamp"] == "2026-09-13T08:39:52.000Z"
    assert event["computer"] == "SYNTHETIC-LAB-HOST"
    identity = {"raw_event_ref", "event_id", "event_type", "timestamp", "computer", "normalization_status"}
    assert all(event[name] is None for name in NORMALIZED_FIELDS if name not in identity)
    assert validate_normalized_event(event) == []


def test_empty_optional_values_become_null():
    data = dict(PROCESS_DATA, CommandLine="", ParentCommandLine="", User="", Hashes="")
    event = normalize_record(make_raw(1, 1, data), 1)
    assert event["command_line"] is None
    assert event["parent_command_line"] is None
    assert event["user"] is None
    assert event["hashes_raw"] is None
    assert event["hash_sha256"] is None
    assert event["normalization_status"] == STATUS_OK


def test_absent_optional_values_stay_null_and_status_is_ok():
    data = {k: v for k, v in PROCESS_DATA.items() if k not in ("ParentImage", "IntegrityLevel", "User")}
    event = normalize_record(make_raw(1, 1, data), 1)
    assert event["parent_process_name"] is None
    assert event["integrity_level"] is None
    assert event["normalization_status"] == STATUS_OK


def test_hashes_keep_the_original_text_and_the_unparsed_algorithms():
    data = dict(PROCESS_DATA, Hashes=f"SHA1={'12' * 20},SHA256={SHA256}")
    event = normalize_record(make_raw(1, 1, data), 1)
    assert event["hashes_raw"] == f"SHA1={'12' * 20},SHA256={SHA256}"
    assert event["hash_sha256"] == SHA256
    assert event["hash_md5"] is None


@pytest.mark.parametrize(
    "event_id, data, key",
    [
        (1, PROCESS_DATA, "Image"),
        (1, PROCESS_DATA, "ProcessGuid"),
        (1, PROCESS_DATA, "ProcessId"),
        (3, NETWORK_DATA, "DestinationIp"),
        (3, NETWORK_DATA, "DestinationPort"),
        (3, NETWORK_DATA, "Protocol"),
        (3, NETWORK_DATA, "Initiated"),
        (11, FILE_DATA, "TargetFilename"),
        (11, FILE_DATA, "Image"),
    ],
)
def test_a_missing_required_field_makes_the_event_invalid_but_keeps_it(event_id, data, key):
    broken = {k: v for k, v in data.items() if k != key}
    event = normalize_record(make_raw(event_id, 5, broken), 1)
    assert event["normalization_status"] == STATUS_INVALID
    assert event["event_type"] != "unsupported"
    assert event["raw_event_ref"] == "1:5"
    assert validate_normalized_event(event) == []


def test_an_empty_required_field_counts_as_missing():
    event = normalize_record(make_raw(1, 5, dict(PROCESS_DATA, Image="")), 1)
    assert event["normalization_status"] == STATUS_INVALID
    assert event["process_name"] is None


@pytest.mark.parametrize(
    "event_id, data, key",
    [
        (1, PROCESS_DATA, "ProcessId"),
        (1, PROCESS_DATA, "ParentProcessId"),
        (3, NETWORK_DATA, "DestinationPort"),
        (3, NETWORK_DATA, "SourcePort"),
        (3, NETWORK_DATA, "Initiated"),
    ],
)
def test_a_value_that_cannot_be_read_makes_the_event_invalid(event_id, data, key):
    event = normalize_record(make_raw(event_id, 5, dict(data, **{key: "abc"})), 1)
    assert event["normalization_status"] == STATUS_INVALID


def test_readable_fields_survive_an_invalid_event():
    event = normalize_record(make_raw(1, 5, dict(PROCESS_DATA, ProcessId="abc")), 1)
    assert event["normalization_status"] == STATUS_INVALID
    assert event["process_id"] is None
    assert event["process_name"] == "C:\\Test\\synthetic.exe"
    assert event["command_line"] == '"C:\\Test\\synthetic.exe" --flag'


def test_timestamp_falls_back_to_time_created_and_converts_to_utc():
    data = {k: v for k, v in FILE_DATA.items() if k != "UtcTime"}
    raw = make_raw(11, 6, data, time_created="2026-09-13 10:39:49.700123+02:00")
    assert normalize_record(raw, 1)["timestamp"] == "2026-09-13T08:39:49.700Z"


def test_an_unreadable_utc_time_falls_back_to_time_created():
    raw = make_raw(11, 6, dict(FILE_DATA, UtcTime="not a time"))
    assert normalize_record(raw, 1)["timestamp"] == "2026-09-13T08:39:49.700Z"


def test_an_unreadable_time_created_is_an_error():
    with pytest.raises(NormalizationError, match="time_created"):
        normalize_record(make_raw(11, 6, FILE_DATA, time_created="garbage"), 1)


def test_an_invalid_raw_record_is_an_error():
    raw = make_raw(11, 6, FILE_DATA)
    del raw["raw_xml"]
    with pytest.raises(NormalizationError, match="invalid raw record"):
        normalize_record(raw, 1)


@pytest.mark.parametrize("evidence_id", [0, -1, "1", None, True, 1.0])
def test_the_evidence_id_must_be_a_positive_integer(evidence_id):
    with pytest.raises(NormalizationError, match="evidence_id"):
        normalize_record(make_raw(11, 6, FILE_DATA), evidence_id)


def test_same_input_gives_the_same_event():
    raw = make_raw(1, 42, PROCESS_DATA)
    assert normalize_record(raw, 1) == normalize_record(dict(raw), 1)


def test_the_raw_record_is_not_changed():
    raw = make_raw(1, 42, PROCESS_DATA)
    before = repr(raw)
    normalize_record(raw, 1)
    assert repr(raw) == before


# ---------------------------------------------------------------- normalize_all


def write_raw(tmp_path, records, name="raw.jsonl"):
    path = tmp_path / name
    write_raw_jsonl(records, path)
    return path


def sample_records():
    return [
        make_raw(1, 10, PROCESS_DATA),
        make_raw(11, 11, FILE_DATA),
        make_raw(5, 12, {"UtcTime": "2026-09-13 08:39:52.000"}),
        make_raw(3, 13, NETWORK_DATA),
        make_raw(1, 14, {k: v for k, v in PROCESS_DATA.items() if k != "Image"}),
        make_raw(255, 15, {"UtcTime": "2026-09-13 08:39:53.000"}),
    ]


def test_normalize_all_counts_and_keeps_every_record_in_order(tmp_path):
    raw = write_raw(tmp_path, sample_records())
    output = tmp_path / "out" / "normalized.jsonl"
    summary = normalize_all(raw, output, 2)
    assert summary["total"] == 6
    assert summary["status_counts"] == {STATUS_INVALID: 1, STATUS_OK: 3, STATUS_UNSUPPORTED: 2}
    assert summary["event_type_counts"] == {
        "file_create": 1,
        "network_connection": 1,
        "process_creation": 2,
        "unsupported": 2,
    }
    events = list(read_normalized_jsonl(output))
    assert [e["raw_event_ref"] for e in events] == [f"2:{n}" for n in (10, 11, 12, 13, 14, 15)]
    assert [e["event_id"] for e in events] == [1, 11, 5, 3, 1, 255]


def test_normalize_all_reports_invalid_examples_and_timestamp_statistics(tmp_path):
    raw = write_raw(tmp_path, sample_records())
    summary = normalize_all(raw, tmp_path / "n.jsonl", 1)
    assert summary["invalid_examples"] == [{"record_id": 14, "event_id": 1, "problems": ["Image is missing"]}]
    assert summary["timestamp_fallbacks"] == 0
    assert summary["timestamp_gap_records"] == 6
    # time_created is fixed at 08:39:49.700 in the sample records; UtcTime is 49.545, 50.250, 51.005,
    # 52.000 and 53.000, so three records differ by more than a second and the largest gap is 3.3 s.
    assert summary["timestamp_gap_over_1s"] == 3
    assert summary["timestamp_gap_max_seconds"] == pytest.approx(3.3, abs=0.001)


def test_normalize_all_counts_timestamp_fallbacks_and_large_gaps(tmp_path):
    no_utc = {k: v for k, v in FILE_DATA.items() if k != "UtcTime"}
    records = [
        make_raw(11, 1, no_utc),
        make_raw(11, 2, dict(FILE_DATA, UtcTime="2026-09-13 08:30:00.000")),
    ]
    summary = normalize_all(write_raw(tmp_path, records), tmp_path / "n.jsonl", 1)
    assert summary["timestamp_fallbacks"] == 1
    assert summary["timestamp_gap_records"] == 1
    assert summary["timestamp_gap_over_1s"] == 1
    assert summary["timestamp_gap_max_seconds"] == pytest.approx(589.7, abs=0.001)


def test_normalize_all_twice_gives_identical_files(tmp_path):
    raw = write_raw(tmp_path, sample_records())
    first, second = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    summary_first = normalize_all(raw, first, 1)
    summary_second = normalize_all(raw, second, 1)
    assert first.read_bytes() == second.read_bytes()
    assert summary_first == summary_second


def test_the_evidence_id_appears_in_every_reference(tmp_path):
    output = tmp_path / "n.jsonl"
    normalize_all(write_raw(tmp_path, sample_records()), output, 12)
    assert all(e["raw_event_ref"].startswith("12:") for e in read_normalized_jsonl(output))


def test_missing_input(tmp_path):
    with pytest.raises(FileNotFoundError):
        normalize_all(tmp_path / "missing.jsonl", tmp_path / "n.jsonl", 1)


def test_output_must_differ_from_input(tmp_path):
    raw = write_raw(tmp_path, sample_records())
    with pytest.raises(ValueError, match="must differ"):
        normalize_all(raw, raw, 1)


def test_a_bad_record_in_the_input_stops_the_run_and_keeps_the_previous_output(tmp_path):
    records = sample_records()
    records.insert(3, make_raw(11, 99, FILE_DATA, time_created="garbage"))
    raw = write_raw(tmp_path, records)
    output = tmp_path / "n.jsonl"
    output.write_text("previous content\n", encoding="utf-8")
    with pytest.raises(NormalizationError, match="time_created"):
        normalize_all(raw, output, 1)
    assert output.read_text(encoding="utf-8") == "previous content\n"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["n.jsonl", "raw.jsonl"]


def test_main_prints_the_counts(tmp_path, capsys):
    raw = write_raw(tmp_path, sample_records())
    output = tmp_path / "n.jsonl"
    assert main([str(raw), str(output), "--evidence-id", "1"]) == 0
    printed = capsys.readouterr().out
    assert "events normalized: 6" in printed
    assert "status OK: 3" in printed
    assert "status UNSUPPORTED_EVENT_ID: 2" in printed
    assert "status INVALID_EVENT_DATA: 1" in printed
    assert "type unsupported: 2" in printed
    assert "invalid: record 14 event 1: Image is missing" in printed


def test_main_reports_errors(tmp_path, capsys):
    assert main([str(tmp_path / "missing.jsonl"), str(tmp_path / "n.jsonl"), "--evidence-id", "1"]) == 1
    assert "ERROR" in capsys.readouterr().err
    raw = write_raw(tmp_path, sample_records())
    assert main([str(raw), str(tmp_path / "n.jsonl"), "--evidence-id", "0"]) == 1
