"""Compare the ways the spec leaves open for searching a rule window (see engine.py) on a database.

    python -m raven.correlation.explore <raven.db>

Every combination of EngineOptions is run on the events of the database with the shipped rules. For
each one it prints the number of groups per rule and the number of distinct events in all groups, and
how far these are from the reference numbers of the spec (section 6.5b): 19, 14 and 54 groups for
R001, R002 and R003, and 558 file creation, 14 network connection and 25 process creation events in
the groups. The best matches come first. The database is opened read-only.
"""

from __future__ import annotations

import argparse
import itertools
import sqlite3
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from raven.correlation.engine import GROUP_POLICIES, MEMBERSHIPS, STEP_ORDERS, EngineOptions, EventPoint, find_groups
from raven.correlation.rule_schema import Rule, RuleError, load_rules

DEFAULT_TARGET: dict[str, dict[str, int]] = {
    "groups": {"RAVEN-R001": 19, "RAVEN-R002": 14, "RAVEN-R003": 54},
    "union": {"file_create": 558, "network_connection": 14, "process_creation": 25},
}
EXAMPLE_GROUP_ID = "RAVEN-R001:1224:2026-09-13T08:39:49.695Z"


@dataclass(frozen=True)
class VariantResult:
    options: EngineOptions
    groups_by_rule: dict[str, int]
    union_by_type: dict[str, int]
    union_total: int
    distance: int
    has_example_group: bool


def explore(
    rules: list[Rule],
    events: list[EventPoint],
    target: dict[str, dict[str, int]] = DEFAULT_TARGET,
    example_group_id: str = EXAMPLE_GROUP_ID,
) -> list[VariantResult]:
    """Run every combination of engine options and rank them by distance from the target numbers."""
    type_by_row = {event.row_id: event.event_type for event in events}
    results: list[VariantResult] = []
    for order, policy, membership, inclusive in itertools.product(STEP_ORDERS, GROUP_POLICIES, MEMBERSHIPS, (True, False)):
        options = EngineOptions(order, policy, membership, inclusive)
        groups_by_rule: dict[str, int] = {}
        union: set[int] = set()
        ids: set[str] = set()
        for rule in rules:
            found = find_groups(rule, events, options)
            groups_by_rule[rule.rule_id] = len(found)
            for group in found:
                union.update(group.event_row_ids)
                ids.add(group.group_id)
        union_by_type: dict[str, int] = {}
        for row_id in union:
            union_by_type[type_by_row[row_id]] = union_by_type.get(type_by_row[row_id], 0) + 1
        distance = sum(abs(groups_by_rule.get(rule_id, 0) - number) for rule_id, number in target["groups"].items())
        distance += sum(abs(union_by_type.get(kind, 0) - number) for kind, number in target["union"].items())
        results.append(
            VariantResult(options, groups_by_rule, dict(sorted(union_by_type.items())), len(union), distance, example_group_id in ids)
        )
    results.sort(key=lambda r: (r.distance, r.options.label()))
    return results


def load_events(db_path: str) -> list[EventPoint]:
    """The supported events of a workspace database (read-only), in table order."""
    path = Path(db_path)
    if not path.is_file():
        raise FileNotFoundError(f"database file not found: {path}")
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT id, raw_event_ref, event_type, timestamp, process_id, process_guid FROM events "
            "WHERE event_type != 'unsupported' ORDER BY id"
        ).fetchall()
    finally:
        connection.close()
    return [EventPoint.create(*row) for row in rows]


def format_result(rank: int, result: VariantResult, rule_ids: Sequence[str]) -> str:
    options = result.options
    rules_text = " ".join(f"{rule_id.replace('RAVEN-', '')} {result.groups_by_rule.get(rule_id, 0):>3}" for rule_id in rule_ids)
    union = result.union_by_type
    return (
        f"{rank:>2}. distance {result.distance:>4} | {options.step_order:<6} {options.group_policy:<12} "
        f"{options.membership:<7} {'incl' if options.inclusive_window else 'excl'} | groups {rules_text} | "
        f"union file {union.get('file_create', 0):>4} net {union.get('network_connection', 0):>3} "
        f"proc {union.get('process_creation', 0):>3} total {result.union_total:>4} | "
        f"spec example group {'yes' if result.has_example_group else 'no'}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m raven.correlation.explore",
        description="Run every engine option combination on a database and rank them against the spec numbers.",
    )
    parser.add_argument("database")
    parser.add_argument("--top", type=int, default=12, help="how many results to print (default 12)")
    args = parser.parse_args(argv)
    try:
        rules = load_rules()
        events = load_events(args.database)
    except (OSError, RuleError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    results = explore(rules, events)
    rule_ids = [rule.rule_id for rule in rules]
    print(f"events used: {len(events)} (unsupported events are not used)")
    print(
        "spec numbers: groups R001 19, R002 14, R003 54; events in groups file_create 558, "
        "network_connection 14, process_creation 25 (597 together)"
    )
    print(f"combinations tried: {len(results)}; exact matches: {sum(1 for r in results if r.distance == 0)}")
    for rank, result in enumerate(results[: max(1, args.top)], start=1):
        print(format_result(rank, result, rule_ids))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
