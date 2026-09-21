"""Run the correlation stage on a workspace database (spec section 7).

    run_correlation(session_factory, summary_file) -> summary

Reads the supported events of the events table, applies the rules, and stores the result:

    correlation_rules   one row per rule (rule_name unique, rule_definition as JSON, enabled)
    correlated_events   one row per event of every group: rule, event, group ID, correlation_type = rule ID
    summary file        for every group WHY it matched: the rule, the steps with required and found
                        counts, the window and the event references

Running it again gives the same rows and the same summary file: the correlated_events rows of the
earlier run are removed and rebuilt in the same transaction. Rules that are no longer in the rule set
stay in correlation_rules with enabled = false.

Run from the command line:

    python -m raven.correlation.runner <raven.db> [--summary <summary.json>]
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
from raven.correlation.engine import EngineOptions, EventPoint, explain_group, find_all_groups
from raven.correlation.rule_schema import Rule, RuleError, load_rules
from raven.database.models import CorrelatedEvent, CorrelationRule, Event
from raven.database.session import open_workspace_database
from raven.fileio import write_text_atomic


def _load_events(session: Session) -> list[EventPoint]:
    rows = session.execute(
        select(Event.id, Event.raw_event_ref, Event.event_type, Event.timestamp, Event.process_id, Event.process_guid)
        .where(Event.event_type != "unsupported")
        .order_by(Event.id)
    ).all()
    return [EventPoint.create(*row) for row in rows]


def _sync_rules(session: Session, rules: list[Rule]) -> dict[str, int]:
    """Make correlation_rules match the rule set. Return rule_id -> table id."""
    existing = {row.rule_name: row for row in session.scalars(select(CorrelationRule))}
    ids: dict[str, int] = {}
    current_names = {rule.rule_name for rule in rules}
    for rule in rules:
        definition = json.dumps(rule.to_definition(), sort_keys=True)
        row = existing.get(rule.rule_name)
        if row is None:
            result = session.execute(
                insert(CorrelationRule).values(
                    rule_name=rule.rule_name, description=rule.description, rule_definition=definition, enabled=True
                )
            )
            ids[rule.rule_id] = int(result.inserted_primary_key[0])
        else:
            session.execute(
                update(CorrelationRule)
                .where(CorrelationRule.id == row.id)
                .values(description=rule.description, rule_definition=definition, enabled=True)
            )
            ids[rule.rule_id] = row.id
    for name, row in existing.items():
        if name not in current_names:
            session.execute(update(CorrelationRule).where(CorrelationRule.id == row.id).values(enabled=False))
    return ids


def run_correlation(
    session_factory: sessionmaker[Session],
    summary_file: str | os.PathLike[str] | None = None,
    rules: list[Rule] | None = None,
    options: EngineOptions | None = None,
) -> dict[str, Any]:
    """Find the correlation groups, store them, and return (and optionally write) the summary."""
    rule_set = load_rules() if rules is None else rules
    engine_options = EngineOptions() if options is None else options

    with session_factory() as session:
        events = _load_events(session)
        groups = find_all_groups(rule_set, events, engine_options)
        rule_ids = _sync_rules(session, rule_set)
        session.execute(delete(CorrelatedEvent))
        rows = [
            {
                "rule_id": rule_ids[group.rule_id],
                "event_id": row_id,
                "correlation_group_id": group.group_id,
                "correlation_type": group.rule_id,
            }
            for group in groups
            for row_id in group.event_row_ids
        ]
        if rows:
            session.execute(insert(CorrelatedEvent), rows)
        session.commit()

    by_row = {event.row_id: event for event in events}
    rules_by_id = {rule.rule_id: rule for rule in rule_set}
    distinct = {row_id for group in groups for row_id in group.event_row_ids}
    distinct_by_type: dict[str, int] = {}
    for row_id in distinct:
        kind = by_row[row_id].event_type
        distinct_by_type[kind] = distinct_by_type.get(kind, 0) + 1
    summary: dict[str, Any] = {
        "engine_options": {
            "step_order": engine_options.step_order,
            "group_policy": engine_options.group_policy,
            "membership": engine_options.membership,
            "inclusive_window": engine_options.inclusive_window,
        },
        "events_examined": len(events),
        "rules": [
            {
                "rule_id": rule.rule_id,
                "rule_name": rule.rule_name,
                "severity": rule.severity,
                "confidence": rule.confidence,
                "groups": sum(1 for group in groups if group.rule_id == rule.rule_id),
            }
            for rule in rule_set
        ],
        "totals": {
            "groups": len(groups),
            "correlated_event_rows": len(rows),
            "distinct_events": len(distinct),
            "distinct_events_by_type": dict(sorted(distinct_by_type.items())),
        },
        "groups": [explain_group(rules_by_id[group.rule_id], group, by_row) for group in groups],
    }
    if summary_file is not None:
        write_text_atomic(summary_file, json.dumps(summary, indent=2, ensure_ascii=True) + "\n")
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m raven.correlation.runner",
        description="Run the correlation rules on a workspace database and store the groups.",
    )
    parser.add_argument("database", help="path of the raven.db file")
    parser.add_argument("--summary", dest="summary_file", help="write the why-matched summary to this JSON file")
    args = parser.parse_args(argv)
    factory = None
    try:
        if not os.path.isfile(args.database):
            raise FileNotFoundError(f"database file not found: {args.database}")
        factory = open_workspace_database(args.database)
        summary = run_correlation(factory, args.summary_file)
    except (OSError, RuleError, SQLAlchemyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        if factory is not None:
            factory.kw["bind"].dispose()
    options = summary["engine_options"]
    print(f"engine options: {options['step_order']} / {options['group_policy']} / {options['membership']} / inclusive={options['inclusive_window']}")
    print(f"events examined: {summary['events_examined']}")
    for rule in summary["rules"]:
        print(f"{rule['rule_id']} ({rule['rule_name']}, {rule['severity']}, confidence {rule['confidence']}): {rule['groups']} groups")
    totals = summary["totals"]
    print(f"groups: {totals['groups']}")
    print(f"correlated_events rows: {totals['correlated_event_rows']}")
    print(f"distinct events in groups: {totals['distinct_events']}")
    for kind, number in totals["distinct_events_by_type"].items():
        print(f"  {kind}: {number}")
    if args.summary_file:
        print(f"summary sha256: {sha256_file(args.summary_file)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
