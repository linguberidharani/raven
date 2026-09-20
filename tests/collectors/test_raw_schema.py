"""Unit tests for the raw record schema. All data here is synthetic test data."""

import pytest

from raven.collectors.raw_schema import RAW_FIELDS, UNNAMED_KEY, validate_raw_record


def make_record(**changes):
    record = {
        "event_id": 1,
        "time_created": "2020-01-01 00:00:00.000000+00:00",
        "computer": "SYNTHETIC-LAB-HOST",
        "record_id": 7,
        "event_data": {"Image": "C:\\Test\\synthetic.exe"},
        "raw_xml": "<Event></Event>",
    }
    record.update(changes)
    return record


def test_fields_are_in_the_documented_order():
    assert RAW_FIELDS == ("event_id", "time_created", "computer", "record_id", "event_data", "raw_xml")


def test_valid_record_has_no_problems():
    assert validate_raw_record(make_record()) == []


def test_unnamed_list_is_allowed():
    record = make_record(event_data={UNNAMED_KEY: ["a", "b"], "Name": "x"})
    assert validate_raw_record(record) == []


def test_empty_event_data_is_allowed():
    assert validate_raw_record(make_record(event_data={})) == []


def test_not_an_object():
    assert validate_raw_record([1, 2]) == ["record is list, expected an object"]


@pytest.mark.parametrize("field", RAW_FIELDS)
def test_missing_field_is_reported(field):
    record = make_record()
    del record[field]
    assert f"missing field: {field}" in validate_raw_record(record)


def test_unexpected_field_is_reported():
    problems = validate_raw_record(make_record(extra="x"))
    assert "unexpected field: extra" in problems


@pytest.mark.parametrize(
    "changes, fragment",
    [
        ({"event_id": "1"}, "event_id must be an integer"),
        ({"event_id": True}, "event_id must be an integer"),
        ({"record_id": None}, "record_id must be an integer"),
        ({"record_id": 1.5}, "record_id must be an integer"),
        ({"time_created": ""}, "time_created must be a non-empty string"),
        ({"computer": None}, "computer must be a non-empty string"),
        ({"raw_xml": ""}, "raw_xml must be a non-empty string"),
        ({"event_data": []}, "event_data must be an object"),
        ({"event_data": {"A": 1}}, "event_data.A must be a string"),
        ({"event_data": {UNNAMED_KEY: "x"}}, f"event_data.{UNNAMED_KEY} must be a list of strings"),
        ({"event_data": {UNNAMED_KEY: [1]}}, f"event_data.{UNNAMED_KEY} must be a list of strings"),
    ],
)
def test_wrong_values_are_reported(changes, fragment):
    assert fragment in validate_raw_record(make_record(**changes))
