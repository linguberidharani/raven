"""Investigations: create, list, read and update (spec sections 6.5 and 8.2).

Every investigation has a code INV-YYYY-NNN (the number counts within the year), a status (open, active,
closed), the analyst who created it, and a workspace folder. All signed-in analysts can see all investigations
(shared case work); the creating analyst is recorded.

Severity and stage are DERIVED, never stored: the severity is the highest severity among the attack sessions
of the workspace (none until an analysis has run); the stage comes from the latest analysis run.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from raven.config import Settings
from raven.database.registry_models import AnalysisRun, EvidenceSource, Investigation, User
from raven.reconstruction.sequencer import SEVERITY_ORDER
from raven.services.clock import iso, utc_now
from raven.services.errors import ServiceError
from raven.services.workspace import Workspace, resolve_workspace, workspace_dir_name

STATUSES = ("open", "active", "closed")
_CODE = re.compile(r"^INV-(\d{4})-(\d{3,})$")


def validate_title(title: str) -> str:
    cleaned = title.strip()
    if not 1 <= len(cleaned) <= 200:
        raise ValueError("title must have 1 to 200 characters")
    return cleaned


def validate_description(description: str | None) -> str | None:
    if description is None:
        return None
    cleaned = description.strip()
    if len(cleaned) > 5000:
        raise ValueError("description must have at most 5000 characters")
    return cleaned or None


def validate_host(host: str | None) -> str | None:
    if host is None:
        return None
    cleaned = host.strip()
    if len(cleaned) > 100:
        raise ValueError("host must have at most 100 characters")
    return cleaned or None


def validate_status(status: str) -> str:
    if status not in STATUSES:
        raise ValueError("status must be one of " + ", ".join(STATUSES))
    return status


def _next_code(registry: Session, year: int) -> str:
    prefix = f"INV-{year}-"
    highest = 0
    for (code,) in registry.execute(select(Investigation.code).where(Investigation.code.like(prefix + "%"))):
        match = _CODE.match(code)
        if match:
            highest = max(highest, int(match.group(2)))
    return f"{prefix}{highest + 1:03d}"


def create_investigation(
    registry: Session,
    settings: Settings,
    *,
    analyst_id: int,
    title: str,
    description: str | None = None,
    host: str | None = None,
    now: datetime | None = None,
) -> Investigation:
    moment = now or utc_now()
    stamp = iso(moment)
    for _attempt in range(5):
        investigation = Investigation(
            code=_next_code(registry, moment.year),
            title=validate_title(title),
            description=validate_description(description),
            host=validate_host(host),
            status="open",
            analyst_id=analyst_id,
            created_at=stamp,
            updated_at=stamp,
            workspace_dir="pending",
        )
        registry.add(investigation)
        try:
            registry.flush()
        except IntegrityError:
            registry.rollback()
            continue
        investigation.workspace_dir = workspace_dir_name(investigation.id)
        registry.commit()
        resolve_workspace(settings.resolved_data_dir, investigation.workspace_dir).ensure()
        return investigation
    raise ServiceError(500, "code_conflict", "Could not allocate an investigation code.")


def get_investigation(registry: Session, investigation_id: int) -> Investigation:
    investigation = registry.get(Investigation, investigation_id)
    if investigation is None:
        raise ServiceError(404, "investigation_not_found", "Investigation not found.")
    return investigation


def list_investigations(
    registry: Session, *, status: str | None = None, q: str | None = None, page: int = 1, page_size: int = 100
) -> tuple[list[Investigation], int]:
    query = select(Investigation)
    if status:
        query = query.where(Investigation.status == status)
    if q and q.strip():
        pattern = "%" + q.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        query = query.where(
            func.lower(Investigation.code).like(pattern, escape="\\")
            | func.lower(Investigation.title).like(pattern, escape="\\")
            | func.lower(func.coalesce(Investigation.description, "")).like(pattern, escape="\\")
        )
    total = registry.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = registry.scalars(query.order_by(Investigation.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return list(rows), total


def update_investigation(registry: Session, investigation_id: int, changes: dict[str, Any], now: datetime | None = None) -> Investigation:
    investigation = get_investigation(registry, investigation_id)
    if "title" in changes:
        investigation.title = validate_title(changes["title"])
    if "description" in changes:
        investigation.description = validate_description(changes["description"])
    if "host" in changes:
        investigation.host = validate_host(changes["host"])
    if "status" in changes:
        investigation.status = validate_status(changes["status"])
    investigation.updated_at = iso(now or utc_now())
    registry.commit()
    return investigation


# ---------------------------------------------------------------------------- derived values


@dataclass(frozen=True)
class WorkspaceFacts:
    severity: str | None
    detections: int
    sessions: int
    timeline_events: int


def workspace_facts(workspace: Workspace) -> WorkspaceFacts:
    """Read-only counts from the workspace database; zeros and no severity when nothing has been analysed."""
    path: Path = workspace.db_path
    if not path.is_file():
        return WorkspaceFacts(None, 0, 0, 0)
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"correlated_events", "attack_sessions", "timeline_events"} <= tables:
            return WorkspaceFacts(None, 0, 0, 0)
        detections = connection.execute("SELECT COUNT(DISTINCT correlation_group_id) FROM correlated_events").fetchone()[0]
        sessions = connection.execute("SELECT COUNT(*) FROM attack_sessions").fetchone()[0]
        timeline = connection.execute("SELECT COUNT(*) FROM timeline_events").fetchone()[0]
        severities = [row[0] for row in connection.execute("SELECT DISTINCT severity FROM attack_sessions") if row[0] in SEVERITY_ORDER]
    finally:
        connection.close()
    severity = max(severities, key=SEVERITY_ORDER.index) if severities else None
    return WorkspaceFacts(severity, detections, sessions, timeline)


def latest_run(registry: Session, investigation_id: int) -> AnalysisRun | None:
    return registry.scalars(
        select(AnalysisRun).where(AnalysisRun.investigation_id == investigation_id).order_by(AnalysisRun.id.desc()).limit(1)
    ).first()


def evidence_count(registry: Session, investigation_id: int) -> int:
    return registry.scalar(select(func.count()).select_from(EvidenceSource).where(EvidenceSource.investigation_id == investigation_id)) or 0


def investigation_view(registry: Session, settings: Settings, row: Investigation) -> dict[str, Any]:
    """The investigation as the API shows it: stored fields plus the derived severity, stage and counts."""
    workspace = resolve_workspace(settings.resolved_data_dir, row.workspace_dir)
    facts = workspace_facts(workspace)
    run = latest_run(registry, row.id)
    analyst = registry.get(User, row.analyst_id)
    return {
        "id": row.id,
        "code": row.code,
        "title": row.title,
        "description": row.description,
        "host": row.host,
        "status": row.status,
        "severity": facts.severity,
        "stage": run.stage if run else None,
        "analysis_status": run.status if run else None,
        "analyst": {"id": analyst.id, "name": analyst.name},
        "counts": {
            "evidence": evidence_count(registry, row.id),
            "detections": facts.detections,
            "sessions": facts.sessions,
            "timeline_events": facts.timeline_events,
        },
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }
