"""Unit tests for timeline descriptions and ordering. Events are SYNTHETIC test data."""

import pytest

from raven.timeline.builder import TimelineEntry, build_timeline, describe_event
from raven.parsers.schema import NORMALIZED_FIELDS


def event(event_type, **fields):
    row = {name: None for name in NORMALIZED_FIELDS}
    row.update(
        id=1,
        raw_event_ref="1:1",
        event_id={"process_creation": 1, "network_connection": 3, "file_create": 11}.get(event_type, 5),
        event_type=event_type,
        timestamp="2026-09-13T08:39:49.545Z",
        computer="SYNTHETIC-LAB-HOST",
        normalization_status="OK",
    )
    row.update(fields)
    return row


def test_process_description_with_user_and_parent():
    text = describe_event(
        event(
            "process_creation",
            process_name="C:\\Test\\synthetic.exe",
            process_id=1224,
            user="SYNTHETIC\\tester",
            parent_process_name="C:\\Test\\parent.exe",
        )
    )
    assert text == "Process created: C:\\Test\\synthetic.exe (PID 1224) by SYNTHETIC\\tester; parent C:\\Test\\parent.exe"


def test_process_description_leaves_out_what_is_missing():
    assert describe_event(event("process_creation", process_name="C:\\a.exe", process_id=5)) == "Process created: C:\\a.exe (PID 5)"
    assert describe_event(event("process_creation", process_name="C:\\a.exe", process_id=5, user="U")) == "Process created: C:\\a.exe (PID 5) by U"
    assert describe_event(event("process_creation", process_name="C:\\a.exe", process_id=5, parent_process_name="C:\\p.exe")) == (
        "Process created: C:\\a.exe (PID 5); parent C:\\p.exe"
    )


def test_file_description():
    text = describe_event(event("file_create", file_path="C:\\Test\\a.txt", process_name="C:\\Test\\synthetic.exe", process_id=1224))
    assert text == "File created: C:\\Test\\a.txt by C:\\Test\\synthetic.exe (PID 1224)"


def test_file_description_with_missing_parts():
    assert describe_event(event("file_create")) == "File created: unknown path by unknown image"


def test_network_description_for_an_outgoing_connection():
    text = describe_event(
        event("network_connection", process_name="C:\\Test\\synthetic.exe", ip_address="127.0.0.1", port=47001, protocol="tcp", initiated=True)
    )
    assert text == "Network connection: C:\\Test\\synthetic.exe to 127.0.0.1:47001/tcp"


def test_network_description_when_initiated_is_unknown_is_worded_as_outgoing():
    text = describe_event(event("network_connection", process_name="C:\\a.exe", ip_address="10.0.0.1", port=53, protocol="udp"))
    assert text == "Network connection: C:\\a.exe to 10.0.0.1:53/udp"


def test_network_description_for_an_incoming_connection():
    text = describe_event(
        event(
            "network_connection",
            process_name="C:\\a.exe",
            ip_address="10.0.2.15",
            port=445,
            protocol="tcp",
            initiated=False,
            source_ip="10.0.2.2",
            source_port=50000,
        )
    )
    assert text == "Network connection (incoming): C:\\a.exe on 10.0.2.15:445/tcp from 10.0.2.2:50000"


def test_network_description_with_missing_parts():
    assert describe_event(event("network_connection", process_name="C:\\a.exe")) == "Network connection: C:\\a.exe to unknown address"
    assert describe_event(event("network_connection", process_name="C:\\a.exe", ip_address="1.2.3.4")) == "Network connection: C:\\a.exe to 1.2.3.4"


def test_other_event_types_get_a_neutral_description():
    assert describe_event(event("unsupported")) == "Sysmon event 5 (unsupported) recorded"


@pytest.mark.parametrize("kind", ["process_creation", "file_create", "network_connection", "unsupported"])
def test_a_description_never_looks_like_a_placeholder(kind):
    text = describe_event(event(kind, process_name="C:\\a.exe", process_id=1))
    assert not text.startswith("Event ")
    assert text.strip() == text and text


def test_events_are_ordered_by_timestamp_then_database_id_and_numbered_from_one():
    events = [
        event("file_create", id=7, timestamp="2026-09-13T08:39:50.000Z", file_path="C:\\c", process_name="x"),
        event("file_create", id=3, timestamp="2026-09-13T08:39:49.000Z", file_path="C:\\a", process_name="x"),
        event("file_create", id=5, timestamp="2026-09-13T08:39:49.000Z", file_path="C:\\b", process_name="x"),
    ]
    entries = build_timeline(events)
    assert [(e.sequence_number, e.event_row_id) for e in entries] == [(1, 3), (2, 5), (3, 7)]
    assert entries[0] == TimelineEntry(1, 3, "2026-09-13T08:39:49.000Z", "File created: C:\\a by x")


def test_each_event_appears_once():
    e = event("file_create", id=4, file_path="C:\\a", process_name="x")
    assert [entry.event_row_id for entry in build_timeline([e, dict(e), e])] == [4]


def test_the_input_order_does_not_change_the_result():
    events = [event("file_create", id=i, timestamp=f"2026-09-13T08:39:{i:02d}.000Z", file_path=f"C:\\{i}", process_name="x") for i in range(1, 9)]
    assert build_timeline(events) == build_timeline(list(reversed(events)))


def test_no_events_no_entries():
    assert build_timeline([]) == []
