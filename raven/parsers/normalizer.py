"""Normalization stage: raw records to normalized events (spec sections 6.2 and 7).

    normalize_record(raw, evidence_id) -> one normalized event (27 fields)
    normalize_all(raw_jsonl, normalized_jsonl, evidence_id) -> counts

Sysmon event 1 becomes process_creation, 3 network_connection, 11 file_create. Every other
event ID becomes an "unsupported" event that keeps only its identity fields (reference,
event ID, timestamp, computer); it is retained, never dropped, and never interpreted.

timestamp is the record's TimeCreated (when the Windows event log wrote the record), converted to
UTC, with the digits beyond the millisecond cut off. The Sysmon UtcTime inside event_data is NOT
used for it. On the reference data 132 events carry a UtcTime about 3.5 hours after their record
time, and the spec's time range and example IDs follow the record time. UtcTime stays available in
event_data and raw_xml; how far it is from the record time is counted in the result for information.

A supported event that lacks a required field, or has a number or true/false value that cannot
be read, gets the status INVALID_EVENT_DATA. It is still written, with every field that could
be read, so nothing disappears silently.

Run from the command line:

    python -m raven.parsers.normalizer <raw.jsonl> <normalized.jsonl> --evidence-id 1
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

from raven.collectors.raw_jsonl import RawRecordError, read_raw_jsonl, sha256_file
from raven.collectors.raw_schema import validate_raw_record
from raven.parsers.hash_utils import parse_hashes
from raven.parsers.normalized_jsonl import NormalizedEventError, write_normalized_jsonl
from raven.parsers.schema import (
    EVENT_TYPE_UNSUPPORTED,
    NORMALIZED_FIELDS,
    STATUS_INVALID,
    STATUS_OK,
    STATUS_UNSUPPORTED,
    SUPPORTED_EVENT_TYPES,
)
from raven.parsers.time_utils import TimeFormatError, format_iso_millis, parse_timestamp

_DIGITS = re.compile(r"^[0-9]+$")
_MAX_INVALID_EXAMPLES = 10


class NormalizationError(ValueError):
    """A raw record or an argument cannot be normalized at all."""


# (normalized field, Sysmon field name, kind); kind is "text", "int" or "bool".
_COMMON = (
    ("process_guid", "ProcessGuid", "text"),
    ("process_id", "ProcessId", "int"),
    ("process_name", "Image", "text"),
    ("user", "User", "text"),
)
_MAPPING: dict[int, tuple[tuple[str, str, str], ...]] = {
    1: _COMMON
    + (
        ("parent_process_guid", "ParentProcessGuid", "text"),
        ("parent_process_id", "ParentProcessId", "int"),
        ("parent_process_name", "ParentImage", "text"),
        ("command_line", "CommandLine", "text"),
        ("parent_command_line", "ParentCommandLine", "text"),
        ("integrity_level", "IntegrityLevel", "text"),
        ("hashes_raw", "Hashes", "text"),
    ),
    3: _COMMON
    + (
        ("ip_address", "DestinationIp", "text"),
        ("port", "DestinationPort", "int"),
        ("source_ip", "SourceIp", "text"),
        ("source_port", "SourcePort", "int"),
        ("protocol", "Protocol", "text"),
        ("initiated", "Initiated", "bool"),
    ),
    11: _COMMON + (("file_path", "TargetFilename", "text"),),
}
_REQUIRED: dict[int, tuple[str, ...]] = {
    1: ("ProcessGuid", "ProcessId", "Image"),
    3: ("ProcessGuid", "ProcessId", "Image", "Protocol", "DestinationIp", "DestinationPort", "Initiated"),
    11: ("ProcessGuid", "ProcessId", "Image", "TargetFilename"),
}


def _check_evidence_id(evidence_id: Any) -> int:
    if isinstance(evidence_id, bool) or not isinstance(evidence_id, int) or evidence_id < 1:
        raise NormalizationError("evidence_id must be a positive integer")
    return evidence_id


def _timestamp_and_gap(raw: dict[str, Any]) -> tuple[str, float | None]:
    """Return (timestamp from TimeCreated, seconds between Sysmon UtcTime and TimeCreated or None)."""
    try:
        created = parse_timestamp(raw["time_created"])
    except TimeFormatError as exc:
        raise NormalizationError(f"record {raw['record_id']}: time_created: {exc}") from exc
    gap = None
    utc_text = raw["event_data"].get("UtcTime")
    if utc_text:
        try:
            gap = abs((parse_timestamp(utc_text, assume_utc=True) - created).total_seconds())
        except TimeFormatError:
            gap = None
    return format_iso_millis(created), gap


def _normalize(raw: dict[str, Any], evidence_id: int) -> tuple[dict[str, Any], list[str], float | None]:
    problems = validate_raw_record(raw)
    if problems:
        raise NormalizationError("invalid raw record: " + "; ".join(problems))
    timestamp, gap = _timestamp_and_gap(raw)

    event: dict[str, Any] = {name: None for name in NORMALIZED_FIELDS}
    event["raw_event_ref"] = f"{evidence_id}:{raw['record_id']}"
    event["event_id"] = raw["event_id"]
    event["timestamp"] = timestamp
    event["computer"] = raw["computer"]

    event_type = SUPPORTED_EVENT_TYPES.get(raw["event_id"])
    if event_type is None:
        event["event_type"] = EVENT_TYPE_UNSUPPORTED
        event["normalization_status"] = STATUS_UNSUPPORTED
        return event, [], gap
    event["event_type"] = event_type

    data = raw["event_data"]
    required = _REQUIRED[raw["event_id"]]
    issues: list[str] = []
    for field, key, kind in _MAPPING[raw["event_id"]]:
        value = data.get(key)
        if not isinstance(value, str) or value == "":
            if key in required:
                issues.append(f"{key} is missing")
            continue
        if kind == "text":
            event[field] = value
        elif kind == "int":
            if _DIGITS.match(value):
                event[field] = int(value)
            else:
                issues.append(f"{key} is not a whole number: {value!r}")
        else:
            lowered = value.lower()
            if lowered in ("true", "false"):
                event[field] = lowered == "true"
            else:
                issues.append(f"{key} is not true or false: {value!r}")

    if raw["event_id"] == 1:
        hashes = parse_hashes(event["hashes_raw"])
        event["hash_sha256"] = hashes["sha256"]
        event["hash_md5"] = hashes["md5"]
        event["hash_imphash"] = hashes["imphash"]

    event["normalization_status"] = STATUS_INVALID if issues else STATUS_OK
    return event, issues, gap


def normalize_record(raw: dict[str, Any], evidence_id: int) -> dict[str, Any]:
    """Turn one raw record into one normalized event."""
    return _normalize(raw, _check_evidence_id(evidence_id))[0]


def normalize_all(
    input_jsonl: str | os.PathLike[str],
    output_jsonl: str | os.PathLike[str],
    evidence_id: int,
) -> dict[str, Any]:
    """Normalize a raw JSONL file into a normalized JSONL file and return the counts.

    The result holds: total, status_counts, event_type_counts, utc_time_gap_records (records that
    have a readable Sysmon UtcTime), utc_time_gap_over_1s, utc_time_gap_max_seconds (how far UtcTime
    is from the record time, for information) and invalid_examples (the first few
    INVALID_EVENT_DATA cases).
    """
    evidence_id = _check_evidence_id(evidence_id)
    source = Path(input_jsonl)
    target = Path(output_jsonl)
    if not source.is_file():
        raise FileNotFoundError(f"raw JSONL file not found: {source}")
    if source.resolve() == target.resolve():
        raise ValueError("the output path must differ from the input path")

    statuses: Counter[str] = Counter()
    types: Counter[str] = Counter()
    stats = {"gap_records": 0, "gap_over_1s": 0, "gap_max": None}
    examples: list[dict[str, Any]] = []

    def events() -> Iterator[dict[str, Any]]:
        for raw in read_raw_jsonl(source):
            event, issues, gap = _normalize(raw, evidence_id)
            statuses[event["normalization_status"]] += 1
            types[event["event_type"]] += 1
            if gap is not None:
                stats["gap_records"] += 1
                if gap > 1:
                    stats["gap_over_1s"] += 1
                if stats["gap_max"] is None or gap > stats["gap_max"]:
                    stats["gap_max"] = gap
            if issues and len(examples) < _MAX_INVALID_EXAMPLES:
                examples.append({"record_id": raw["record_id"], "event_id": raw["event_id"], "problems": issues})
            yield event

    total = write_normalized_jsonl(events(), target)
    return {
        "total": total,
        "status_counts": dict(sorted(statuses.items())),
        "event_type_counts": dict(sorted(types.items())),
        "utc_time_gap_records": stats["gap_records"],
        "utc_time_gap_over_1s": stats["gap_over_1s"],
        "utc_time_gap_max_seconds": stats["gap_max"],
        "invalid_examples": examples,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m raven.parsers.normalizer",
        description="Normalize a raw JSONL file (one raw record per line) into a normalized JSONL file.",
    )
    parser.add_argument("raw_jsonl")
    parser.add_argument("normalized_jsonl")
    parser.add_argument("--evidence-id", type=int, required=True, help="numeric evidence ID used in raw_event_ref")
    args = parser.parse_args(argv)
    try:
        summary = normalize_all(args.raw_jsonl, args.normalized_jsonl, args.evidence_id)
        digest = sha256_file(args.normalized_jsonl)
    except (OSError, ValueError, RawRecordError, NormalizedEventError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"events normalized: {summary['total']}")
    print(f"output:            {args.normalized_jsonl}")
    print(f"output sha256:     {digest}")
    for status, number in summary["status_counts"].items():
        print(f"status {status}: {number}")
    for event_type, number in summary["event_type_counts"].items():
        print(f"type {event_type}: {number}")
    maximum = summary["utc_time_gap_max_seconds"]
    print("timestamp comes from the record time (TimeCreated); Sysmon UtcTime is not used for it")
    print(
        f"Sysmon UtcTime differs from the record time by more than 1 s: {summary['utc_time_gap_over_1s']} "
        f"of {summary['utc_time_gap_records']} (largest gap: "
        f"{'none' if maximum is None else f'{maximum:.3f} s'})"
    )
    for example in summary["invalid_examples"]:
        print(f"invalid: record {example['record_id']} event {example['event_id']}: " + "; ".join(example["problems"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
