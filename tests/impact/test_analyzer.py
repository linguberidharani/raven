"""Unit tests for the impact analyzer. Events are SYNTHETIC test data."""

from raven.impact.analyzer import CATEGORIES, CATEGORY_EVENT_TYPES, analyze_session
from raven.parsers.schema import NORMALIZED_FIELDS


def event(event_id_db, event_type, **fields):
    row = {name: None for name in NORMALIZED_FIELDS}
    row.update(
        id=event_id_db,
        raw_event_ref=f"1:{event_id_db}",
        event_id={"process_creation": 1, "network_connection": 3, "file_create": 11}.get(event_type, 5),
        event_type=event_type,
        timestamp="2026-09-13T08:39:49.545Z",
        computer="SYNTHETIC-LAB-HOST",
        normalization_status="OK",
    )
    row.update(fields)
    return row


def by_category(results):
    return {result.category: result for result in results}


def test_four_categories_are_always_reported_in_a_fixed_order():
    results = analyze_session([])
    assert [r.category for r in results] == list(CATEGORIES)
    assert CATEGORIES == ("files_affected", "network_activity", "process_activity", "unsupported_events")
    assert all(r.impact_score == 0 and r.affected_assets == () and r.analysis["event_count"] == 0 for r in results)
    assert set(CATEGORY_EVENT_TYPES.values()) == {"file_create", "network_connection", "process_creation", "unsupported"}


def test_files_affected_counts_distinct_paths():
    events = [
        event(1, "file_create", file_path="C:\\a.txt", process_name="C:\\p.exe", user="U1"),
        event(2, "file_create", file_path="C:\\b.txt", process_name="C:\\p.exe", user="U1"),
        event(3, "file_create", file_path="C:\\a.txt", process_name="C:\\q.exe", user="U2"),
    ]
    files = by_category(analyze_session(events))["files_affected"]
    assert files.impact_score == 2
    assert files.affected_assets == ("C:\\a.txt", "C:\\b.txt")
    assert files.analysis == {
        "event_ids": [1, 2, 3],
        "raw_event_refs": ["1:1", "1:2", "1:3"],
        "event_count": 3,
        "details": {"distinct_computers": 1, "distinct_users": 2, "distinct_processes": 2},
    }


def test_network_activity_counts_distinct_ip_port_destinations_and_lists_protocols():
    events = [
        event(1, "network_connection", ip_address="10.0.0.1", port=53, protocol="udp", process_name="C:\\a.exe"),
        event(2, "network_connection", ip_address="10.0.0.1", port=53, protocol="tcp", process_name="C:\\a.exe"),
        event(3, "network_connection", ip_address="10.0.0.1", port=443, protocol="tcp", process_name="C:\\b.exe"),
        event(4, "network_connection", ip_address="10.0.0.2", port=443, protocol="tcp", process_name="C:\\b.exe"),
    ]
    network = by_category(analyze_session(events))["network_activity"]
    assert network.impact_score == 3  # 10.0.0.1:53 counts once although seen with two protocols
    assert network.affected_assets == ("10.0.0.1:443", "10.0.0.1:53", "10.0.0.2:443")
    assert network.analysis["details"] == {"distinct_computers": 1, "distinct_users": 0, "distinct_processes": 2, "protocols_seen": ["tcp", "udp"]}
    assert network.analysis["event_count"] == 4


def test_a_destination_without_a_port_is_the_address_alone_and_one_without_an_address_is_skipped():
    events = [event(1, "network_connection", ip_address="10.0.0.9"), event(2, "network_connection")]
    network = by_category(analyze_session(events))["network_activity"]
    assert network.affected_assets == ("10.0.0.9",)
    assert network.analysis["event_count"] == 2


def test_process_activity_counts_distinct_images():
    events = [
        event(1, "process_creation", process_name="C:\\a.exe", parent_process_name="C:\\p.exe"),
        event(2, "process_creation", process_name="C:\\a.exe", parent_process_name="C:\\q.exe"),
        event(3, "process_creation", process_name="C:\\b.exe", parent_process_name="C:\\p.exe"),
    ]
    process = by_category(analyze_session(events))["process_activity"]
    assert process.impact_score == 2
    assert process.affected_assets == ("C:\\a.exe", "C:\\b.exe")
    assert process.analysis["details"] == {"distinct_computers": 1, "distinct_users": 0, "distinct_parent_images": 2}


def test_unsupported_events_are_counted_by_event_id():
    events = [event(1, "unsupported"), event(2, "unsupported"), event(3, "unsupported", event_id=16)]
    unsupported = by_category(analyze_session(events))["unsupported_events"]
    assert unsupported.impact_score == 2
    assert unsupported.affected_assets == ("16", "5")
    assert unsupported.analysis["details"]["event_ids_seen"] == [5, 16]
    assert unsupported.analysis["event_count"] == 3


def test_events_are_split_by_type_and_keep_the_timeline_order():
    events = [
        event(9, "process_creation", process_name="C:\\a.exe"),
        event(3, "file_create", file_path="C:\\z.txt"),
        event(7, "file_create", file_path="C:\\y.txt"),
    ]
    results = by_category(analyze_session(events))
    assert results["files_affected"].analysis["event_ids"] == [3, 7]
    assert results["process_activity"].analysis["event_ids"] == [9]
    assert results["network_activity"].analysis["event_count"] == 0
    assert results["files_affected"].affected_assets == ("C:\\y.txt", "C:\\z.txt")  # assets are sorted, events are not


def test_assets_that_differ_only_in_letter_case_are_different_assets():
    events = [event(1, "file_create", file_path="C:\\A.txt"), event(2, "file_create", file_path="C:\\a.txt")]
    assert by_category(analyze_session(events))["files_affected"].impact_score == 2


def test_events_without_the_asset_field_count_as_events_but_not_as_assets():
    events = [event(1, "file_create"), event(2, "file_create", file_path="C:\\a.txt")]
    files = by_category(analyze_session(events))["files_affected"]
    assert files.impact_score == 1 and files.analysis["event_count"] == 2


def test_the_result_does_not_change_between_runs():
    events = [event(i, "file_create", file_path=f"C:\\{i % 4}.txt", process_name="C:\\p.exe") for i in range(1, 20)]
    assert analyze_session(events) == analyze_session(list(events))


def test_details_count_distinct_users_and_computers():
    events = [
        event(1, "file_create", file_path="C:\\a", user="U1"),
        event(2, "file_create", file_path="C:\\b", user="U2", computer="OTHER"),
    ]
    details = by_category(analyze_session(events))["files_affected"].analysis["details"]
    assert details["distinct_users"] == 2 and details["distinct_computers"] == 2
