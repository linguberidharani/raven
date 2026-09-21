"""Run the timeline stage on a workspace database (spec section 7).

    run_timeline(session_factory, summary_file=None) -> summary

For every attack session, the timeline holds the events of the session's groups (see builder.py). A
group belongs to a session when it is on the session's computer and lies inside the session's time
span; the computer is found from the session's first group, which its session ID names.

Rebuilding replaces the timeline rows of all sessions, so running it again gives the same rows.

Run from the command line:

    python -m raven.timeline.persist <raven.db> [--summary <summary.json>]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import delete, insert, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from raven.collectors.raw_jsonl import sha256_file
from raven.correlation.engine import timestamp_to_ms
from raven.database.models import AttackSession, CorrelatedEvent, Event, TimelineEvent
from raven.database.session import open_workspace_database
from raven.fileio import write_text_atomic
from raven.reconstruction.persist import load_groups
from raven.reconstruction.sequencer import GroupInfo, sanitize_id_part
from raven.timeline.builder import TimelineEntry, build_timeline

_CHUNK = 500


class TimelineError(ValueError):
    """The timeline cannot be built from what is in the database."""


def _chunks(items: list[Any], size: int = _CHUNK) -> Iterable[list[Any]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def session_groups(session_id: str, start_time: str, end_time: str, groups: list[GroupInfo]) -> list[GroupInfo]:
    """The groups of one attack session, found from its ID, its time span and the stored groups."""
    firsts = [
        group
        for group in groups
        if session_id == f"RAVEN-SESSION-{sanitize_id_part(group.computer)}-{sanitize_id_part(group.group_id)}"
    ]
    if len(firsts) != 1:
        raise TimelineError(f"cannot find the first group of session {session_id}; run the reconstruction again")
    computer = firsts[0].computer
    start_ms, end_ms = timestamp_to_ms(start_time), timestamp_to_ms(end_time)
    return [g for g in groups if g.computer == computer and start_ms <= g.start_ms and g.end_ms <= end_ms]


def _event_rows(session: Session, group_ids: list[str]) -> list[dict[str, Any]]:
    event_ids: set[int] = set()
    for chunk in _chunks(sorted(group_ids)):
        event_ids.update(session.scalars(select(CorrelatedEvent.event_id).where(CorrelatedEvent.correlation_group_id.in_(chunk))))
    rows: list[dict[str, Any]] = []
    for chunk in _chunks(sorted(event_ids)):
        for event in session.scalars(select(Event).where(Event.id.in_(chunk))):
            rows.append({column.name: getattr(event, column.name) for column in Event.__table__.columns})
    return rows


def run_timeline(session_factory: sessionmaker[Session], summary_file: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """Build and store the timeline of every attack session and return the summary."""
    results: list[tuple[AttackSession, list[GroupInfo], list[TimelineEntry], list[dict[str, Any]]]] = []
    with session_factory() as session:
        groups = load_groups(session)
        sessions = session.execute(select(AttackSession).order_by(AttackSession.id)).scalars().all()
        for row in sessions:
            members = session_groups(row.session_id, row.start_time, row.end_time, groups)
            events = _event_rows(session, [group.group_id for group in members])
            results.append((row, members, build_timeline(events), events))

        session.execute(delete(TimelineEvent))
        rows = [
            {
                "attack_session_id": row.id,
                "event_id": entry.event_row_id,
                "sequence_number": entry.sequence_number,
                "timeline_timestamp": entry.timestamp,
                "description": entry.description,
            }
            for row, _members, entries, _events in results
            for entry in entries
        ]
        if rows:
            session.execute(insert(TimelineEvent), rows)
        session.commit()

    summary: dict[str, Any] = {"sessions": [], "totals": {"sessions": len(results), "timeline_events": sum(len(r[2]) for r in results)}}
    for row, members, entries, events in results:
        type_by_id = {event["id"]: event["event_type"] for event in events}
        by_type: dict[str, int] = {}
        for entry in entries:
            kind = type_by_id[entry.event_row_id]
            by_type[kind] = by_type.get(kind, 0) + 1
        summary["sessions"].append(
            {
                "session_id": row.session_id,
                "groups": len(members),
                "timeline_events": len(entries),
                "events_by_type": dict(sorted(by_type.items())),
                "first_timestamp": entries[0].timestamp if entries else None,
                "last_timestamp": entries[-1].timestamp if entries else None,
                "first_descriptions": [entry.description for entry in entries[:3]],
                "last_description": entries[-1].description if entries else None,
            }
        )
    if summary_file is not None:
        write_text_atomic(summary_file, json.dumps(summary, indent=2, ensure_ascii=True) + "\n")
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m raven.timeline.persist",
        description="Build the timeline of every attack session of a workspace database.",
    )
    parser.add_argument("database", help="path of the raven.db file")
    parser.add_argument("--summary", dest="summary_file", help="write the summary to this JSON file")
    args = parser.parse_args(argv)
    factory = None
    try:
        if not os.path.isfile(args.database):
            raise FileNotFoundError(f"database file not found: {args.database}")
        factory = open_workspace_database(args.database)
        summary = run_timeline(factory, args.summary_file)
    except (OSError, ValueError, SQLAlchemyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        if factory is not None:
            factory.kw["bind"].dispose()
    print(f"attack sessions: {summary['totals']['sessions']}")
    print(f"timeline events: {summary['totals']['timeline_events']}")
    for item in summary["sessions"]:
        print(f"session {item['session_id']}")
        print(f"  groups: {item['groups']}")
        print(f"  timeline events: {item['timeline_events']}")
        for kind, number in item["events_by_type"].items():
            print(f"    {kind}: {number}")
        print(f"  first: {item['first_timestamp']}")
        print(f"  last:  {item['last_timestamp']}")
        for number, text in enumerate(item["first_descriptions"], start=1):
            print(f"  description {number}: {text}")
        print(f"  last description: {item['last_description']}")
    if args.summary_file:
        print(f"summary sha256: {sha256_file(args.summary_file)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
