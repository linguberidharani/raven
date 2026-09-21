"""Unit tests for the report evidence extractor. The RARF comes from a small synthetic workspace."""

from raven.report.evidence import ReportSource, format_duration, group_match_value


def test_format_duration():
    assert format_duration(0) == "0.000 s"
    assert format_duration(999) == "0.999 s"
    assert format_duration(59_999) == "59.999 s"
    assert format_duration(199_943) == "3 min 19.943 s"
    assert format_duration(3_723_004) == "1 h 2 min 3.004 s"


def test_group_match_value():
    assert group_match_value("RAVEN-R001:1224:2026-09-13T08:39:49.695Z") == "1224"
    assert group_match_value("RAVEN-R003:4:2026-09-13T08:39:49.545Z") == "4"
    assert group_match_value("broken") == ""


def test_counts_and_times(rarf):
    src = ReportSource(rarf)
    assert src.event_count == 11
    assert src.first_timestamp == "2026-09-13T08:00:00.000Z" and src.last_timestamp == "2026-09-13T08:00:10.000Z"
    assert src.duration_ms() == 10_000
    assert len(src.events_of_type("file_create")) == 10 and len(src.events_of_type("process_creation")) == 1
    assert src.events_per_minute() == [("2026-09-13T08:00", 11)]
    assert src.busiest_minute() == ("2026-09-13T08:00", 11)


def test_groups_and_rules(rarf):
    src = ReportSource(rarf)
    assert [g["correlation_type"] for g in src.ordered_groups()] == ["RAVEN-R001", "RAVEN-R003"]
    assert len(src.groups_of_rule("RAVEN-R001")) == 1 and src.groups_of_rule("RAVEN-R999") == []
    assert len(src.events_of_groups(src.groups)) == 11
    assert src.group_event_entries() == 6 + 10
    first_group = src.ordered_groups()[0]
    assert src.group_span(first_group) == ("2026-09-13T08:00:00.000Z", "2026-09-13T08:00:05.000Z")


def test_evidence_references_are_sorted_and_aligned(rarf):
    src = ReportSource(rarf)
    evidence = src.evidence({9, 3, 5}, ["g2", "g1", "g2"], [4, 2, 4])
    assert list(evidence) == ["event_ids", "correlation_group_ids", "timeline_event_ids", "impact_analysis_ids", "raw_event_refs"]
    assert evidence["event_ids"] == sorted(evidence["event_ids"])
    assert evidence["correlation_group_ids"] == ["g2", "g1"]
    assert evidence["impact_analysis_ids"] == [2, 4]
    assert evidence["raw_event_refs"] == [src.by_event[i]["raw_event_ref"] for i in evidence["event_ids"]]
    assert len(evidence["timeline_event_ids"]) == 3


def test_empty_evidence():
    # a source is needed only for the mapping; an empty request never touches it
    src = ReportSource.__new__(ReportSource)
    src.by_event = {}
    assert src.evidence() == {
        "event_ids": [],
        "correlation_group_ids": [],
        "timeline_event_ids": [],
        "impact_analysis_ids": [],
        "raw_event_refs": [],
    }
