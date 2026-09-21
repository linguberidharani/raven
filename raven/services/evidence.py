"""Evidence files of an investigation: validated upload, listing and the event breakdown (spec sections 6.5, 8.2).

An upload is accepted only when
  - its name ends in .evtx (the name is kept for display only; it is never used as a file name or path),
  - it is not larger than RAVEN_MAX_UPLOAD_MB,
  - it starts with the EVTX file signature and is at least one header long,
  - the same content (SHA-256) is not already part of the investigation.
The file is stored as evidence/<evidence id>.evtx inside the workspace.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import uuid
from datetime import datetime
from typing import Any, BinaryIO

from sqlalchemy import select
from sqlalchemy.orm import Session

from raven.config import Settings
from raven.database.registry_models import EvidenceSource
from raven.services.clock import iso, utc_now
from raven.services.errors import ServiceError
from raven.services.investigations import get_investigation
from raven.services.workspace import Workspace, resolve_workspace

EVTX_SIGNATURE = b"ElfFile\x00"
MIN_EVTX_BYTES = 4096
_CHUNK = 1024 * 1024
_MAX_NAME = 255


def clean_filename(name: str | None) -> str:
    """The display name of an upload: the last path component, checked. Never used as a path."""
    base = (name or "").replace("\\", "/").split("/")[-1].strip()
    if not base or len(base) > _MAX_NAME or any(ord(character) < 32 for character in base):
        raise ServiceError(422, "invalid_filename", "The file name is not valid.")
    if not base.lower().endswith(".evtx"):
        raise ServiceError(422, "invalid_file_type", "Only .evtx files can be uploaded.")
    return base


def save_upload(
    registry: Session,
    settings: Settings,
    investigation_id: int,
    filename: str | None,
    source: BinaryIO,
    now: datetime | None = None,
) -> EvidenceSource:
    display_name = clean_filename(filename)
    investigation = get_investigation(registry, investigation_id)
    workspace = resolve_workspace(settings.resolved_data_dir, investigation.workspace_dir).ensure()
    part = workspace.evidence_dir / f"upload-{uuid.uuid4().hex}.part"

    digest = hashlib.sha256()
    size = 0
    head = b""
    try:
        with open(part, "wb") as handle:
            while True:
                block = source.read(_CHUNK)
                if not block:
                    break
                if len(head) < len(EVTX_SIGNATURE):
                    head = (head + block)[: len(EVTX_SIGNATURE)]
                size += len(block)
                if size > settings.max_upload_bytes:
                    raise ServiceError(413, "file_too_large", f"The file is larger than {settings.max_upload_mb} MB.")
                digest.update(block)
                handle.write(block)
        if size < MIN_EVTX_BYTES or head != EVTX_SIGNATURE:
            raise ServiceError(422, "invalid_evtx", "The file is not a Windows event log (EVTX) file.")
        sha256 = digest.hexdigest().upper()
        duplicate = registry.scalar(
            select(EvidenceSource.id).where(EvidenceSource.investigation_id == investigation_id, EvidenceSource.sha256 == sha256)
        )
        if duplicate is not None:
            raise ServiceError(409, "duplicate_evidence", "This file is already part of the investigation.")

        stamp = iso(now or utc_now())
        evidence = EvidenceSource(
            investigation_id=investigation_id,
            filename=display_name,
            sha256=sha256,
            size_bytes=size,
            source_type="evtx_upload",
            status="uploaded",
            events_total=0,
            created_at=stamp,
        )
        registry.add(evidence)
        registry.flush()
        try:
            os.replace(part, workspace.evidence_path(evidence.id))
        except OSError:
            registry.rollback()
            raise
        investigation.updated_at = stamp
        registry.commit()
        return evidence
    finally:
        if part.exists():
            part.unlink()


def list_evidence(registry: Session, investigation_id: int) -> list[EvidenceSource]:
    get_investigation(registry, investigation_id)
    return list(registry.scalars(select(EvidenceSource).where(EvidenceSource.investigation_id == investigation_id).order_by(EvidenceSource.id)))


def event_breakdown(workspace: Workspace) -> list[dict[str, Any]]:
    """Counts of the stored events by Sysmon event ID (unsupported IDs included), from the workspace database."""
    path = workspace.db_path
    if not path.is_file():
        return []
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "events" not in tables:
            return []
        rows = connection.execute("SELECT event_id, event_type, COUNT(*) FROM events GROUP BY event_id, event_type ORDER BY event_id").fetchall()
    finally:
        connection.close()
    return [{"event_id": event_id, "event_type": event_type, "count": count} for event_id, event_type, count in rows]
