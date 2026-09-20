"""Normalized event schema (spec section 6.2): 27 fields, always in this order.

    raw_event_ref        "<evidence_id>:<record_id>", unique within an investigation
    event_id             Sysmon event ID
    event_type           process_creation | network_connection | file_create | unsupported
    timestamp            ISO-8601 UTC with milliseconds and a trailing Z
    computer             computer name
    process_guid ... file_path   see normalizer.py for the Sysmon field each one comes from
    normalization_status OK | UNSUPPORTED_EVENT_ID | INVALID_EVENT_DATA

A field that does not apply to the event type, or is absent from the event, is null.
Text fields are never empty strings: an empty value is stored as null.
"""

from __future__ import annotations

import re
from typing import Any

NORMALIZED_FIELDS: tuple[str, ...] = (
    "raw_event_ref",
    "event_id",
    "event_type",
    "timestamp",
    "computer",
    "process_guid",
    "process_id",
    "process_name",
    "parent_process_guid",
    "parent_process_id",
    "parent_process_name",
    "command_line",
    "parent_command_line",
    "user",
    "integrity_level",
    "hash_sha256",
    "hash_md5",
    "hash_imphash",
    "hashes_raw",
    "ip_address",
    "port",
    "source_ip",
    "source_port",
    "protocol",
    "initiated",
    "file_path",
    "normalization_status",
)

EVENT_TYPE_PROCESS = "process_creation"
EVENT_TYPE_NETWORK = "network_connection"
EVENT_TYPE_FILE = "file_create"
EVENT_TYPE_UNSUPPORTED = "unsupported"
EVENT_TYPES = (EVENT_TYPE_PROCESS, EVENT_TYPE_NETWORK, EVENT_TYPE_FILE, EVENT_TYPE_UNSUPPORTED)

# Sysmon event ID -> event type. Every other event ID is unsupported (and is kept).
SUPPORTED_EVENT_TYPES: dict[int, str] = {
    1: EVENT_TYPE_PROCESS,
    3: EVENT_TYPE_NETWORK,
    11: EVENT_TYPE_FILE,
}

STATUS_OK = "OK"
STATUS_UNSUPPORTED = "UNSUPPORTED_EVENT_ID"
STATUS_INVALID = "INVALID_EVENT_DATA"
STATUSES = (STATUS_OK, STATUS_UNSUPPORTED, STATUS_INVALID)

INTEGER_FIELDS = ("process_id", "parent_process_id", "port", "source_port")
TEXT_FIELDS = (
    "process_guid",
    "process_name",
    "parent_process_guid",
    "parent_process_name",
    "command_line",
    "parent_command_line",
    "user",
    "integrity_level",
    "hash_sha256",
    "hash_md5",
    "hash_imphash",
    "hashes_raw",
    "ip_address",
    "source_ip",
    "protocol",
    "file_path",
)

_REF_PATTERN = re.compile(r"^[0-9]+:[0-9]+$")
_TIMESTAMP_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z$")


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_normalized_event(event: Any) -> list[str]:
    """Return the problems found in a normalized event. An empty list means it is valid."""
    if not isinstance(event, dict):
        return [f"event is {type(event).__name__}, expected an object"]

    problems: list[str] = []
    for name in NORMALIZED_FIELDS:
        if name not in event:
            problems.append(f"missing field: {name}")
    for name in event:
        if name not in NORMALIZED_FIELDS:
            problems.append(f"unexpected field: {name}")
    if problems:
        return problems

    if not isinstance(event["raw_event_ref"], str) or not _REF_PATTERN.match(event["raw_event_ref"]):
        problems.append("raw_event_ref must look like <evidence_id>:<record_id>")
    if not _is_int(event["event_id"]):
        problems.append("event_id must be an integer")
    if event["event_type"] not in EVENT_TYPES:
        problems.append(f"event_type must be one of {', '.join(EVENT_TYPES)}")
    if not isinstance(event["timestamp"], str) or not _TIMESTAMP_PATTERN.match(event["timestamp"]):
        problems.append("timestamp must look like 2026-09-13T08:39:49.545Z")
    if not isinstance(event["computer"], str) or not event["computer"]:
        problems.append("computer must be a non-empty string")
    if event["normalization_status"] not in STATUSES:
        problems.append(f"normalization_status must be one of {', '.join(STATUSES)}")

    for name in INTEGER_FIELDS:
        if event[name] is not None and not _is_int(event[name]):
            problems.append(f"{name} must be an integer or null")
    for name in TEXT_FIELDS:
        if event[name] is not None and (not isinstance(event[name], str) or not event[name]):
            problems.append(f"{name} must be a non-empty string or null")
    if event["initiated"] is not None and not isinstance(event["initiated"], bool):
        problems.append("initiated must be true, false or null")

    unsupported_type = event["event_type"] == EVENT_TYPE_UNSUPPORTED
    unsupported_status = event["normalization_status"] == STATUS_UNSUPPORTED
    if unsupported_type != unsupported_status:
        problems.append("event_type unsupported and status UNSUPPORTED_EVENT_ID must go together")
    if _is_int(event["event_id"]):
        expected_type = SUPPORTED_EVENT_TYPES.get(event["event_id"], EVENT_TYPE_UNSUPPORTED)
        if event["event_type"] in EVENT_TYPES and event["event_type"] != expected_type:
            problems.append(f"event_type {event['event_type']} does not match event_id {event['event_id']}")
    return problems
