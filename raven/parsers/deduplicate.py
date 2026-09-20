"""Deduplication stage (spec sections 6.3 and 7).

    deduplicate(normalized_jsonl, deduplicated_jsonl, duplicates_jsonl=None) -> (input, unique, removed)

Two normalized events are duplicates when they are equal in every field except raw_event_ref (the
record-specific reference). That is the 26 fields in FINGERPRINT_FIELDS. The fingerprint is the
SHA-256 of those 26 values, in that fixed order, written as compact JSON, so the same events always
give the same fingerprint. The first event of a group is kept, in file order; the others are removed.

Nothing is removed without a trace: when a duplicates file is given, it gets one line per removed
event with the removed reference, the kept reference and the fingerprint.

Unsupported events carry only identity fields (see normalizer.py), so two unsupported events with the
same event ID and the same millisecond are duplicates of each other. That is the behavior the spec's
reference numbers (97 removed) describe; the duplicates file shows exactly which events it applies to.

Run from the command line:

    python -m raven.parsers.deduplicate <normalized.jsonl> <deduplicated.jsonl> [--duplicates <duplicates.jsonl>]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any, NamedTuple

from raven.collectors.raw_jsonl import sha256_file
from raven.fileio import write_lines_atomic
from raven.parsers.normalized_jsonl import (
    NormalizedEventError,
    read_normalized_jsonl,
    serialize_event,
    write_normalized_jsonl,
)
from raven.parsers.schema import NORMALIZED_FIELDS

FINGERPRINT_FIELDS: tuple[str, ...] = tuple(name for name in NORMALIZED_FIELDS if name != "raw_event_ref")


class DedupResult(NamedTuple):
    input_count: int
    unique_count: int
    removed_count: int


def fingerprint(event: dict[str, Any]) -> str:
    """SHA-256 (upper case hex) over the 26 fingerprint fields of a normalized event."""
    values = [event[name] for name in FINGERPRINT_FIELDS]
    text = json.dumps(values, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("ascii")).hexdigest().upper()


def deduplicate(
    input_jsonl: str | os.PathLike[str],
    output_jsonl: str | os.PathLike[str],
    duplicates_jsonl: str | os.PathLike[str] | None = None,
) -> DedupResult:
    """Remove duplicate events from a normalized JSONL file. Return (input, unique, removed)."""
    source = Path(input_jsonl)
    target = Path(output_jsonl)
    side = Path(duplicates_jsonl) if duplicates_jsonl is not None else None
    if not source.is_file():
        raise FileNotFoundError(f"normalized JSONL file not found: {source}")
    resolved = {source.resolve(), target.resolve()}
    if side is not None:
        resolved.add(side.resolve())
    if len(resolved) != (3 if side is not None else 2):
        raise ValueError("the input, output and duplicates paths must all differ")

    first_seen: dict[str, str] = {}
    removed: list[dict[str, str]] = []
    counts = {"input": 0}

    def unique_events() -> Iterator[dict[str, Any]]:
        for event in read_normalized_jsonl(source):
            counts["input"] += 1
            key = fingerprint(event)
            kept_reference = first_seen.get(key)
            if kept_reference is None:
                first_seen[key] = event["raw_event_ref"]
                yield event
            else:
                removed.append(
                    {"removed_ref": event["raw_event_ref"], "kept_ref": kept_reference, "fingerprint": key}
                )

    unique = write_normalized_jsonl(unique_events(), target)
    if side is not None:
        write_lines_atomic(
            side, (json.dumps(row, ensure_ascii=True, separators=(",", ":")) for row in removed)
        )
    return DedupResult(counts["input"], unique, len(removed))


def count_duplicate_fingerprints(path: str | os.PathLike[str]) -> int:
    """How many events in a file share a fingerprint with an earlier event (0 after deduplication)."""
    seen: set[str] = set()
    repeated = 0
    for event in read_normalized_jsonl(path):
        key = fingerprint(event)
        if key in seen:
            repeated += 1
        seen.add(key)
    return repeated


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m raven.parsers.deduplicate",
        description="Remove duplicate events (equal in every field except raw_event_ref) from a normalized JSONL file.",
    )
    parser.add_argument("normalized_jsonl")
    parser.add_argument("deduplicated_jsonl")
    parser.add_argument("--duplicates", dest="duplicates_jsonl", help="write one line per removed event here")
    args = parser.parse_args(argv)
    try:
        result = deduplicate(args.normalized_jsonl, args.deduplicated_jsonl, args.duplicates_jsonl)
        digest = sha256_file(args.deduplicated_jsonl)
        remaining = count_duplicate_fingerprints(args.deduplicated_jsonl)
        kept_by_status = Counter(event["normalization_status"] for event in read_normalized_jsonl(args.deduplicated_jsonl))
        removed_by_status: Counter[str] = Counter()
        if args.duplicates_jsonl:
            statuses = {event["raw_event_ref"]: event["normalization_status"] for event in read_normalized_jsonl(args.normalized_jsonl)}
            with open(args.duplicates_jsonl, "r", encoding="utf-8", newline="\n") as handle:
                for line in handle:
                    removed_by_status[statuses[json.loads(line)["removed_ref"]]] += 1
    except (OSError, ValueError, NormalizedEventError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"input events:                {result.input_count}")
    print(f"unique events:               {result.unique_count}")
    print(f"duplicates removed:          {result.removed_count}")
    print(f"duplicate fingerprints left: {remaining}")
    print(f"output sha256:               {digest}")
    for status, number in sorted(kept_by_status.items()):
        print(f"kept {status}: {number}")
    for status, number in sorted(removed_by_status.items()):
        print(f"removed {status}: {number}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
