"""Run the reconstruction stage on a workspace database (spec section 7).

    run_reconstruction(session_factory, mapping_file=None, merge_gap_seconds=300) -> summary

Reads the correlation groups from correlated_events (with the computer and times of their events and the
severity of their rule), merges them into attack sessions (see sequencer.py) and stores one row per session
in attack_sessions. The optional mapping file lists every session with its groups.

Running it again gives the same session IDs and the same rows. A session that is no longer produced is
removed together with its timeline, impact and report rows (those stages are rebuilt after this one).
A session that is still produced keeps its row and its database ID.

Run from the command line:

    python -m raven.reconstruction.persist <raven.db> [--mapping <mapping.json>] [--merge-gap 300]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from raven.collectors.raw_jsonl import sha256_file
from raven.correlation.engine import timestamp_to_ms
from raven.database.models import AttackSession, CorrelatedEvent, CorrelationRule, Event, ImpactAnalysis, Report, TimelineEvent
from raven.database.session import open_workspace_database
from raven.fileio import write_text_atomic
from raven.reconstruction.sequencer import DEFAULT_MERGE_GAP_SECONDS, GroupInfo, ReconstructionError, SessionPlan, build_sessions


def _rule_severities(session: Session) -> dict[str, str]:
    severities: dict[str, str] = {}
    for definition in session.scalars(select(CorrelationRule.rule_definition)):
        data = json.loads(definition)
        severities[data["rule_id"]] = data["severity"]
    return severities


def load_groups(session: Session) -> list[GroupInfo]:
    """The correlation groups stored in the database, with the computer and times of their events."""
    severities = _rule_severities(session)
    rows = session.execute(
        select(CorrelatedEvent.correlation_group_id, CorrelatedEvent.correlation_type, Event.computer, Event.timestamp).join(
            Event, Event.id == CorrelatedEvent.event_id
        )
    ).all()
    collected: dict[str, dict[str, Any]] = {}
    for group_id, rule_id, computer, timestamp in rows:
        entry = collected.setdefault(group_id, {"rule_id": rule_id, "computers": set(), "times": []})
        if entry["rule_id"] != rule_id:
            raise ReconstructionError(f"group {group_id} belongs to more than one rule")
        entry["computers"].add(computer)
        entry["times"].append(timestamp)

    groups: list[GroupInfo] = []
    for group_id in sorted(collected):
        entry = collected[group_id]
        if len(entry["computers"]) != 1:
            raise ReconstructionError(
                f"group {group_id} has events of several computers ({', '.join(sorted(entry['computers']))}); "
                "correlation is not scoped per computer yet"
            )
        if entry["rule_id"] not in severities:
            raise ReconstructionError(f"group {group_id}: rule {entry['rule_id']} is not in correlation_rules")
        times = sorted(entry["times"])
        groups.append(
            GroupInfo(
                group_id=group_id,
                rule_id=entry["rule_id"],
                severity=severities[entry["rule_id"]],
                computer=next(iter(entry["computers"])),
                start_time=times[0],
                end_time=times[-1],
                start_ms=timestamp_to_ms(times[0]),
                end_ms=timestamp_to_ms(times[-1]),
                event_count=len(times),
            )
        )
    return groups


def _store(session: Session, plans: list[SessionPlan]) -> None:
    existing = {row.session_id: row.id for row in session.execute(select(AttackSession.session_id, AttackSession.id))}
    wanted = {plan.session_id for plan in plans}
    stale = [row_id for session_id, row_id in existing.items() if session_id not in wanted]
    if stale:
        session.execute(delete(TimelineEvent).where(TimelineEvent.attack_session_id.in_(stale)))
        session.execute(delete(ImpactAnalysis).where(ImpactAnalysis.attack_session_id.in_(stale)))
        session.execute(delete(Report).where(Report.attack_session_id.in_(stale)))
        session.execute(delete(AttackSession).where(AttackSession.id.in_(stale)))
    for plan in plans:
        values = {
            "start_time": plan.start_time,
            "end_time": plan.end_time,
            "description": plan.description,
            "severity": plan.severity,
            "confidence": None,
        }
        if plan.session_id in existing:
            session.execute(update(AttackSession).where(AttackSession.session_id == plan.session_id).values(**values))
        else:
            session.execute(insert(AttackSession).values(session_id=plan.session_id, **values))


def run_reconstruction(
    session_factory: sessionmaker[Session],
    mapping_file: str | os.PathLike[str] | None = None,
    merge_gap_seconds: int = DEFAULT_MERGE_GAP_SECONDS,
) -> dict[str, Any]:
    """Build the attack sessions from the stored correlation groups, store them and return the summary."""
    with session_factory() as session:
        groups = load_groups(session)
        plans = build_sessions(groups, merge_gap_seconds)
        _store(session, plans)
        session.commit()

    summary: dict[str, Any] = {
        "merge_gap_seconds": merge_gap_seconds,
        "totals": {"groups": len(groups), "sessions": len(plans)},
        "sessions": [
            {
                "session_id": plan.session_id,
                "computer": plan.computer,
                "start_time": plan.start_time,
                "end_time": plan.end_time,
                "severity": plan.severity,
                "confidence": None,
                "description": plan.description,
                "group_count": len(plan.groups),
                "rule_ids": list(plan.rule_ids),
                "groups": [
                    {
                        "group_id": group.group_id,
                        "rule_id": group.rule_id,
                        "severity": group.severity,
                        "start_time": group.start_time,
                        "end_time": group.end_time,
                        "event_count": group.event_count,
                    }
                    for group in plan.groups
                ],
            }
            for plan in plans
        ],
    }
    if mapping_file is not None:
        write_text_atomic(mapping_file, json.dumps(summary, indent=2, ensure_ascii=True) + "\n")
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m raven.reconstruction.persist",
        description="Merge the correlation groups of a workspace database into attack sessions.",
    )
    parser.add_argument("database", help="path of the raven.db file")
    parser.add_argument("--mapping", dest="mapping_file", help="write the session to group mapping to this JSON file")
    parser.add_argument("--merge-gap", type=int, default=DEFAULT_MERGE_GAP_SECONDS, help="merge gap in seconds (default 300)")
    args = parser.parse_args(argv)
    factory = None
    try:
        if not os.path.isfile(args.database):
            raise FileNotFoundError(f"database file not found: {args.database}")
        factory = open_workspace_database(args.database)
        summary = run_reconstruction(factory, args.mapping_file, args.merge_gap)
    except (OSError, ReconstructionError, SQLAlchemyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        if factory is not None:
            factory.kw["bind"].dispose()
    print(f"merge gap: {summary['merge_gap_seconds']} s")
    print(f"correlation groups read: {summary['totals']['groups']}")
    print(f"attack sessions: {summary['totals']['sessions']}")
    for item in summary["sessions"]:
        print(f"session {item['session_id']}")
        print(f"  computer:   {item['computer']}")
        print(f"  start:      {item['start_time']}")
        print(f"  end:        {item['end_time']}")
        print(f"  severity:   {item['severity']}")
        print(f"  confidence: {item['confidence']}")
        print(f"  groups:     {item['group_count']} (rules: {', '.join(item['rule_ids'])})")
        print(f"  description: {item['description']}")
    if args.mapping_file:
        print(f"mapping sha256: {sha256_file(args.mapping_file)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
