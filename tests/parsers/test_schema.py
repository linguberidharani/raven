"""Unit tests for the normalized event schema. Synthetic values only."""

import pytest

from raven.parsers.schema import (
    NORMALIZED_FIELDS,
    STATUS_INVALID,
    STATUS_OK,
    STATUS_UNSUPPORTED,
    SUPPORTED_EVENT_TYPES,
    validate_normalized_event,
)


def make_event(**changes):
    event = {name: None for name in NORMALIZED_FIELDS}
    event.update(
        raw_event_ref="1:42",
        event_id=11,
        event_type="file_create",
        timestamp="2026-09-13T08:39:49.545Z",
        computer="SYNTHETIC-LAB-HOST",
        normalization_status=STATUS_OK,
        file_path="C:\\Test\\a.txt",
    )
    event.update(changes)
    return event


def test_there_are_27_fields_in_the_documented_order():
    assert len(NORMALIZED_FIELDS) == 27
    assert NORMALIZED_FIELDS[0] == "raw_event_ref"
    assert NORMALIZED_FIELDS[-1] == "normalization_status"
    assert NORMALIZED_FIELDS[7] == "process_name"
    assert len(set(NORMALIZED_FIELDS)) == 27


def test_supported_event_ids():
    assert SUPPORTED_EVENT_TYPES == {1: "process_creation", 3: "network_connection", 11: "file_create"}


def test_valid_event():
    assert validate_normalized_event(make_event()) == []


def test_valid_unsupported_event():
    event = make_event(event_id=5, event_type="unsupported", normalization_status=STATUS_UNSUPPORTED, file_path=None)
    assert validate_normalized_event(event) == []


def test_invalid_status_with_a_supported_type_is_valid():
    assert validate_normalized_event(make_event(normalization_status=STATUS_INVALID)) == []


def test_not_an_object():
    assert validate_normalized_event("x") == ["event is str, expected an object"]


@pytest.mark.parametrize("field", NORMALIZED_FIELDS)
def test_missing_field(field):
    event = make_event()
    del event[field]
    assert f"missing field: {field}" in validate_normalized_event(event)


def test_unexpected_field():
    assert "unexpected field: extra" in validate_normalized_event(make_event(extra=1))


@pytest.mark.parametrize(
    "changes, fragment",
    [
        ({"raw_event_ref": "42"}, "raw_event_ref must look like"),
        ({"raw_event_ref": "a:1"}, "raw_event_ref must look like"),
        ({"event_id": "11"}, "event_id must be an integer"),
        ({"event_id": True}, "event_id must be an integer"),
        ({"event_type": "other"}, "event_type must be one of"),
        ({"timestamp": "2026-09-13 08:39:49.545"}, "timestamp must look like"),
        ({"timestamp": "2026-09-13T08:39:49Z"}, "timestamp must look like"),
        ({"computer": ""}, "computer must be a non-empty string"),
        ({"normalization_status": "FINE"}, "normalization_status must be one of"),
        ({"process_id": "1"}, "process_id must be an integer or null"),
        ({"port": 1.5}, "port must be an integer or null"),
        ({"user": ""}, "user must be a non-empty string or null"),
        ({"file_path": 5}, "file_path must be a non-empty string or null"),
        ({"initiated": "true"}, "initiated must be true, false or null"),
        ({"event_type": "unsupported"}, "must go together"),
        ({"normalization_status": STATUS_UNSUPPORTED}, "must go together"),
        ({"event_id": 1}, "does not match event_id 1"),
        ({"event_id": 5, "event_type": "file_create"}, "does not match event_id 5"),
    ],
)
def test_wrong_values(changes, fragment):
    problems = validate_normalized_event(make_event(**changes))
    assert any(fragment in problem for problem in problems), problems
