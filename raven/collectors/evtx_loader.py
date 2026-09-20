"""Collection stage: EVTX file to raw JSONL (spec section 7, stage Collect).

    load_evtx(input_evtx, output_jsonl) -> number of records written

Every event of the EVTX file becomes one raw record (see raw_schema.py), in file order.
Nothing is dropped and nothing is interpreted here: unsupported Sysmon event IDs are
kept too. If any record cannot be read, the load stops with an error and the output
path is left unchanged, so a partial result is never mistaken for a complete one.

Run from the command line:

    python -m raven.collectors.evtx_loader <input.evtx> <output.jsonl>
"""

from __future__ import annotations

import argparse
import os
import sys
import xml.etree.ElementTree as ET
from collections.abc import Iterator, Sequence
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from Evtx.Evtx import Evtx

from raven.collectors.raw_jsonl import RawRecordError, sha256_file, write_raw_jsonl
from raven.collectors.raw_schema import UNNAMED_KEY

EVENT_NS = "{http://schemas.microsoft.com/win/2004/08/events/event}"


class EvtxLoadError(Exception):
    """The EVTX file, or one of its records, could not be read."""


def _required_text(system: ET.Element, tag: str) -> str:
    element = system.find(EVENT_NS + tag)
    if element is None or element.text is None or not element.text.strip():
        raise EvtxLoadError(f"System/{tag} is missing")
    return element.text.strip()


def _required_int(system: ET.Element, tag: str) -> int:
    text = _required_text(system, tag)
    try:
        return int(text)
    except ValueError as exc:
        raise EvtxLoadError(f"System/{tag} is not an integer: {text!r}") from exc


def parse_event_xml(xml: str) -> dict[str, Any]:
    """Turn the XML of one event into a raw record."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise EvtxLoadError(f"invalid event XML: {exc}") from exc

    system = root.find(EVENT_NS + "System")
    if system is None:
        raise EvtxLoadError("System section is missing")

    time_element = system.find(EVENT_NS + "TimeCreated")
    time_created = time_element.get("SystemTime") if time_element is not None else None
    if not time_created:
        raise EvtxLoadError("System/TimeCreated SystemTime is missing")

    event_data: dict[str, Any] = {}
    unnamed: list[str] = []
    data_section = root.find(EVENT_NS + "EventData")
    if data_section is not None:
        for item in data_section.findall(EVENT_NS + "Data"):
            value = item.text if item.text is not None else ""
            name = item.get("Name")
            if name is None:
                unnamed.append(value)
            elif name in event_data:
                raise EvtxLoadError(f"EventData has the name {name!r} more than once")
            else:
                event_data[name] = value
    if unnamed:
        event_data[UNNAMED_KEY] = unnamed

    return {
        "event_id": _required_int(system, "EventID"),
        "time_created": time_created,
        "computer": _required_text(system, "Computer"),
        "record_id": _required_int(system, "EventRecordID"),
        "event_data": event_data,
        "raw_xml": xml,
    }


def _advance(iterator: Iterator[Any], description: str) -> Any:
    """Next item of an iterator, or None at the end. Any error becomes an EvtxLoadError."""
    try:
        return next(iterator)
    except StopIteration:
        return None
    except Exception as exc:
        raise EvtxLoadError(f"cannot read {description}: {exc}") from exc


def iter_evtx_records(input_evtx: str | os.PathLike[str]) -> Iterator[dict[str, Any]]:
    """Yield the raw records of an EVTX file, in file order.

    python-evtx stops quietly at a damaged record and does not check the file
    signature. So this function checks both itself: the file signature, the
    signature of every chunk, and, for every chunk, that the number of records read
    equals the number of records the chunk header declares. Any mismatch is an
    EvtxLoadError, never a silently shorter result. A file without records is an error too.
    """
    path = Path(input_evtx)
    with ExitStack() as stack:
        try:
            log = stack.enter_context(Evtx(str(path)))
            signature_ok = log.get_file_header().check_magic()
        except Exception as exc:
            raise EvtxLoadError(f"cannot open {path.name} as an EVTX file: {exc}") from exc
        if not signature_ok:
            raise EvtxLoadError(f"{path.name} is not an EVTX file (wrong file signature)")

        total = 0
        chunks = iter(log.chunks())
        chunk_number = 0
        while True:
            chunk = _advance(chunks, f"chunk {chunk_number + 1} of {path.name}")
            if chunk is None:
                break
            chunk_number += 1
            if not chunk.check_magic():
                raise EvtxLoadError(f"chunk {chunk_number} of {path.name} has an invalid header")
            expected = max(0, chunk.file_last_record_number() - chunk.file_first_record_number() + 1)

            found = 0
            records = iter(chunk.records())
            while True:
                record = _advance(records, f"a record of chunk {chunk_number} of {path.name}")
                if record is None:
                    break
                position = total + 1
                try:
                    raw = parse_event_xml(record.xml())
                except EvtxLoadError as exc:
                    raise EvtxLoadError(f"record {position} of {path.name}: {exc}") from exc
                except Exception as exc:
                    raise EvtxLoadError(f"cannot read record {position} of {path.name}: {exc}") from exc
                total += 1
                found += 1
                yield raw

            if found != expected:
                raise EvtxLoadError(
                    f"chunk {chunk_number} of {path.name}: {found} record(s) could be read, "
                    f"the chunk header declares {expected}"
                )

        if total == 0:
            raise EvtxLoadError(f"{path.name} contains no records")


def load_evtx(input_evtx: str | os.PathLike[str], output_jsonl: str | os.PathLike[str]) -> int:
    """Read an EVTX file and write its raw records as JSONL. Return the record count."""
    source = Path(input_evtx)
    target = Path(output_jsonl)
    if not source.is_file():
        raise FileNotFoundError(f"EVTX file not found: {source}")
    if source.resolve() == target.resolve():
        raise ValueError("the output path must differ from the input path")
    return write_raw_jsonl(iter_evtx_records(source), target)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m raven.collectors.evtx_loader",
        description="Convert an EVTX file to raw JSONL (one raw record per line).",
    )
    parser.add_argument("input_evtx")
    parser.add_argument("output_jsonl")
    args = parser.parse_args(argv)
    try:
        count = load_evtx(args.input_evtx, args.output_jsonl)
        digest = sha256_file(args.output_jsonl)
    except (OSError, ValueError, EvtxLoadError, RawRecordError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"records written: {count}")
    print(f"output:          {args.output_jsonl}")
    print(f"output sha256:   {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
