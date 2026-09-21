"""Run the impact stage on a workspace database (spec section 7).

    run_impact(session_factory, summary_file=None) -> summary

For every attack session the events of its timeline are analyzed (see analyzer.py) and four rows are
stored in impact_analysis, one per category. Delete and rebuild: every run replaces all impact rows,
so running it again gives the same rows.

Run from the command line:

    python -m raven.impact.persist <raven.db> [--summary <summary.json>]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, insert, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from raven.collectors.raw_jsonl import sha256_file
from raven.database.models import AttackSession, Event, ImpactAnalysis, TimelineEvent
from raven.database.session import open_workspace_database
from raven.fileio import write_text_atomic
from raven.impact.analyzer import ImpactResult, analyze_session


def _timeline_events(session: Session, attack_session_id: int) -> list[dict[str, Any]]:
    rows = session.execute(
        select(Event).join(TimelineEvent, TimelineEvent.event_id == Event.id)
        .where(TimelineEvent.attack_session_id == attack_session_id)
        .order_by(TimelineEvent.sequence_number)
    ).scalars()
    return [{column.name: getattr(row, column.name) for column in Event.__table__.columns} for row in rows]


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def run_impact(session_factory: sessionmaker[Session], summary_file: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """Analyze every attack session, store the results and return the summary."""
    per_session: list[tuple[AttackSession, list[ImpactResult]]] = []
    with session_factory() as session:
        for row in session.execute(select(AttackSession).order_by(AttackSession.id)).scalars():
            per_session.append((row, analyze_session(_timeline_events(session, row.id))))

        session.execute(delete(ImpactAnalysis))
        rows = [
            {
                "attack_session_id": row.id,
                "impact_category": result.category,
                "impact_score": result.impact_score,
                "affected_assets": _json(list(result.affected_assets)),
                "analysis": _json(result.analysis),
            }
            for row, results in per_session
            for result in results
        ]
        if rows:
            session.execute(insert(ImpactAnalysis), rows)
        session.commit()

    summary: dict[str, Any] = {
        "totals": {"sessions": len(per_session), "impact_rows": sum(len(results) for _row, results in per_session)},
        "sessions": [
            {
                "session_id": row.session_id,
                "categories": [
                    {
                        "category": result.category,
                        "impact_score": result.impact_score,
                        "event_count": result.analysis["event_count"],
                        "first_assets": list(result.affected_assets[:3]),
                        "details": result.analysis["details"],
                    }
                    for result in results
                ],
            }
            for row, results in per_session
        ],
    }
    if summary_file is not None:
        write_text_atomic(summary_file, json.dumps(summary, indent=2, ensure_ascii=True) + "\n")
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m raven.impact.persist",
        description="Compute the impact analysis of every attack session of a workspace database.",
    )
    parser.add_argument("database", help="path of the raven.db file")
    parser.add_argument("--summary", dest="summary_file", help="write the summary to this JSON file")
    args = parser.parse_args(argv)
    factory = None
    try:
        if not os.path.isfile(args.database):
            raise FileNotFoundError(f"database file not found: {args.database}")
        factory = open_workspace_database(args.database)
        summary = run_impact(factory, args.summary_file)
    except (OSError, ValueError, SQLAlchemyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        if factory is not None:
            factory.kw["bind"].dispose()
    print(f"attack sessions: {summary['totals']['sessions']}")
    print(f"impact rows: {summary['totals']['impact_rows']}")
    for item in summary["sessions"]:
        print(f"session {item['session_id']}")
        for category in item["categories"]:
            print(f"  {category['category']}: score {category['impact_score']} distinct assets, {category['event_count']} events")
            for asset in category["first_assets"]:
                print(f"    e.g. {asset}")
            print(f"    details: {json.dumps(category['details'], sort_keys=True)}")
    if args.summary_file:
        print(f"summary sha256: {sha256_file(args.summary_file)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
