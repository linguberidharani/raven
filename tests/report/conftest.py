"""Shared helpers for the report tests: a RARF document from a small synthetic workspace.

All events are SYNTHETIC test data. Databases live in temporary directories only.
"""

import pytest

from raven.database.session import open_workspace_database
from raven.rarf.builder import build_rarf, list_session_ids
from tests.rarf.conftest import prepare_workspace, rows_for


@pytest.fixture
def rarf(tmp_path):
    factory = open_workspace_database(tmp_path / "workspace" / "raven.db")
    try:
        prepare_workspace(factory, rows_for(10, 0))
        (session_id,) = list_session_ids(factory)
        return build_rarf(factory, session_id)
    finally:
        factory.kw["bind"].dispose()


@pytest.fixture
def rarf_with_network(tmp_path):
    """A workspace whose session also holds a network connection (rule R002 matches too)."""
    from sqlalchemy import insert

    from raven.correlation.runner import run_correlation
    from raven.database.models import Event
    from raven.impact.persist import run_impact
    from raven.parsers.schema import NORMALIZED_FIELDS
    from raven.reconstruction.persist import run_reconstruction
    from raven.timeline.persist import run_timeline
    from tests.rarf.conftest import event_row

    rows = [event_row(1, "process_creation", 0, 30), event_row(2, "network_connection", 3, 30), event_row(3, "file_create", 6, 30)]
    rows[1].update(ip_address="10.0.0.1", port=443, protocol="tcp", initiated=True, file_path=None)
    factory = open_workspace_database(tmp_path / "workspace2" / "raven.db")
    try:
        with factory.kw["bind"].begin() as connection:
            connection.execute(insert(Event), rows)
        run_correlation(factory, None)
        run_reconstruction(factory, None)
        run_timeline(factory)
        run_impact(factory)
        (session_id,) = list_session_ids(factory)
        return build_rarf(factory, session_id)
    finally:
        factory.kw["bind"].dispose()
