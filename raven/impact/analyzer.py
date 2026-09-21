"""Impact analysis of an attack session (spec section 6.9). Pure code: no database, no files.

The events of a session's timeline are split into four categories:

    files_affected     file creation events;        assets = distinct file paths
    network_activity   network connection events;   assets = distinct "ip:port" destinations
    process_activity   process creation events;     assets = distinct process images
    unsupported_events events of unsupported types; assets = the Sysmon event IDs seen, as text

impact_score is the number of distinct affected assets. It is a DERIVED counted metric: it says how many
different files, destinations, images or event types the session's events touch. It says nothing about
harm, and no monetary or business impact is ever computed.

Every category is always reported, also with 0 events (score 0).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

CATEGORIES: tuple[str, ...] = ("files_affected", "network_activity", "process_activity", "unsupported_events")
CATEGORY_EVENT_TYPES: dict[str, str] = {
    "files_affected": "file_create",
    "network_activity": "network_connection",
    "process_activity": "process_creation",
    "unsupported_events": "unsupported",
}


@dataclass(frozen=True)
class ImpactResult:
    category: str
    impact_score: int
    affected_assets: tuple[str, ...]
    analysis: dict[str, Any]


def _distinct(values: list[Any]) -> list[Any]:
    return sorted({value for value in values if value is not None})


def _destination(event: dict[str, Any]) -> str | None:
    address = event.get("ip_address")
    if not address:
        return None
    port = event.get("port")
    return str(address) if port is None else f"{address}:{port}"


def _assets(category: str, events: list[dict[str, Any]]) -> list[str]:
    if category == "files_affected":
        return _distinct([event.get("file_path") for event in events])
    if category == "network_activity":
        return _distinct([_destination(event) for event in events])
    if category == "process_activity":
        return _distinct([event.get("process_name") for event in events])
    return _distinct([str(event["event_id"]) for event in events])


def _details(category: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    details: dict[str, Any] = {
        "distinct_computers": len(_distinct([event.get("computer") for event in events])),
        "distinct_users": len(_distinct([event.get("user") for event in events])),
    }
    if category in ("files_affected", "network_activity"):
        details["distinct_processes"] = len(_distinct([event.get("process_name") for event in events]))
    if category == "network_activity":
        details["protocols_seen"] = _distinct([event.get("protocol") for event in events])
    if category == "process_activity":
        details["distinct_parent_images"] = len(_distinct([event.get("parent_process_name") for event in events]))
    if category == "unsupported_events":
        details["event_ids_seen"] = _distinct([event["event_id"] for event in events])
    return details


def analyze_session(events: list[dict[str, Any]]) -> list[ImpactResult]:
    """The four impact results of one session.

    events: the session's timeline events in timeline order; each a mapping with the normalized field
    names plus "id" (database ID).
    """
    results: list[ImpactResult] = []
    for category in CATEGORIES:
        members = [event for event in events if event["event_type"] == CATEGORY_EVENT_TYPES[category]]
        assets = _assets(category, members)
        results.append(
            ImpactResult(
                category=category,
                impact_score=len(assets),
                affected_assets=tuple(assets),
                analysis={
                    "event_ids": [event["id"] for event in members],
                    "raw_event_refs": [event["raw_event_ref"] for event in members],
                    "event_count": len(members),
                    "details": _details(category, members),
                },
            )
        )
    return results
