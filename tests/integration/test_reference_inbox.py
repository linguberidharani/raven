"""S14 acceptance on the reference data (spec sections 6.5b, 10.3 and 12): the reference records arrive through the
inbox in two pieces, as if a VM collector had sent them, and after the second piece the investigation shows the
reference numbers, without any manual analysis or rebuild. The RARF file is byte-identical to the one of stage S9.

The reference file is real telemetry and is never committed (*.evtx is ignored). Put it at
tests/fixtures/sysmon_export.evtx to run this test; without it the test is skipped.
Everything is written to temporary directories, never to the real data folder.
"""

import hashlib
import tempfile
from pathlib import Path

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from raven.api.main import create_app
from raven.collectors.evtx_loader import load_evtx
from tests.api.conftest import FAST_HASHER, make_investigation, make_settings, register_and_login

pytestmark = pytest.mark.slow

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sysmon_export.evtx"
REFERENCE_SIZE = 3_215_360
S9_RARF_SHA256 = "845724C83763D2B12B98247C64F67830DEF4BB0B9E3E8923C051B887E70B210B"
NAME = "sysmon-Dharani.jsonl"


@pytest.fixture(scope="module")
def live():
    if not FIXTURE.is_file():
        pytest.skip(f"reference file not present: {FIXTURE}")
    if FIXTURE.stat().st_size != REFERENCE_SIZE:
        pytest.skip(f"{FIXTURE.name} is not the {REFERENCE_SIZE}-byte reference file")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        raw = root / "raw.jsonl"
        load_evtx(FIXTURE, raw)
        lines = raw.read_text(encoding="utf-8").splitlines(keepends=True)
        assert len(lines) == 2816
        half = len(lines) // 2
        settings = make_settings(root)
        settings.resolved_inbox_dir.mkdir(parents=True, exist_ok=True)
        inbox_file = settings.resolved_inbox_dir / NAME
        app = create_app(settings, PasswordHasher(**FAST_HASHER))
        try:
            with TestClient(app) as client:
                register_and_login(client)
                investigation = make_investigation(client, "Live VM data", host="Dharani")
                base = f"/api/investigations/{investigation['id']}"
                inbox_file.write_text("".join(lines[:half]), encoding="utf-8", newline="")
                linked = client.post(base + "/collector", json={"source_name": NAME})
                assert linked.status_code == 201

                def poll_and_wait():
                    outcome = client.post("/api/inbox/poll").json()
                    for started in outcome["analyses_started"]:
                        assert started == investigation["id"]
                        run = client.get(base + "/analysis").json()
                        assert app.state.runs.wait(run["id"], 600), "the analysis run did not finish"
                    return outcome

                first = poll_and_wait()
                first_header = client.get(base).json()
                first_timeline = client.get(base + "/timeline").json()["total"]
                with open(inbox_file, "a", encoding="utf-8", newline="") as handle:
                    handle.write("".join(lines[half:]))
                second = poll_and_wait()
                third = poll_and_wait()
                workspace = settings.resolved_data_dir / "investigations" / str(investigation["id"])
                result = {
                    "half": half,
                    "linked": linked.json(),
                    "first": first,
                    "first_header": first_header,
                    "first_timeline": first_timeline,
                    "second": second,
                    "third": third,
                    "header": client.get(base).json(),
                    "sources": client.get(base + "/collector").json()["items"],
                    "run": client.get(base + "/analysis").json(),
                    "detections": client.get(base + "/detections", params={"page_size": 200}).json(),
                    "timeline": client.get(base + "/timeline", params={"page_size": 1}).json(),
                    "impact": client.get(base + "/impact").json(),
                    "rarf_bytes": next((workspace / "processed" / "rarf").glob("RARF-*.json")).read_bytes(),
                    "raw_bytes": (workspace / "raw" / f"evidence-{linked.json()['id']}.jsonl").read_bytes(),
                    "source_bytes": inbox_file.read_bytes(),
                    "original_raw": raw.read_bytes(),
                }
        finally:
            app.state.registry_factory.kw["bind"].dispose()
    return result


def test_the_first_piece_is_taken_over_and_analysed_by_itself(live):
    (result,) = live["first"]["results"]
    assert (result["records_added"], result["rejected"], result["error"]) == (live["half"], 0, None)
    assert live["first"]["analyses_started"] == [1]
    assert live["first_header"]["analysis_status"] == "completed" and live["first_header"]["counts"]["evidence"] == 1
    assert live["first_timeline"] < 597  # only part of the session is visible after the first piece


def test_the_second_piece_completes_the_investigation_without_a_manual_rebuild(live):
    (result,) = live["second"]["results"]
    assert (result["records_added"], result["rejected"]) == (2816 - live["half"], 0)
    assert live["second"]["analyses_started"] == [1]
    assert live["third"] == {"results": [{**live["third"]["results"][0], "records_added": 0}], "analyses_started": []}


def test_the_numbers_are_those_of_the_reference(live):
    header = live["header"]
    assert (header["severity"], header["analysis_status"]) == ("HIGH", "completed")
    assert header["counts"] == {"evidence": 1, "detections": 87, "sessions": 1, "timeline_events": 597}
    assert live["detections"]["counts"]["by_rule"] == {"RAVEN-R001": 19, "RAVEN-R002": 14, "RAVEN-R003": 54}
    assert live["timeline"]["total"] == 597
    (session,) = live["impact"]["sessions"]
    assert {c["category"]: c["derived"]["impact_score"] for c in session["categories"]} == {"files_affected": 475, "network_activity": 12, "process_activity": 14, "unsupported_events": 0}
    stages = {s["name"]: s["summary"] for s in live["run"]["stages"]}
    assert stages["collect"]["records"] == 2816 and stages["deduplicate"] == {"input": 2816, "unique": 2719, "removed": 97}


def test_the_cursor_and_the_evidence_source_follow_the_file(live):
    (source,) = live["sources"]
    assert (source["source_name"], source["events_total"], source["status"], source["error"]) == (NAME, 2816, "ready", None)
    assert source["last_offset"] == len(live["source_bytes"])
    assert live["linked"]["source_type"] == "vm_collector"


def test_the_raw_file_of_the_workspace_is_the_reference_raw_file(live):
    assert live["raw_bytes"] == live["original_raw"]
    assert hashlib.sha256(live["rarf_bytes"]).hexdigest().upper() == S9_RARF_SHA256
