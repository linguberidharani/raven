"""Ingest stage: deduplicated normalized events into the events table (spec section 7).

    ingest_events(deduplicated_jsonl, summary_json, session_factory) -> counts

Idempotent: an event whose raw_event_ref is already in the table is skipped, so ingesting the same
file again inserts nothing. All inserts of one call happen in one transaction: if anything fails,
nothing is inserted.

Run from the command line:

    python -m raven.database.ingest <deduplicated.jsonl> <raven.db> [--summary <summary.json>]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from raven.database.models import Event
from raven.database.session import open_workspace_database
from raven.fileio import write_text_atomic
from raven.parsers.normalized_jsonl import NormalizedEventError, read_normalized_jsonl


def ingest_events(
    input_jsonl: str | os.PathLike[str],
    summary_json: str | os.PathLike[str] | None,
    session_factory: sessionmaker[Session],
    batch_size: int = 1000,
) -> dict[str, int]:
    """Insert the events of a normalized JSONL file that are not in the database yet.

    Returns {"read": ..., "inserted": ..., "skipped_existing": ...}. When summary_json is given, the
    same counts are written there as JSON. An event that appears twice in the input counts as skipped.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    read = inserted = skipped = 0
    with session_factory() as session:
        known = set(session.scalars(select(Event.raw_event_ref)))
        batch: list[dict[str, Any]] = []
        for event in read_normalized_jsonl(input_jsonl):
            read += 1
            reference = event["raw_event_ref"]
            if reference in known:
                skipped += 1
                continue
            known.add(reference)
            batch.append(event)
            if len(batch) >= batch_size:
                session.execute(insert(Event), batch)
                inserted += len(batch)
                batch = []
        if batch:
            session.execute(insert(Event), batch)
            inserted += len(batch)
        session.commit()
    summary = {"read": read, "inserted": inserted, "skipped_existing": skipped}
    if summary_json is not None:
        write_text_atomic(summary_json, json.dumps(summary, sort_keys=True, indent=2) + "\n")
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m raven.database.ingest",
        description="Insert the events of a deduplicated normalized JSONL file into a workspace database.",
    )
    parser.add_argument("deduplicated_jsonl")
    parser.add_argument("database", help="path of the raven.db file (created when missing)")
    parser.add_argument("--summary", dest="summary_json", help="also write the counts to this JSON file")
    args = parser.parse_args(argv)
    factory = None
    try:
        factory = open_workspace_database(args.database)
        summary = ingest_events(args.deduplicated_jsonl, args.summary_json, factory)
    except (OSError, ValueError, NormalizedEventError, SQLAlchemyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        if factory is not None:
            factory.kw["bind"].dispose()
    print(f"events read:      {summary['read']}")
    print(f"inserted:         {summary['inserted']}")
    print(f"skipped existing: {summary['skipped_existing']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
