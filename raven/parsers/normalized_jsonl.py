"""Reading and writing normalized JSONL files: one normalized event per line.

Same rules as the raw JSONL files: fixed field order, compact separators, ASCII only,
LF line ends, atomic replace of the output, every event validated.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from raven.parsers.schema import NORMALIZED_FIELDS, validate_normalized_event


class NormalizedEventError(ValueError):
    """A normalized event or a normalized JSONL file is invalid."""


def serialize_event(event: dict[str, Any]) -> str:
    """One event as one JSON line (without the line end)."""
    ordered = {name: event[name] for name in NORMALIZED_FIELDS}
    return json.dumps(ordered, ensure_ascii=True, separators=(",", ":"))


def write_normalized_jsonl(events: Iterable[dict[str, Any]], output_path: str | os.PathLike[str]) -> int:
    """Write events to a JSONL file and return how many were written.

    Every event is validated first. On any error nothing is changed at the output path.
    """
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    count = 0
    try:
        with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
            for event in events:
                problems = validate_normalized_event(event)
                if problems:
                    raise NormalizedEventError(f"event {count + 1} is invalid: " + "; ".join(problems))
                handle.write(serialize_event(event))
                handle.write("\n")
                count += 1
        os.replace(temporary, output)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return count


def read_normalized_jsonl(path: str | os.PathLike[str]) -> Iterator[dict[str, Any]]:
    """Yield the events of a normalized JSONL file, validating each one."""
    with open(path, "r", encoding="utf-8", newline="\n") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                raise NormalizedEventError(f"line {line_number}: empty line")
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise NormalizedEventError(f"line {line_number}: invalid JSON ({exc})") from exc
            problems = validate_normalized_event(event)
            if problems:
                raise NormalizedEventError(f"line {line_number}: " + "; ".join(problems))
            yield event
