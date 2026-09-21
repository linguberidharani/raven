"""Reading the JSONL files that the VM collector drops in the inbox (spec sections 7 and 10.3).

    read_new_records(path, offset) -> InboxRead

The collector appends one raw record (spec 6.1) per line to a file in the shared inbox folder. The host reads only the
bytes after a saved offset and only COMPLETE lines (a line still being written waits for the next look), so nothing
is read twice and nothing half-written is used. Lines that are not valid raw records are rejected and counted; they
never stop the good lines around them.

Check a file from the command line:

    python -m raven.collectors.inbox <file.jsonl>
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from raven.collectors.raw_schema import validate_raw_record

MAX_CHUNK_BYTES = 16 * 1024 * 1024
MAX_REJECTED_MESSAGES = 20
SOURCE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}\.jsonl$")
_BOM = b"\xef\xbb\xbf"


class InboxError(ValueError):
    """An inbox file cannot be read (it was replaced or shortened, or a line is far too long)."""


@dataclass(frozen=True)
class InboxRead:
    records: list[dict[str, Any]]
    rejected: list[str]
    rejected_count: int
    new_offset: int


def valid_source_name(name: object) -> bool:
    """A source name is a plain file name ending in .jsonl: letters, digits, dot, underscore and dash only."""
    return isinstance(name, str) and SOURCE_NAME.match(name) is not None and ".." not in name


def read_new_records(path: str | os.PathLike[str], offset: int = 0, max_bytes: int = MAX_CHUNK_BYTES) -> InboxRead:
    """The complete lines after `offset`: valid raw records, the rejected lines (with a reason) and the new offset."""
    if offset < 0:
        raise InboxError("the offset cannot be negative")
    with open(path, "rb") as handle:
        size = os.fstat(handle.fileno()).st_size
        if offset > size:
            raise InboxError("the file is smaller than the saved position; it may have been replaced or rotated")
        handle.seek(offset)
        chunk = handle.read(max_bytes)
    if not chunk:
        return InboxRead([], [], 0, offset)
    end = chunk.rfind(b"\n")
    if end == -1:
        if len(chunk) >= max_bytes:
            raise InboxError(f"a line is longer than {max_bytes} bytes")
        return InboxRead([], [], 0, offset)

    complete = chunk[: end + 1]
    records: list[dict[str, Any]] = []
    rejected: list[str] = []
    rejected_count = 0
    position = offset
    for number, line in enumerate(complete.split(b"\n")[:-1]):
        line_start = position
        position += len(line) + 1
        if number == 0 and offset == 0 and line.startswith(_BOM):
            line = line[len(_BOM):]
        line = line.rstrip(b"\r")
        if not line.strip():
            continue
        problem: str | None = None
        record: Any = None
        try:
            record = json.loads(line.decode("utf-8"))
        except UnicodeDecodeError:
            problem = "not valid UTF-8"
        except json.JSONDecodeError as exc:
            problem = f"not valid JSON ({exc.msg})"
        if problem is None:
            problems = validate_raw_record(record)
            if problems:
                problem = "; ".join(problems)
        if problem is not None:
            rejected_count += 1
            if len(rejected) < MAX_REJECTED_MESSAGES:
                rejected.append(f"line at byte {line_start}: {problem}")
            continue
        records.append(record)
    return InboxRead(records, rejected, rejected_count, offset + end + 1)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m raven.collectors.inbox", description="Check a collector JSONL file.")
    parser.add_argument("file")
    args = parser.parse_args(argv)
    try:
        result = read_new_records(Path(args.file), 0)
    except (OSError, InboxError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    ids = [record["record_id"] for record in result.records]
    print(f"valid records: {len(result.records)}")
    print(f"rejected lines: {result.rejected_count}")
    print(f"bytes read: {result.new_offset}")
    if ids:
        print(f"record ids: {min(ids)} to {max(ids)}")
    for message in result.rejected:
        print(f"  {message}")
    return 0 if result.rejected_count == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
