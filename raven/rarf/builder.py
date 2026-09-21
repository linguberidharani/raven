"""Build the RARF document of an attack session from the database (spec section 6.10).

    build_rarf(session_factory, session_id) -> document (see schema.py)

Everything comes from rows that earlier stages stored: the attack session, its correlation groups and rules,
its timeline and its impact analysis. Nothing is detected, inferred or recalculated here. If the stages
have not all run for the session, or their results do not fit together, a RarfError says so.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from raven.database.models import AttackSession, CorrelatedEvent, CorrelationRule, Event, ImpactAnalysis, TimelineEvent
from raven.rarf.schema import IMPACT_CATEGORIES, RARF_VERSION
from raven.reconstruction.persist import load_groups
from raven.timeline.persist import TimelineError, session_groups

_CHUNK = 500


class RarfError(ValueError):
    """The RARF document cannot be built or is not valid."""


def _chunks(items: list[Any]) -> list[list[Any]]:
    return [items[start : start + _CHUNK] for start in range(0, len(items), _CHUNK)]


def list_session_ids(session_factory: sessionmaker[Session]) -> list[str]:
    with session_factory() as session:
        return list(session.scalars(select(AttackSession.session_id).order_by(AttackSession.id)))


def build_rarf(session_factory: sessionmaker[Session], session_id: str) -> dict[str, Any]:
    """The RARF document of one attack session."""
    with session_factory() as session:
        row = session.scalars(select(AttackSession).where(AttackSession.session_id == session_id)).one_or_none()
        if row is None:
            raise RarfError(f"attack session not found: {session_id}")
        try:
            members = session_groups(row.session_id, row.start_time, row.end_time, load_groups(session))
        except TimelineError as exc:
            raise RarfError(str(exc)) from exc
        members = sorted(members, key=lambda group: (group.start_ms, group.group_id))
        group_ids = [group.group_id for group in members]
        computer = members[0].computer

        # correlation groups and their events
        pairs: list[tuple[str, int]] = []
        for chunk in _chunks(group_ids):
            pairs.extend(
                session.execute(
                    select(CorrelatedEvent.correlation_group_id, CorrelatedEvent.event_id).where(
                        CorrelatedEvent.correlation_group_id.in_(chunk)
                    )
                ).all()
            )
        event_ids = sorted({event_id for _group, event_id in pairs})
        events: dict[int, Event] = {}
        for chunk in _chunks(event_ids):
            for event in session.scalars(select(Event).where(Event.id.in_(chunk))):
                events[event.id] = event
        by_group: dict[str, list[int]] = {group_id: [] for group_id in group_ids}
        for group_id, event_id in pairs:
            by_group[group_id].append(event_id)
        correlation_groups = [
            {
                "correlation_group_id": group.group_id,
                "correlation_type": group.rule_id,
                "event_ids": sorted(set(by_group[group.group_id]), key=lambda i: (events[i].timestamp, i)),
            }
            for group in members
        ]

        # rules used by these groups
        used = {group.rule_id for group in members}
        rules: list[dict[str, Any]] = []
        for rule_row in session.scalars(select(CorrelationRule).order_by(CorrelationRule.id)):
            definition = json.loads(rule_row.rule_definition)
            if definition["rule_id"] in used:
                rules.append(
                    {
                        "rule_database_id": rule_row.id,
                        "rule_id": definition["rule_id"],
                        "rule_name": rule_row.rule_name,
                        "description": rule_row.description,
                        "enabled": rule_row.enabled,
                        "rule_definition": definition,
                    }
                )

        # timeline
        timeline_rows = session.execute(
            select(TimelineEvent, Event).join(Event, Event.id == TimelineEvent.event_id)
            .where(TimelineEvent.attack_session_id == row.id)
            .order_by(TimelineEvent.sequence_number)
        ).all()
        if not timeline_rows:
            raise RarfError(f"session {session_id} has no timeline; run the timeline stage first")
        timeline_events = [
            {
                "timeline_event_id": entry.id,
                "event_id": entry.event_id,
                "sequence_number": entry.sequence_number,
                "timestamp": entry.timeline_timestamp,
                "raw_event_ref": event.raw_event_ref,
                "event_type": event.event_type,
                "computer": event.computer,
                "user": event.user,
            }
            for entry, event in timeline_rows
        ]

        # impact
        impact_rows = session.scalars(
            select(ImpactAnalysis).where(ImpactAnalysis.attack_session_id == row.id).order_by(ImpactAnalysis.id)
        ).all()
        by_category = {impact.impact_category: impact for impact in impact_rows}
        if set(by_category) != set(IMPACT_CATEGORIES):
            raise RarfError(f"session {session_id} has no complete impact analysis; run the impact stage first")
        categories = {
            name: {
                "impact_analysis_id": by_category[name].id,
                "impact_score": by_category[name].impact_score,
                "affected_assets": json.loads(by_category[name].affected_assets),
                "analysis": json.loads(by_category[name].analysis),
            }
            for name in IMPACT_CATEGORIES
        }

        document: dict[str, Any] = {
            "rarf_version": RARF_VERSION,
            "rarf_id": f"RARF-{row.session_id}",
            "attack_session": {
                "session_id": row.session_id,
                "computer": computer,
                "start_time": row.start_time,
                "end_time": row.end_time,
                "severity": row.severity,
                "confidence": row.confidence,
                "description": row.description,
            },
            "detection": {"correlation_groups": correlation_groups, "rules": rules, "event_ids": list(event_ids)},
            "timeline": {"events": timeline_events},
            "impact": {"categories": categories},
            "traceability": {
                "event_ids": list(event_ids),
                "raw_event_refs": [events[event_id].raw_event_ref for event_id in event_ids],
                "correlation_group_ids": list(group_ids),
                "timeline_event_ids": sorted(entry["timeline_event_id"] for entry in timeline_events),
                "impact_analysis_ids": sorted(category["impact_analysis_id"] for category in categories.values()),
            },
        }
    return document
