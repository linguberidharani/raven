"""SYNTHETIC test data for the service and API tests. It is not real telemetry.

Fake raw records and fake loaders stand in for the EVTX reader, so the whole pipeline can run in a test without
an EVTX file. Every record is built from a seed, so different evidence files give different processes and times.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from raven.collectors.evtx_loader import EvtxLoadError
from raven.collectors.raw_jsonl import write_raw_jsonl

EVTX_BYTES = b"ElfFile\x00" + bytes(8192)  # passes the upload checks; the fake loaders never read it


def evtx_bytes(salt: int = 0) -> bytes:
    """Fake EVTX content that differs by salt (so its SHA-256 differs)."""
    return EVTX_BYTES + salt.to_bytes(4, "big")


def synthetic_raw_records(seed: int = 0, file_creations: int = 12) -> list[dict[str, Any]]:
    """One process creation followed by file creations of the same process: matches rules R001 and R003."""
    pid = 1000 + seed
    guid = "{00000000-0000-0000-0000-%012d}" % pid
    base = seed * 3600  # evidence with different seeds are more than 300 s apart: separate sessions
    records: list[dict[str, Any]] = []

    def stamp(offset: int) -> str:
        total = base + offset
        hours, remainder = divmod(total, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"2026-09-13 {8 + hours:02d}:{minutes:02d}:{seconds:02d}.500000+00:00"

    records.append(
        {
            "event_id": 1,
            "time_created": stamp(0),
            "computer": "SYNTHETIC-LAB-HOST",
            "record_id": 1,
            "event_data": {
                "RuleName": "-",
                "UtcTime": "2026-09-13 08:00:00.500",
                "ProcessGuid": guid,
                "ProcessId": str(pid),
                "Image": f"C:\\Test\\synthetic{seed}.exe",
                "CommandLine": f"synthetic{seed}.exe --run",
                "User": "SYNTHETIC\\tester",
                "IntegrityLevel": "Medium",
                "Hashes": "SHA256=" + "AB" * 32,
                "ParentProcessGuid": "{00000000-0000-0000-0000-000000000001}",
                "ParentProcessId": "900",
                "ParentImage": "C:\\Test\\parent.exe",
                "ParentCommandLine": "parent.exe",
            },
            "raw_xml": "<Event>1</Event>",
        }
    )
    for number in range(file_creations):
        records.append(
            {
                "event_id": 11,
                "time_created": stamp(1 + number),
                "computer": "SYNTHETIC-LAB-HOST",
                "record_id": 2 + number,
                "event_data": {
                    "UtcTime": "2026-09-13 08:00:01.500",
                    "ProcessGuid": guid,
                    "ProcessId": str(pid),
                    "Image": f"C:\\Test\\synthetic{seed}.exe",
                    "TargetFilename": f"C:\\Test\\seed{seed}\\file_{number:03d}.txt",
                    "User": "SYNTHETIC\\tester",
                },
                "raw_xml": f"<Event>{2 + number}</Event>",
            }
        )
    return records


def fake_loader(seed_of=None, failing_ids=()):
    """A loader with the signature of load_evtx. The evidence ID is the stem of the file name (<id>.evtx).

    seed_of(evidence_id) -> seed (default: the ID itself). Evidence IDs in failing_ids raise EvtxLoadError.
    The loader records its calls in loader.calls.
    """

    def loader(input_evtx: Path, output_jsonl: Path) -> int:
        evidence_id = int(Path(input_evtx).stem)
        loader.calls.append(evidence_id)
        if evidence_id in failing_ids:
            raise EvtxLoadError(f"cannot open {evidence_id}.evtx as an EVTX file: synthetic failure")
        seed = seed_of(evidence_id) if seed_of else evidence_id
        return write_raw_jsonl(synthetic_raw_records(seed), output_jsonl)

    loader.calls = []
    return loader


def raw_lines(records) -> str:
    """Raw records as the text a collector would append to its file (one JSON object per line, LF line ends)."""
    from raven.collectors.raw_jsonl import serialize_record

    return "".join(serialize_record(record) + "\n" for record in records)
