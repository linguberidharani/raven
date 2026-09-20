"""Timestamp helpers.

Two inputs are handled:
  - Sysmon UtcTime inside event_data, for example "2026-09-13 08:39:49.545". It carries no
    zone because Sysmon writes it in UTC (use assume_utc=True).
  - The TimeCreated SystemTime of the record as python-evtx renders it, for example
    "2026-09-12 18:04:54.529902+00:00". It carries its own offset.

The output format is ISO-8601 UTC with milliseconds and a trailing Z. Digits beyond the
millisecond are cut off (not rounded), so the same input always gives the same output.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

_PATTERN = re.compile(
    r"^([0-9]{4})-([0-9]{2})-([0-9]{2})[ T]([0-9]{2}):([0-9]{2}):([0-9]{2})"
    r"(?:\.([0-9]{1,9}))?\s*(Z|[+-][0-9]{2}:?[0-9]{2})?$"
)


class TimeFormatError(ValueError):
    """A timestamp text could not be understood."""


def parse_timestamp(text: str, *, assume_utc: bool = False) -> datetime:
    """Parse a timestamp text into a timezone-aware datetime in UTC (microsecond precision)."""
    if not isinstance(text, str):
        raise TimeFormatError(f"timestamp must be text, not {type(text).__name__}")
    match = _PATTERN.match(text.strip())
    if match is None:
        raise TimeFormatError(f"unrecognized timestamp: {text!r}")
    year, month, day, hour, minute, second, fraction, zone = match.groups()
    microsecond = int((fraction or "").ljust(6, "0")[:6])

    if zone is None and not assume_utc:
        raise TimeFormatError(f"timestamp has no time zone: {text!r}")
    try:
        if zone is None or zone == "Z":
            tzinfo = timezone.utc
        else:
            digits = zone[1:].replace(":", "")
            offset = timedelta(hours=int(digits[:2]), minutes=int(digits[2:]))
            tzinfo = timezone(offset if zone[0] == "+" else -offset)
        moment = datetime(
            int(year), int(month), int(day), int(hour), int(minute), int(second), microsecond, tzinfo=tzinfo
        )
    except ValueError as exc:
        raise TimeFormatError(f"invalid timestamp {text!r}: {exc}") from exc
    return moment.astimezone(timezone.utc)


def format_iso_millis(moment: datetime) -> str:
    """Format a datetime as 2026-09-13T08:39:49.545Z (UTC, milliseconds cut off, trailing Z)."""
    if moment.tzinfo is None:
        raise TimeFormatError("datetime must be timezone-aware")
    utc = moment.astimezone(timezone.utc)
    return (
        f"{utc.year:04d}-{utc.month:02d}-{utc.day:02d}T"
        f"{utc.hour:02d}:{utc.minute:02d}:{utc.second:02d}.{utc.microsecond // 1000:03d}Z"
    )
