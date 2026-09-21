"""Shared fixtures for the reference-data integration tests.

The reference file is real telemetry and is never committed (*.evtx is ignored). Put it at
tests/fixtures/sysmon_export.evtx to run these tests; without it they are skipped.

The pipeline up to correlation runs ONCE per test session in a temporary directory (never the real data
folder). Each test module that needs a database gets its own copy of the result, so stages run by one
module cannot disturb another.
"""

import shutil
from pathlib import Path

import pytest

from raven.collectors.evtx_loader import load_evtx
from raven.correlation.runner import run_correlation
from raven.database.ingest import ingest_events
from raven.database.session import open_workspace_database
from raven.parsers.deduplicate import deduplicate
from raven.parsers.normalizer import normalize_all

REFERENCE_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sysmon_export.evtx"
REFERENCE_SIZE = 3_215_360


@pytest.fixture(scope="session")
def reference_template_db(tmp_path_factory):
    """Path of a database holding the reference events and their correlation groups."""
    if not REFERENCE_FIXTURE.is_file():
        pytest.skip(f"reference file not present: {REFERENCE_FIXTURE}")
    if REFERENCE_FIXTURE.stat().st_size != REFERENCE_SIZE:
        pytest.skip(f"{REFERENCE_FIXTURE.name} is not the {REFERENCE_SIZE}-byte reference file")
    directory = tmp_path_factory.mktemp("reference_template")
    load_evtx(REFERENCE_FIXTURE, directory / "raw.jsonl")
    normalize_all(directory / "raw.jsonl", directory / "normalized.jsonl", 1)
    deduplicate(directory / "normalized.jsonl", directory / "deduplicated.jsonl")
    factory = open_workspace_database(directory / "workspace" / "raven.db")
    try:
        ingest_events(directory / "deduplicated.jsonl", None, factory)
        run_correlation(factory, None)
    finally:
        factory.kw["bind"].dispose()
    return directory / "workspace" / "raven.db"


@pytest.fixture(scope="module")
def reference_db(reference_template_db, tmp_path_factory):
    """A private copy of the template database for one test module."""
    directory = tmp_path_factory.mktemp("reference_copy")
    target = directory / "raven.db"
    shutil.copyfile(reference_template_db, target)
    return target
