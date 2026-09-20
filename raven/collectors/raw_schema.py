"""Raw record schema (spec section 6.1).

A raw record is one Sysmon event as it was read from the EVTX file, before any
normalization. Raw records are stored one JSON object per line.

Fields, always in this order:

    event_id      int   Sysmon event ID (System/EventID)
    time_created  str   System/TimeCreated SystemTime, exactly as recorded in the XML
    computer      str   System/Computer
    record_id     int   System/EventRecordID
    event_data    dict  EventData/Data items as Name -> text. Items without a Name go
                        to the list under the key "_unnamed" (Sysmon events have none)
    raw_xml       str   XML of the whole event as rendered by python-evtx, always kept
                        for traceability
"""

from __future__ import annotations

from typing import Any

RAW_FIELDS: tuple[str, ...] = (
    "event_id",
    "time_created",
    "computer",
    "record_id",
    "event_data",
    "raw_xml",
)

UNNAMED_KEY = "_unnamed"


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _event_data_problems(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["event_data must be an object"]
    problems: list[str] = []
    for key, item in value.items():
        if not isinstance(key, str) or not key:
            problems.append("event_data keys must be non-empty strings")
        elif key == UNNAMED_KEY:
            if not (isinstance(item, list) and all(isinstance(entry, str) for entry in item)):
                problems.append(f"event_data.{UNNAMED_KEY} must be a list of strings")
        elif not isinstance(item, str):
            problems.append(f"event_data.{key} must be a string")
    return problems


def validate_raw_record(record: Any) -> list[str]:
    """Return the problems found in a raw record. An empty list means it is valid."""
    if not isinstance(record, dict):
        return [f"record is {type(record).__name__}, expected an object"]

    problems: list[str] = []
    for name in RAW_FIELDS:
        if name not in record:
            problems.append(f"missing field: {name}")
    for name in record:
        if name not in RAW_FIELDS:
            problems.append(f"unexpected field: {name}")

    for name in ("event_id", "record_id"):
        if name in record and not _is_int(record[name]):
            problems.append(f"{name} must be an integer")
    for name in ("time_created", "computer", "raw_xml"):
        if name in record and (not isinstance(record[name], str) or not record[name]):
            problems.append(f"{name} must be a non-empty string")
    if "event_data" in record:
        problems.extend(_event_data_problems(record["event_data"]))
    return problems
