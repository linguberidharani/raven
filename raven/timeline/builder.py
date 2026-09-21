"""Timeline (spec section 6.8). Pure code: no database, no files.

The timeline of an attack session holds every event of its correlation groups, each event once,
ordered by timestamp and then by the event's database ID, numbered from 1.

Every event gets a description generated from its normalized fields, in plain factual wording:

    process:  Process created: <image> (PID <pid>) by <user>; parent <parent image>
    file:     File created: <path> by <image> (PID <pid>)
    network:  Network connection: <image> to <ip>:<port>/<protocol>

Parts that are missing from the event are left out (never invented). A connection that was not
initiated by the process (Sysmon Initiated = false) is worded as incoming, because its destination
address is then the local one:

    Network connection (incoming): <image> on <ip>:<port>/<protocol> from <source ip>:<source port>

The descriptions state what was observed. They never say what it means.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TimelineEntry:
    sequence_number: int
    event_row_id: int
    timestamp: str
    description: str


def _endpoint(address: Any, port: Any) -> str | None:
    if not address:
        return None
    return str(address) if port is None else f"{address}:{port}"


def describe_event(event: dict[str, Any]) -> str:
    """The description of one event (a mapping with the normalized field names)."""
    event_type = event["event_type"]
    image = event.get("process_name") or "unknown image"
    pid = event.get("process_id")
    pid_text = f" (PID {pid})" if pid is not None else ""

    if event_type == "process_creation":
        text = f"Process created: {image}{pid_text}"
        if event.get("user"):
            text += f" by {event['user']}"
        if event.get("parent_process_name"):
            text += f"; parent {event['parent_process_name']}"
        return text

    if event_type == "file_create":
        return f"File created: {event.get('file_path') or 'unknown path'} by {image}{pid_text}"

    if event_type == "network_connection":
        target = _endpoint(event.get("ip_address"), event.get("port")) or "unknown address"
        if event.get("protocol"):
            target += f"/{event['protocol']}"
        if event.get("initiated") is False:
            text = f"Network connection (incoming): {image} on {target}"
            source = _endpoint(event.get("source_ip"), event.get("source_port"))
            return text + (f" from {source}" if source else "")
        return f"Network connection: {image} to {target}"

    return f"Sysmon event {event['event_id']} ({event_type}) recorded"


def build_timeline(events: list[dict[str, Any]]) -> list[TimelineEntry]:
    """Order events by timestamp, then database ID, and number them from 1. Each event appears once.

    Each event is a mapping with the normalized fields plus "id" (its database ID).
    """
    unique = {event["id"]: event for event in events}
    ordered = sorted(unique.values(), key=lambda event: (event["timestamp"], event["id"]))
    return [
        TimelineEntry(number, event["id"], event["timestamp"], describe_event(event))
        for number, event in enumerate(ordered, start=1)
    ]
