"""S2 acceptance on the reference EVTX (spec sections 6.3, 6.5b and 12).

The reference file is real telemetry and is never committed (*.evtx is ignored). Put it at
tests/fixtures/sysmon_export.evtx to run this test; without it the test is skipped.
The output goes to a temporary directory, never to the real data folder.
"""

from pathlib import Path

import pytest

from raven.collectors.evtx_loader import load_evtx
from raven.collectors.raw_jsonl import read_raw_jsonl, sha256_file

pytestmark = pytest.mark.slow

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sysmon_export.evtx"
REFERENCE_SIZE = 3_215_360
REFERENCE_RAW_RECORDS = 2816


@pytest.fixture(scope="module")
def reference_evtx():
    if not FIXTURE.is_file():
        pytest.skip(f"reference file not present: {FIXTURE}")
    if FIXTURE.stat().st_size != REFERENCE_SIZE:
        pytest.skip(f"{FIXTURE.name} is not the {REFERENCE_SIZE}-byte reference file")
    return FIXTURE


@pytest.fixture(scope="module")
def loaded(reference_evtx, tmp_path_factory):
    directory = tmp_path_factory.mktemp("reference")
    first = directory / "first.jsonl"
    second = directory / "second.jsonl"
    count_first = load_evtx(reference_evtx, first)
    count_second = load_evtx(reference_evtx, second)
    return first, second, count_first, count_second


def test_reference_file_gives_the_reference_record_count(loaded):
    _, _, count_first, _ = loaded
    assert count_first == REFERENCE_RAW_RECORDS


def test_every_record_is_valid_and_carries_raw_xml(loaded):
    first, _, count_first, _ = loaded
    records = list(read_raw_jsonl(first))
    assert len(records) == count_first
    assert all(record["raw_xml"].lstrip().startswith("<Event") for record in records)


def test_record_ids_are_unique(loaded):
    first, _, count_first, _ = loaded
    assert len({record["record_id"] for record in read_raw_jsonl(first)}) == count_first


def test_loading_twice_gives_identical_output(loaded):
    first, second, count_first, count_second = loaded
    assert count_first == count_second
    assert sha256_file(first) == sha256_file(second)
