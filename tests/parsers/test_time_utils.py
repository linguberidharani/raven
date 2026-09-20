"""Unit tests for the timestamp helpers. Synthetic values only."""

from datetime import datetime, timedelta, timezone

import pytest

from raven.parsers.time_utils import TimeFormatError, format_iso_millis, parse_timestamp


def test_sysmon_utc_time_with_milliseconds():
    moment = parse_timestamp("2026-09-13 08:39:49.545", assume_utc=True)
    assert moment == datetime(2026, 9, 13, 8, 39, 49, 545000, tzinfo=timezone.utc)
    assert format_iso_millis(moment) == "2026-09-13T08:39:49.545Z"


def test_python_evtx_system_time_with_microseconds_and_zero_offset():
    moment = parse_timestamp("2026-09-12 18:04:54.529902+00:00")
    assert moment.microsecond == 529902
    assert format_iso_millis(moment) == "2026-09-12T18:04:54.529Z"


def test_digits_beyond_milliseconds_are_cut_off_not_rounded():
    assert format_iso_millis(parse_timestamp("2026-01-01 00:00:00.999999+00:00")) == "2026-01-01T00:00:00.999Z"
    assert format_iso_millis(parse_timestamp("2026-01-01 00:00:00.999999999", assume_utc=True)) == "2026-01-01T00:00:00.999Z"


def test_missing_fraction_gives_zero_milliseconds():
    assert format_iso_millis(parse_timestamp("2026-01-01 10:20:30", assume_utc=True)) == "2026-01-01T10:20:30.000Z"


def test_short_fractions_are_padded_on_the_right():
    assert format_iso_millis(parse_timestamp("2026-01-01 10:20:30.5", assume_utc=True)) == "2026-01-01T10:20:30.500Z"
    assert format_iso_millis(parse_timestamp("2026-01-01 10:20:30.05", assume_utc=True)) == "2026-01-01T10:20:30.050Z"


def test_offsets_are_converted_to_utc():
    assert format_iso_millis(parse_timestamp("2026-01-01 01:30:00.000+02:00")) == "2025-12-31T23:30:00.000Z"
    assert format_iso_millis(parse_timestamp("2026-01-01 01:30:00.000-0530")) == "2026-01-01T07:00:00.000Z"
    assert format_iso_millis(parse_timestamp("2026-01-01T01:30:00Z")) == "2026-01-01T01:30:00.000Z"


def test_a_time_without_zone_needs_assume_utc():
    with pytest.raises(TimeFormatError, match="no time zone"):
        parse_timestamp("2026-01-01 00:00:00.000")


@pytest.mark.parametrize(
    "text",
    ["", "yesterday", "2026-13-01 00:00:00.000", "2026-02-30 00:00:00.000", "2026-01-01 25:00:00.000", "2026-01-01 00:00:00.000+99:99"],
)
def test_bad_values_are_rejected(text):
    with pytest.raises(TimeFormatError):
        parse_timestamp(text, assume_utc=True)


def test_not_text_is_rejected():
    with pytest.raises(TimeFormatError):
        parse_timestamp(None)


def test_format_needs_an_aware_datetime():
    with pytest.raises(TimeFormatError):
        format_iso_millis(datetime(2026, 1, 1))


def test_format_converts_any_zone_to_utc():
    moment = datetime(2026, 1, 1, 1, 0, 0, 250000, tzinfo=timezone(timedelta(hours=1)))
    assert format_iso_millis(moment) == "2026-01-01T00:00:00.250Z"
