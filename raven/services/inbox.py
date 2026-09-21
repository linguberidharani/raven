"""The inbox: VM collector files, their links to investigations, and the watcher (spec sections 8.3 and 10.3, decision D4).

    The collector (in the VM) appends raw records to  <inbox>/<source name>.jsonl  in the shared folder.
    An analyst LINKS such a file to an investigation (a vm_collector evidence source plus a cursor).
    The watcher looks at the inbox every few seconds:
        - it reads only the complete lines after the saved offset (collectors.inbox.read_new_records),
        - it appends the new records to the raw file of the evidence source in the workspace,
        - it moves the cursor, and starts an incremental analysis run for the investigation.

Duplicate-safe: a record that is already in the raw file (same record ID and time) is not added again, so a collector
that starts over, or a crash between writing the records and saving the cursor, changes nothing.
Data waits in the inbox file while an analysis run of the investigation is active, so the run never reads a raw file
that is being extended.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from raven.collectors.inbox import InboxError, read_new_records, valid_source_name
from raven.collectors.raw_jsonl import serialize_record
from raven.config import Settings
from raven.database.registry_models import AnalysisRun, CollectorCursor, EvidenceSource, Investigation
from raven.services.analysis_runs import ACTIVE, AnalysisRunManager
from raven.services.clock import iso, utc_now
from raven.services.errors import ServiceError
from raven.services.investigations import get_investigation
from raven.services.workspace import resolve_workspace

logger = logging.getLogger("raven.inbox")

EMPTY_SHA256 = hashlib.sha256(b"").hexdigest().upper()
_READ_ERRORS = ("The inbox file", "The file is smaller", "A line is longer")


@dataclass(frozen=True)
class SourceResult:
    source_name: str
    investigation_id: int
    records_added: int
    rejected: int
    offset: int
    error: str | None
    skipped: str | None


@dataclass(frozen=True)
class PollResult:
    results: list[SourceResult] = field(default_factory=list)
    analyses_started: list[int] = field(default_factory=list)


def inbox_file(settings: Settings, source_name: str) -> Path:
    """The path of an inbox file. The name must be a plain .jsonl file name; the result must lie in the inbox folder."""
    if not valid_source_name(source_name):
        raise ServiceError(422, "invalid_source_name", "A source name is a plain file name ending in .jsonl (letters, digits, dot, underscore, dash).")
    base = settings.resolved_inbox_dir.resolve()
    path = (base / source_name).resolve()
    if path.parent != base:
        raise ServiceError(422, "invalid_source_name", "A source name is a plain file name ending in .jsonl (letters, digits, dot, underscore, dash).")
    return path


def list_inbox(registry: Session, settings: Settings) -> list[dict[str, Any]]:
    folder = settings.resolved_inbox_dir
    links = {
        cursor.source_name: (cursor.investigation_id, code)
        for cursor, code in registry.execute(select(CollectorCursor, Investigation.code).join(Investigation, Investigation.id == CollectorCursor.investigation_id))
    }
    items: list[dict[str, Any]] = []
    if folder.is_dir():
        for path in sorted(folder.iterdir()):
            if path.is_file() and valid_source_name(path.name):
                info = path.stat()
                linked = links.get(path.name)
                items.append(
                    {
                        "source_name": path.name,
                        "size_bytes": info.st_size,
                        "modified_at": iso(datetime.fromtimestamp(info.st_mtime, tz=timezone.utc)),
                        "investigation_id": linked[0] if linked else None,
                        "investigation_code": linked[1] if linked else None,
                    }
                )
    return items


def link_source(registry: Session, settings: Settings, investigation_id: int, source_name: str, now: datetime | None = None) -> EvidenceSource:
    """Link an inbox file to an investigation: a vm_collector evidence source and a cursor at the start of the file."""
    investigation = get_investigation(registry, investigation_id)
    path = inbox_file(settings, source_name)
    if not path.is_file():
        raise ServiceError(404, "inbox_file_not_found", "There is no such file in the inbox.")
    if registry.scalar(select(CollectorCursor.id).where(CollectorCursor.source_name == source_name)) is not None:
        raise ServiceError(409, "source_already_linked", "This inbox file is already linked to an investigation.")
    stamp = iso(now or utc_now())
    evidence = EvidenceSource(
        investigation_id=investigation_id,
        filename=source_name,
        sha256=EMPTY_SHA256,
        size_bytes=0,
        source_type="vm_collector",
        status="uploaded",
        events_total=0,
        created_at=stamp,
    )
    registry.add(evidence)
    registry.add(CollectorCursor(investigation_id=investigation_id, source_name=source_name, last_offset=0, last_record_id=None, updated_at=stamp))
    investigation.updated_at = stamp
    registry.commit()
    resolve_workspace(settings.resolved_data_dir, investigation.workspace_dir).ensure()
    return evidence


def collector_sources(registry: Session, investigation_id: int) -> list[dict[str, Any]]:
    get_investigation(registry, investigation_id)
    rows = registry.execute(
        select(CollectorCursor, EvidenceSource)
        .join(EvidenceSource, (EvidenceSource.investigation_id == CollectorCursor.investigation_id) & (EvidenceSource.filename == CollectorCursor.source_name) & (EvidenceSource.source_type == "vm_collector"))
        .where(CollectorCursor.investigation_id == investigation_id)
        .order_by(CollectorCursor.id)
    ).all()
    return [
        {
            "source_name": cursor.source_name,
            "evidence_id": evidence.id,
            "last_offset": cursor.last_offset,
            "last_record_id": cursor.last_record_id,
            "updated_at": cursor.updated_at,
            "status": evidence.status,
            "events_total": evidence.events_total,
            "error": evidence.error,
        }
        for cursor, evidence in rows
    ]


def _raw_keys(raw_path: Path) -> set[tuple[int, str]]:
    keys: set[tuple[int, str]] = set()
    if raw_path.is_file():
        with open(raw_path, "r", encoding="utf-8", newline="\n") as handle:
            for line in handle:
                if line.strip():
                    record = json.loads(line)
                    keys.add((record["record_id"], record["time_created"]))
    return keys


def _hash_prefix(path: Path, length: int) -> str:
    digest = hashlib.sha256()
    remaining = length
    with open(path, "rb") as handle:
        while remaining > 0:
            block = handle.read(min(1024 * 1024, remaining))
            if not block:
                break
            digest.update(block)
            remaining -= len(block)
    return digest.hexdigest().upper()


class InboxWatcher:
    def __init__(self, registry_factory: sessionmaker[Session], settings: Settings, runs: AnalysisRunManager) -> None:
        self._factory = registry_factory
        self._settings = settings
        self._runs = runs
        self._poll_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------ thread

    def start(self) -> None:
        interval = self._settings.inbox_poll_seconds
        if interval <= 0 or self._thread is not None:
            return
        self._settings.resolved_inbox_dir.mkdir(parents=True, exist_ok=True)
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, args=(interval,), name="raven-inbox-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
            self._thread = None

    def _loop(self, interval: float) -> None:
        while not self._stop.wait(interval):
            try:
                self.poll_once()
            except Exception:  # noqa: BLE001 - the watcher must keep running
                logger.exception("the inbox watcher could not finish a look at the inbox")

    # ------------------------------------------------------------------ one look at the inbox

    def poll_once(self) -> PollResult:
        with self._poll_lock:
            with self._factory() as registry:
                cursor_ids = list(registry.scalars(select(CollectorCursor.id).order_by(CollectorCursor.id)))
            results = [self._poll_cursor(cursor_id) for cursor_id in cursor_ids]
            return PollResult(results, self._start_pending_runs())

    def _poll_cursor(self, cursor_id: int) -> SourceResult:
        with self._factory() as registry:
            cursor = registry.get(CollectorCursor, cursor_id)
            name, investigation_id = cursor.source_name, cursor.investigation_id

            def result(added: int = 0, rejected: int = 0, error: str | None = None, skipped: str | None = None) -> SourceResult:
                return SourceResult(name, investigation_id, added, rejected, cursor.last_offset, error, skipped)

            evidence = registry.scalars(
                select(EvidenceSource).where(
                    EvidenceSource.investigation_id == investigation_id,
                    EvidenceSource.filename == name,
                    EvidenceSource.source_type == "vm_collector",
                )
            ).one()
            active = registry.scalar(select(AnalysisRun.id).where(AnalysisRun.investigation_id == investigation_id, AnalysisRun.status.in_(ACTIVE)))
            if active is not None:
                return result(skipped="an analysis run is active; the data waits in the inbox")
            investigation = registry.get(Investigation, investigation_id)
            workspace = resolve_workspace(self._settings.resolved_data_dir, investigation.workspace_dir)
            path = inbox_file(self._settings, name)
            if not path.is_file():
                evidence.error = "The inbox file is missing."
                registry.commit()
                return result(error=evidence.error)
            try:
                read = read_new_records(path, cursor.last_offset)
            except InboxError as exc:
                message = str(exc)
                evidence.error = (message[0].upper() + message[1:])[:500]
                if not evidence.error.startswith(_READ_ERRORS):
                    evidence.error = "The inbox file cannot be read: " + evidence.error
                registry.commit()
                return result(error=evidence.error)

            raw_path = workspace.raw_path(evidence.id)
            accepted = self._new_records(raw_path, read.records, cursor.last_record_id)
            if accepted:
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                data = "".join(serialize_record(record) + "\n" for record in accepted).encode("utf-8")
                with open(raw_path, "ab") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())

            moved = read.new_offset != cursor.last_offset
            stamp = iso(utc_now())
            if read.records:
                cursor.last_record_id = max(cursor.last_record_id or 0, max(record["record_id"] for record in read.records))
            cursor.last_offset = read.new_offset
            if moved:
                cursor.updated_at = stamp
                evidence.size_bytes = read.new_offset
                evidence.sha256 = _hash_prefix(path, read.new_offset)
            if accepted:
                evidence.events_total += len(accepted)
                evidence.status = "uploaded"
                investigation.updated_at = stamp
            if read.rejected_count:
                evidence.error = f"{read.rejected_count} invalid line(s) were skipped; first: {read.rejected[0]}"[:500]
            elif evidence.error and evidence.error.startswith(_READ_ERRORS + ("The inbox file cannot",)):
                evidence.error = None
            registry.commit()
            return result(added=len(accepted), rejected=read.rejected_count)

    @staticmethod
    def _new_records(raw_path: Path, records: list[dict[str, Any]], last_record_id: int | None) -> list[dict[str, Any]]:
        """The records that are not in the raw file yet (record ID and time decide)."""
        seen: set[tuple[int, str]] = set()
        known: set[tuple[int, str]] | None = None
        fresh: list[dict[str, Any]] = []
        for record in records:
            key = (record["record_id"], record["time_created"])
            if key in seen:
                continue
            seen.add(key)
            if last_record_id is not None and record["record_id"] <= last_record_id:
                if known is None:
                    known = _raw_keys(raw_path)
                if key in known:
                    continue
            fresh.append(record)
        return fresh

    def _start_pending_runs(self) -> list[int]:
        """Start an analysis run for every investigation whose collector data is not analysed yet."""
        with self._factory() as registry:
            candidates = list(
                registry.scalars(
                    select(EvidenceSource.investigation_id)
                    .where(EvidenceSource.source_type == "vm_collector", EvidenceSource.status == "uploaded", EvidenceSource.events_total > 0)
                    .distinct()
                    .order_by(EvidenceSource.investigation_id)
                )
            )
            wanted: list[int] = []
            for investigation_id in candidates:
                latest = registry.scalars(
                    select(AnalysisRun).where(AnalysisRun.investigation_id == investigation_id).order_by(AnalysisRun.id.desc()).limit(1)
                ).first()
                if latest is not None and latest.status in ACTIVE:
                    continue
                if latest is not None and latest.status == "failed":
                    newest = max(
                        registry.scalars(select(CollectorCursor.updated_at).where(CollectorCursor.investigation_id == investigation_id)),
                        default="",
                    )
                    if latest.finished_at is not None and newest <= latest.finished_at:
                        continue  # the last run failed and there is no new data since: do not retry in a loop
                wanted.append(investigation_id)
        started: list[int] = []
        for investigation_id in wanted:
            try:
                self._runs.start(investigation_id)
                started.append(investigation_id)
            except ServiceError as exc:
                if exc.code not in ("analysis_already_running", "no_evidence"):
                    raise
        return started
