"""Read layer of the API (spec section 8.2): answers built from what the pipeline stored in one workspace.

Every function reads the workspace database through a read-only connection and returns plain dictionaries. Nothing
here detects, infers or recalculates a finding: rules, groups, sessions, timeline rows and impact rows are read
as stored. What the pages call "derived" text (why a group matched, the interpretation of a group, the impact score
definition) is generated here in controlled wording and labelled with its basis, so the frontend only shows it.

A workspace that has not been analysed yet gives empty answers, not errors.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from raven.correlation.engine import timestamp_to_ms
from raven.database.models import AttackSession, CorrelatedEvent, CorrelationRule, Event, ImpactAnalysis, TimelineEvent
from raven.impact.analyzer import CATEGORIES
from raven.rarf.schema import IMPACT_CATEGORIES
from raven.reconstruction.persist import load_groups
from raven.reconstruction.sequencer import SEVERITY_ORDER
from raven.services.clock import iso
from raven.services.errors import ServiceError
from raven.services.workspace import Workspace
from raven.timeline.builder import describe_event
from raven.timeline.persist import session_groups

_TYPE_WORDS = {"process_creation": "process creation", "network_connection": "network connection", "file_create": "file creation"}
_MATCH_LABELS = {"process_id": "process ID", "process_guid": "process GUID"}
EVENT_COLUMNS = [column.name for column in Event.__table__.columns]


@contextmanager
def read_session(workspace: Workspace) -> Iterator[Session | None]:
    """A read-only session on the workspace database, or None when there is no database yet."""
    path = workspace.db_path
    if not path.is_file():
        yield None
        return
    uri = path.resolve().as_uri() + "?mode=ro"
    engine = create_engine("sqlite://", creator=lambda: sqlite3.connect(uri, uri=True))
    try:
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()


def _event_dict(event: Event) -> dict[str, Any]:
    return {name: getattr(event, name) for name in EVENT_COLUMNS}


def _chunks(items: list[Any], size: int = 500) -> Iterator[list[Any]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _events_by_id(session: Session, ids: list[int]) -> dict[int, Event]:
    found: dict[int, Event] = {}
    for chunk in _chunks(sorted(set(ids))):
        for event in session.scalars(select(Event).where(Event.id.in_(chunk))):
            found[event.id] = event
    return found


def group_match_value(group_id: str) -> str:
    parts = group_id.split(":", 2)
    return parts[1] if len(parts) == 3 else ""


# ---------------------------------------------------------------------------- rules and groups


def rule_definitions(session: Session) -> dict[str, dict[str, Any]]:
    """rule_id -> {"definition": ..., "enabled": ..., "database_id": ...} from the workspace database."""
    result: dict[str, dict[str, Any]] = {}
    for row in session.scalars(select(CorrelationRule).order_by(CorrelationRule.id)):
        definition = json.loads(row.rule_definition)
        result[definition["rule_id"]] = {"definition": definition, "enabled": row.enabled, "database_id": row.id}
    return result


def _steps_text(definition: dict[str, Any]) -> str:
    return ", then ".join(f"at least {step['min_count']} {_TYPE_WORDS[step['event_type']]} event(s)" for step in definition["steps"])


def _why(definition: dict[str, Any], match_value: str, counts: Counter[str], start: str, end: str) -> dict[str, Any]:
    label = _MATCH_LABELS.get(definition["match_key"], definition["match_key"])
    steps = [{"event_type": step["event_type"], "required": step["min_count"], "found": counts.get(step["event_type"], 0)} for step in definition["steps"]]
    found_parts = [str(item["found"]) + " " + _TYPE_WORDS[item["event_type"]] for item in steps]
    found_text = ", ".join(found_parts)
    text = (
        f"For {label} {match_value}, the recorded events satisfy rule {definition['rule_id']} ({definition['rule_name']}): "
        f"{_steps_text(definition)} within {definition['time_window_seconds']} seconds. "
        f"Found: {found_text} event(s) between {start} and {end} (UTC)."
    )
    return {"basis": "derived", "text": text, "steps": steps}


def _interpretation(definition: dict[str, Any]) -> dict[str, Any]:
    return {
        "basis": "derived",
        "text": (
            f"The recorded events match the pattern described by rule {definition['rule_id']} ({definition['rule_name']}). "
            "A matching pattern alone does not show the purpose of the activity."
        ),
    }


def collect_groups(session: Session) -> list[dict[str, Any]]:
    """Every correlation group with its rule, times, events and the text that explains the match, in time order."""
    rules = rule_definitions(session)
    rows = session.execute(
        select(CorrelatedEvent.correlation_group_id, CorrelatedEvent.correlation_type, Event.id, Event.raw_event_ref, Event.event_type, Event.timestamp)
        .join(Event, Event.id == CorrelatedEvent.event_id)
    ).all()
    collected: dict[str, dict[str, Any]] = {}
    for group_id, rule_id, event_id, ref, event_type, timestamp in rows:
        entry = collected.setdefault(group_id, {"rule_id": rule_id, "events": []})
        entry["events"].append((timestamp, event_id, ref, event_type))
    groups: list[dict[str, Any]] = []
    for group_id, entry in collected.items():
        info = rules.get(entry["rule_id"])
        if info is None:
            continue
        definition = info["definition"]
        events = sorted(entry["events"])
        start, end = events[0][0], events[-1][0]
        match_value = group_match_value(group_id)
        counts: Counter[str] = Counter(item[3] for item in events)
        groups.append(
            {
                "group_id": group_id,
                "rule_id": definition["rule_id"],
                "rule_name": definition["rule_name"],
                "severity": definition["severity"],
                "confidence": definition["confidence"],
                "match_key": definition["match_key"],
                "match_value": match_value,
                "time_window_seconds": definition["time_window_seconds"],
                "window_start": start,
                "window_end": end,
                "event_count": len(events),
                "why": _why(definition, match_value, counts, start, end),
                "interpretation": _interpretation(definition),
                "evidence": {"event_ids": [item[1] for item in events], "raw_event_refs": [item[2] for item in events]},
            }
        )
    groups.sort(key=lambda g: (g["window_start"], g["group_id"]))
    return groups


def detections(workspace: Workspace, *, rule_id: str | None, severity: str | None, page: int, page_size: int) -> dict[str, Any]:
    with read_session(workspace) as session:
        if session is None:
            return {"analysed": False, "rules": [], "counts": {"total_groups": 0, "by_rule": {}, "by_severity": {}}, "groups": [], "total": 0, "page": page, "page_size": page_size}
        rules = rule_definitions(session)
        groups = collect_groups(session)
    by_rule = Counter(g["rule_id"] for g in groups)
    by_severity = Counter(g["severity"] for g in groups)
    selected = [g for g in groups if (rule_id is None or g["rule_id"] == rule_id) and (severity is None or g["severity"] == severity)]
    return {
        "analysed": bool(rules),
        "rules": [
            {
                "rule_id": rid,
                "rule_name": info["definition"]["rule_name"],
                "description": info["definition"]["description"],
                "severity": info["definition"]["severity"],
                "confidence": info["definition"]["confidence"],
                "match_key": info["definition"]["match_key"],
                "time_window_seconds": info["definition"]["time_window_seconds"],
                "steps": info["definition"]["steps"],
                "enabled": info["enabled"],
                "groups": by_rule.get(rid, 0),
            }
            for rid, info in rules.items()
        ],
        "counts": {"total_groups": len(groups), "by_rule": dict(sorted(by_rule.items())), "by_severity": dict(sorted(by_severity.items()))},
        "groups": selected[(page - 1) * page_size : page * page_size],
        "total": len(selected),
        "page": page,
        "page_size": page_size,
    }


# ---------------------------------------------------------------------------- reconstruction


def _process_tree(events: list[dict[str, Any]], group_ids_by_event: dict[int, list[str]]) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    for event in sorted(events, key=lambda e: (e["timestamp"], e["id"])):
        guid = event["process_guid"]
        if not guid:
            continue
        node = nodes.setdefault(
            guid,
            {
                "process_guid": guid,
                "process_id": event["process_id"],
                "image": event["process_name"],
                "user": event["user"],
                "parent_process_guid": None,
                "parent_process_id": None,
                "parent_image": None,
                "first_seen": event["timestamp"],
                "last_seen": event["timestamp"],
                "event_counts": {},
                "group_ids": [],
                "in_session": True,
                "basis": "observed",
                "child_guids": [],
            },
        )
        node["last_seen"] = event["timestamp"]
        node["event_counts"][event["event_type"]] = node["event_counts"].get(event["event_type"], 0) + 1
        if event["event_type"] == "process_creation" and event["parent_process_guid"]:
            node["parent_process_guid"] = event["parent_process_guid"]
            node["parent_process_id"] = event["parent_process_id"]
            node["parent_image"] = event["parent_process_name"]
        for group_id in group_ids_by_event.get(event["id"], []):
            if group_id not in node["group_ids"]:
                node["group_ids"].append(group_id)
    for node in list(nodes.values()):
        parent = node["parent_process_guid"]
        if parent and parent not in nodes:
            nodes[parent] = {
                "process_guid": parent,
                "process_id": node["parent_process_id"],
                "image": node["parent_image"],
                "user": None,
                "parent_process_guid": None,
                "parent_process_id": None,
                "parent_image": None,
                "first_seen": None,
                "last_seen": None,
                "event_counts": {},
                "group_ids": [],
                "in_session": False,
                "basis": "observed",
                "child_guids": [],
            }
    for guid, node in nodes.items():
        parent = node["parent_process_guid"]
        if parent and parent in nodes:
            nodes[parent]["child_guids"].append(guid)
    ordered = sorted(nodes.values(), key=lambda n: (n["first_seen"] is None, n["first_seen"] or "", n["process_guid"]))
    roots = [n["process_guid"] for n in ordered if not n["parent_process_guid"] or n["parent_process_guid"] not in nodes]
    return {"nodes": ordered, "roots": roots}


def reconstruction(workspace: Workspace) -> dict[str, Any]:
    with read_session(workspace) as session:
        if session is None:
            return {"sessions": []}
        stored = session.execute(select(AttackSession).order_by(AttackSession.start_time, AttackSession.id)).scalars().all()
        infos = load_groups(session)
        by_id = {group["group_id"]: group for group in collect_groups(session)}
        sessions: list[dict[str, Any]] = []
        for row in stored:
            members = sorted(session_groups(row.session_id, row.start_time, row.end_time, infos), key=lambda g: (g.start_ms, g.group_id))
            group_ids = [g.group_id for g in members]
            event_ids = sorted({i for gid in group_ids for i in by_id[gid]["evidence"]["event_ids"]})
            events = {i: _event_dict(e) for i, e in _events_by_id(session, event_ids).items()}
            membership: dict[int, list[str]] = {}
            chain: list[dict[str, Any]] = []
            for gid in group_ids:
                group = by_id[gid]
                for event_id in group["evidence"]["event_ids"]:
                    membership.setdefault(event_id, []).append(gid)
                chain.append(
                    {
                        "group_id": gid,
                        "rule_id": group["rule_id"],
                        "rule_name": group["rule_name"],
                        "severity": group["severity"],
                        "match_value": group["match_value"],
                        "start_time": group["window_start"],
                        "end_time": group["window_end"],
                        "event_count": group["event_count"],
                        "events": [
                            {
                                "event_id": i,
                                "raw_event_ref": events[i]["raw_event_ref"],
                                "timestamp": events[i]["timestamp"],
                                "event_type": events[i]["event_type"],
                                "description": describe_event(events[i]),
                            }
                            for i in group["evidence"]["event_ids"]
                        ],
                        "interpretation": group["interpretation"],
                    }
                )
            sessions.append(
                {
                    "session_id": row.session_id,
                    "computer": members[0].computer if members else None,
                    "start_time": row.start_time,
                    "end_time": row.end_time,
                    "duration_ms": timestamp_to_ms(row.end_time) - timestamp_to_ms(row.start_time),
                    "severity": row.severity,
                    "confidence": row.confidence,
                    "description": row.description,
                    "group_count": len(chain),
                    "rule_ids": sorted({g["rule_id"] for g in chain}),
                    "chain": chain,
                    "process_tree": _process_tree(list(events.values()), membership),
                }
            )
    return {"sessions": sessions}


# ---------------------------------------------------------------------------- timeline and events


def timeline(
    workspace: Workspace,
    *,
    session_id: str | None,
    event_type: str | None,
    rule_id: str | None,
    q: str | None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    with read_session(workspace) as session:
        if session is None:
            return {"items": [], "total": 0, "page": page, "page_size": page_size}
        query = (
            select(TimelineEvent, Event, AttackSession.session_id, AttackSession.start_time)
            .join(Event, Event.id == TimelineEvent.event_id)
            .join(AttackSession, AttackSession.id == TimelineEvent.attack_session_id)
        )
        if session_id:
            query = query.where(AttackSession.session_id == session_id)
        if event_type:
            query = query.where(Event.event_type == event_type)
        if rule_id:
            query = query.where(
                Event.id.in_(select(CorrelatedEvent.event_id).where(CorrelatedEvent.correlation_type == rule_id))
            )
        if q and q.strip():
            pattern = "%" + q.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            query = query.where(func.lower(TimelineEvent.description).like(pattern, escape="\\"))
        total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = session.execute(
            query.order_by(AttackSession.start_time, AttackSession.id, TimelineEvent.sequence_number).offset((page - 1) * page_size).limit(page_size)
        ).all()
        ids = [event.id for _entry, event, _sid, _start in rows]
        membership: dict[int, list[dict[str, Any]]] = {}
        for chunk in _chunks(ids):
            for event_id, group_id, rule in session.execute(
                select(CorrelatedEvent.event_id, CorrelatedEvent.correlation_group_id, CorrelatedEvent.correlation_type).where(CorrelatedEvent.event_id.in_(chunk))
            ):
                membership.setdefault(event_id, []).append({"group_id": group_id, "rule_id": rule, "basis": "derived"})
        items = [
            {
                "timeline_event_id": entry.id,
                "session_id": sid,
                "sequence_number": entry.sequence_number,
                "timestamp": entry.timeline_timestamp,
                "description": entry.description,
                "computer": event.computer,
                "event_type": event.event_type,
                "event_id": event.id,
                "sysmon_event_id": event.event_id,
                "raw_event_ref": event.raw_event_ref,
                "basis": "observed",
                "groups": sorted(membership.get(event.id, []), key=lambda g: g["group_id"]),
            }
            for entry, event, sid, _start in rows
        ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def raw_record(path: Path, record_id: int) -> dict[str, Any] | None:
    """The raw record with this record ID from a raw JSONL file (one line each, fixed key order)."""
    if not path.is_file():
        return None
    needle = f'"record_id":{record_id}'
    with open(path, "r", encoding="utf-8", newline="\n") as handle:
        for line in handle:
            if needle in line:
                record = json.loads(line)
                if record.get("record_id") == record_id:
                    return record
    return None


def event_detail(workspace: Workspace, raw_event_ref: str) -> dict[str, Any]:
    evidence_id, _, record_text = raw_event_ref.partition(":")
    with read_session(workspace) as session:
        event = session.scalars(select(Event).where(Event.raw_event_ref == raw_event_ref)).one_or_none() if session else None
        if event is None:
            raise ServiceError(404, "event_not_found", "No stored event has this reference.")
        normalized = _event_dict(event)
        groups = [
            {"group_id": group_id, "rule_id": rule, "basis": "derived"}
            for group_id, rule in session.execute(
                select(CorrelatedEvent.correlation_group_id, CorrelatedEvent.correlation_type).where(CorrelatedEvent.event_id == event.id).order_by(CorrelatedEvent.correlation_group_id)
            )
        ]
        entry = session.execute(
            select(TimelineEvent.sequence_number, TimelineEvent.description, AttackSession.session_id)
            .join(AttackSession, AttackSession.id == TimelineEvent.attack_session_id)
            .where(TimelineEvent.event_id == event.id)
        ).first()
    raw = raw_record(workspace.raw_path(int(evidence_id)), int(record_text))
    if raw is None:
        raise ServiceError(404, "raw_record_not_found", "The raw record of this event is not available.")
    return {
        "raw_event_ref": raw_event_ref,
        "event": normalized,
        "raw": {"event_id": raw["event_id"], "time_created": raw["time_created"], "computer": raw["computer"], "record_id": raw["record_id"], "event_data": raw["event_data"]},
        "raw_xml": raw["raw_xml"],
        "groups": groups,
        "timeline": None if entry is None else {"session_id": entry.session_id, "sequence_number": entry.sequence_number, "description": entry.description},
    }


# ---------------------------------------------------------------------------- impact


def _bucket_seconds(span_seconds: float) -> int:
    for size in (10, 60, 600, 3600):
        if span_seconds / size <= 400:
            return size
    return 3600


def _asset(event: dict[str, Any], category: str) -> str | None:
    if category == "files_affected":
        return event["file_path"]
    if category == "network_activity":
        if not event["ip_address"]:
            return None
        return event["ip_address"] if event["port"] is None else f"{event['ip_address']}:{event['port']}"
    if category == "process_activity":
        return event["process_name"]
    return str(event["event_id"])


def impact(workspace: Workspace) -> dict[str, Any]:
    with read_session(workspace) as session:
        if session is None:
            return {"sessions": []}
        result: list[dict[str, Any]] = []
        for row in session.execute(select(AttackSession).order_by(AttackSession.start_time, AttackSession.id)).scalars():
            rows = {r.impact_category: r for r in session.scalars(select(ImpactAnalysis).where(ImpactAnalysis.attack_session_id == row.id))}
            if set(rows) != set(IMPACT_CATEGORIES):
                continue
            timeline_ids = list(session.scalars(select(TimelineEvent.event_id).where(TimelineEvent.attack_session_id == row.id)))
            events = {i: _event_dict(e) for i, e in _events_by_id(session, timeline_ids).items()}
            categories: list[dict[str, Any]] = []
            for name in CATEGORIES:
                stored = rows[name]
                analysis = json.loads(stored.analysis)
                assets = json.loads(stored.affected_assets)
                counts: Counter[str] = Counter()
                for event_id in analysis["event_ids"]:
                    asset = _asset(events[event_id], name)
                    if asset is not None:
                        counts[asset] += 1
                top = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:5]
                categories.append(
                    {
                        "category": name,
                        "impact_analysis_id": stored.id,
                        "observed": {
                            "basis": "observed",
                            "event_count": analysis["event_count"],
                            "affected_assets": assets,
                            "top_assets": [{"asset": asset, "events": number} for asset, number in top],
                            "details": analysis["details"],
                        },
                        "derived": {
                            "basis": "derived",
                            "impact_score": stored.impact_score,
                            "definition": "The number of distinct affected assets. A calculated count; it does not measure damage.",
                        },
                        "evidence": {"event_ids": analysis["event_ids"], "raw_event_refs": analysis["raw_event_refs"]},
                    }
                )
            stamps = sorted(timestamp_to_ms(e["timestamp"]) for e in events.values())
            buckets: list[dict[str, Any]] = []
            size = 10
            if stamps:
                size = _bucket_seconds((stamps[-1] - stamps[0]) / 1000)
                origin = stamps[0] - stamps[0] % (size * 1000)
                counts_by_bucket: dict[int, Counter[str]] = {}
                for event in events.values():
                    index = (timestamp_to_ms(event["timestamp"]) - origin) // (size * 1000)
                    counts_by_bucket.setdefault(index, Counter())[event["event_type"]] += 1
                for index in range(max(counts_by_bucket) + 1):
                    counter = counts_by_bucket.get(index, Counter())
                    epoch = (origin + index * size * 1000) / 1000
                    buckets.append(
                        {
                            "start": iso(datetime.fromtimestamp(epoch, tz=timezone.utc)),
                            "file_create": counter.get("file_create", 0),
                            "network_connection": counter.get("network_connection", 0),
                            "process_creation": counter.get("process_creation", 0),
                            "total": sum(counter.values()),
                        }
                    )
            result.append({"session_id": row.session_id, "categories": categories, "activity": {"basis": "derived", "bucket_seconds": size, "buckets": buckets}})
    return {"sessions": result}


# ---------------------------------------------------------------------------- RARF and report files


def session_ids(workspace: Workspace) -> list[str]:
    with read_session(workspace) as session:
        if session is None:
            return []
        return list(session.scalars(select(AttackSession.session_id).order_by(AttackSession.start_time, AttackSession.id)))


def artifact_path(folder: Path, prefix: str, session_id: str) -> Path | None:
    """The file of a session in a folder. The session ID is only compared with the names found; it never builds a path."""
    if not folder.is_dir():
        return None
    for path in sorted(folder.glob(f"{prefix}-*.json")):
        if path.name == f"{prefix}-{session_id}.json":
            return path
    return None


def workspace_overview(workspace: Workspace) -> dict[str, Any]:
    """Groups and sessions of a workspace, for the dashboard."""
    with read_session(workspace) as session:
        if session is None:
            return {"groups": [], "sessions": []}
        groups = collect_groups(session)
        sessions = [
            {"session_id": row.session_id, "start_time": row.start_time, "end_time": row.end_time, "severity": row.severity}
            for row in session.execute(select(AttackSession).order_by(AttackSession.start_time, AttackSession.id)).scalars()
        ]
    return {"groups": groups, "sessions": sessions}
