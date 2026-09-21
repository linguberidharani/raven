"""Shared helpers for the RARF tests: a small synthetic workspace with one attack session.

All events are SYNTHETIC test data. Databases live in temporary directories only.
"""

import pytest
from sqlalchemy import insert

from raven.correlation.runner import run_correlation
from raven.database.models import Event
from raven.database.session import open_workspace_database
from raven.impact.persist import run_impact
from raven.parsers.schema import NORMALIZED_FIELDS
from raven.reconstruction.persist import run_reconstruction
from raven.timeline.persist import run_timeline


def stamp(seconds):
    minutes, sec = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"2026-09-13T{8 + hours:02d}:{minutes:02d}:{sec:02d}.000Z"


def event_row(number, event_type, seconds, pid, computer="Dharani"):
    row = {name: None for name in NORMALIZED_FIELDS}
    row.update(
        raw_event_ref=f"1:{number}",
        event_id={"process_creation": 1, "network_connection": 3, "file_create": 11}[event_type],
        event_type=event_type,
        timestamp=stamp(seconds),
        computer=computer,
        process_id=pid,
        process_name=f"C:\\Test\\p{pid}.exe",
        file_path=f"C:\\Test\\{pid}_{number % 3}.txt" if event_type == "file_create" else None,
        user="SYNTHETIC\\tester",
        normalization_status="OK",
    )
    return row


def rows_for(pid, start, first_number=1):
    """A process creation and 12 file creations: one R001 group and one R003 group."""
    rows = [event_row(first_number, "process_creation", start, pid)]
    for i in range(12):
        rows.append(event_row(first_number + 1 + i, "file_create", start + 1 + i, pid))
    return rows


def prepare_workspace(factory, rows, through="impact"):
    with factory.kw["bind"].begin() as connection:
        connection.execute(insert(Event), rows)
    run_correlation(factory, None)
    run_reconstruction(factory, None)
    if through in ("timeline", "impact"):
        run_timeline(factory)
    if through == "impact":
        run_impact(factory)


@pytest.fixture
def factory(tmp_path):
    factory = open_workspace_database(tmp_path / "workspace" / "raven.db")
    yield factory
    factory.kw["bind"].dispose()
