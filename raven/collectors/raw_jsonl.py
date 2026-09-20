"""Reading and writing raw JSONL files: one raw record per line (spec section 6.1).

Writing is deterministic (fixed field order, compact separators, ASCII only, LF line
ends) and atomic (a temporary file is renamed over the output, so a failed run never
leaves a half-written file and never damages an existing output).

Check a file from the command line:

    python -m raven.collectors.raw_jsonl <file.jsonl>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path
from typing import Any

from raven.collectors.raw_schema import RAW_FIELDS, validate_raw_record


class RawRecordError(ValueError):
    """A raw record or a raw JSONL file is invalid."""


def serialize_record(record: dict[str, Any]) -> str:
    """One record as one JSON line (without the line end)."""
    ordered = {name: record[name] for name in RAW_FIELDS}
    return json.dumps(ordered, ensure_ascii=True, separators=(",", ":"))


def write_raw_jsonl(records: Iterable[dict[str, Any]], output_path: str | os.PathLike[str]) -> int:
    """Write records to a JSONL file and return how many were written.

    Every record is validated first. On any error nothing is changed at the output path.
    """
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    count = 0
    try:
        with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
            for record in records:
                problems = validate_raw_record(record)
                if problems:
                    raise RawRecordError(f"record {count + 1} is invalid: " + "; ".join(problems))
                handle.write(serialize_record(record))
                handle.write("\n")
                count += 1
        os.replace(temporary, output)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return count


def read_raw_jsonl(path: str | os.PathLike[str]) -> Iterator[dict[str, Any]]:
    """Yield the records of a JSONL file, validating each one."""
    with open(path, "r", encoding="utf-8", newline="\n") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                raise RawRecordError(f"line {line_number}: empty line")
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RawRecordError(f"line {line_number}: invalid JSON ({exc})") from exc
            problems = validate_raw_record(record)
            if problems:
                raise RawRecordError(f"line {line_number}: " + "; ".join(problems))
            yield record


def sha256_file(path: str | os.PathLike[str]) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def summarize_raw_jsonl(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Counts read back from a raw JSONL file (every record is validated on the way)."""
    total = 0
    event_ids: Counter[int] = Counter()
    computers: set[str] = set()
    record_ids: set[int] = set()
    first: str | None = None
    last: str | None = None
    for record in read_raw_jsonl(path):
        total += 1
        event_ids[record["event_id"]] += 1
        computers.add(record["computer"])
        record_ids.add(record["record_id"])
        stamp = record["time_created"]
        if first is None or stamp < first:
            first = stamp
        if last is None or stamp > last:
            last = stamp
    return {
        "records": total,
        "unique_record_ids": len(record_ids),
        "event_id_counts": dict(sorted(event_ids.items())),
        "computers": sorted(computers),
        "first_time_created": first,
        "last_time_created": last,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m raven.collectors.raw_jsonl",
        description="Validate a raw JSONL file and print its counts.",
    )
    parser.add_argument("jsonl_file")
    args = parser.parse_args(argv)
    try:
        summary = summarize_raw_jsonl(args.jsonl_file)
        digest = sha256_file(args.jsonl_file)
    except (OSError, RawRecordError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"file:               {args.jsonl_file}")
    print(f"sha256:             {digest}")
    print(f"records:            {summary['records']}")
    print(f"unique record ids:  {summary['unique_record_ids']}")
    print(f"computers:          {', '.join(summary['computers'])}")
    print(f"first time_created: {summary['first_time_created']} (text order)")
    print(f"last time_created:  {summary['last_time_created']} (text order)")
    for event_id, number in summary["event_id_counts"].items():
        print(f"event {event_id}: {number}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
