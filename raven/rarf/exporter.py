"""Write the RARF files of a workspace database (spec sections 6.10 and 7).

    export_rarf(session_factory, output_dir) -> list of exported files

One file RARF-<session_id>.json per attack session, written only when the document is valid. The text is
deterministic (fixed key order, 2-space indent, ASCII only, LF line ends), so the same database always
gives byte-identical files.

Run from the command line:

    python -m raven.rarf.exporter <raven.db> <output folder>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from raven.collectors.raw_jsonl import sha256_file
from raven.database.session import open_workspace_database
from raven.fileio import write_text_atomic
from raven.rarf.builder import RarfError, build_rarf, list_session_ids
from raven.rarf.schema import validate_rarf


@dataclass(frozen=True)
class ExportedRarf:
    session_id: str
    path: Path
    document: dict[str, Any]


def rarf_text(document: dict[str, Any]) -> str:
    """The deterministic JSON text of a RARF document."""
    return json.dumps(document, indent=2, ensure_ascii=True) + "\n"


def export_rarf(session_factory: sessionmaker[Session], output_dir: str | os.PathLike[str]) -> list[ExportedRarf]:
    """Build, validate and write the RARF file of every attack session."""
    folder = Path(output_dir)
    exported: list[ExportedRarf] = []
    for session_id in list_session_ids(session_factory):
        document = build_rarf(session_factory, session_id)
        problems = validate_rarf(document)
        if problems:
            raise RarfError(f"RARF of {session_id} is not valid: " + "; ".join(problems))
        path = folder / f"RARF-{session_id}.json"
        write_text_atomic(path, rarf_text(document))
        exported.append(ExportedRarf(session_id, path, document))
    return exported


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m raven.rarf.exporter",
        description="Write RARF-<session_id>.json for every attack session of a workspace database.",
    )
    parser.add_argument("database", help="path of the raven.db file")
    parser.add_argument("output_dir", help="folder for the RARF files")
    args = parser.parse_args(argv)
    factory = None
    try:
        if not os.path.isfile(args.database):
            raise FileNotFoundError(f"database file not found: {args.database}")
        factory = open_workspace_database(args.database)
        exported = export_rarf(factory, args.output_dir)
    except (OSError, ValueError, SQLAlchemyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        if factory is not None:
            factory.kw["bind"].dispose()
    print(f"RARF files written: {len(exported)}")
    for item in exported:
        document = item.document
        trace = document["traceability"]
        print(f"file: {item.path}")
        print(f"  bytes:  {item.path.stat().st_size}")
        print(f"  sha256: {sha256_file(item.path)}")
        print(f"  rarf_version: {document['rarf_version']}, rarf_id: {document['rarf_id']}")
        print(f"  validation: valid")
        print(f"  correlation groups: {len(document['detection']['correlation_groups'])}, rules: {len(document['detection']['rules'])}")
        print(f"  timeline events: {len(document['timeline']['events'])}")
        for name, category in document["impact"]["categories"].items():
            print(f"  impact {name}: score {category['impact_score']}, events {category['analysis']['event_count']}")
        print(
            "  traceability: "
            f"event_ids {len(trace['event_ids'])}, raw_event_refs {len(trace['raw_event_refs'])}, "
            f"correlation_group_ids {len(trace['correlation_group_ids'])}, "
            f"timeline_event_ids {len(trace['timeline_event_ids'])}, impact_analysis_ids {len(trace['impact_analysis_ids'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
