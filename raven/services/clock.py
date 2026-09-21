"""The current time in the format used across RAVEN: 2026-09-13T08:39:49.545Z (UTC, milliseconds)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from raven.parsers.time_utils import format_iso_millis


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(moment: datetime) -> str:
    return format_iso_millis(moment)


def utc_now_iso() -> str:
    return iso(utc_now())


def in_hours(hours: int, start: datetime | None = None) -> str:
    """The timestamp `hours` after `start` (default: now)."""
    return iso((start or utc_now()) + timedelta(hours=hours))
