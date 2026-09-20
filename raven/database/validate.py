"""Validation of a workspace database (spec stage S4).

    python -m raven.database.validate <raven.db>

Checks and prints: the 7 expected tables exist, row counts per table, events by status and type,
no repeated raw_event_ref, SQLite integrity_check and foreign_key_check. The exit code is 0 only when
every check passes. The database is opened read-only; nothing in it is changed.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from raven.database.models import EXPECTED_TABLES


def validate_database(db_path: str) -> dict[str, Any]:
    """Return the findings for a database file; the key "problems" lists what is wrong."""
    path = Path(db_path)
    if not path.is_file():
        raise FileNotFoundError(f"database file not found: {path}")
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        problems: list[str] = []
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = [name for name in EXPECTED_TABLES if name not in tables]
        if missing:
            problems.append("missing tables: " + ", ".join(missing))
        counts = {name: connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] for name in EXPECTED_TABLES if name in tables}

        by_status: dict[str, int] = {}
        by_type: dict[str, int] = {}
        repeated = 0
        if "events" in tables:
            by_status = dict(connection.execute("SELECT normalization_status, COUNT(*) FROM events GROUP BY 1 ORDER BY 1"))
            by_type = dict(connection.execute("SELECT event_type, COUNT(*) FROM events GROUP BY 1 ORDER BY 1"))
            repeated = connection.execute(
                "SELECT COUNT(*) FROM (SELECT raw_event_ref FROM events GROUP BY raw_event_ref HAVING COUNT(*) > 1)"
            ).fetchone()[0]
            if repeated:
                problems.append(f"{repeated} raw_event_ref values occur more than once")

        integrity = [row[0] for row in connection.execute("PRAGMA integrity_check")]
        if integrity != ["ok"]:
            problems.append("integrity_check: " + "; ".join(integrity))
        foreign = connection.execute("PRAGMA foreign_key_check").fetchall()
        if foreign:
            problems.append(f"foreign_key_check found {len(foreign)} broken references")
        return {
            "tables_missing": missing,
            "row_counts": counts,
            "events_by_status": by_status,
            "events_by_type": by_type,
            "repeated_raw_event_refs": repeated,
            "integrity_check": integrity,
            "foreign_key_problems": len(foreign),
            "problems": problems,
        }
    finally:
        connection.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m raven.database.validate", description="Validate a workspace database.")
    parser.add_argument("database")
    args = parser.parse_args(argv)
    try:
        result = validate_database(args.database)
    except (OSError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"tables expected: {len(EXPECTED_TABLES)}, missing: {', '.join(result['tables_missing']) or 'none'}")
    for name, number in result["row_counts"].items():
        print(f"rows in {name}: {number}")
    for status, number in result["events_by_status"].items():
        print(f"events with status {status}: {number}")
    for event_type, number in result["events_by_type"].items():
        print(f"events of type {event_type}: {number}")
    print(f"repeated raw_event_ref values: {result['repeated_raw_event_refs']}")
    print(f"integrity_check: {', '.join(result['integrity_check'])}")
    print(f"foreign_key_check problems: {result['foreign_key_problems']}")
    if result["problems"]:
        for problem in result["problems"]:
            print(f"PROBLEM: {problem}")
        return 1
    print("database is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
