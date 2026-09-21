"""Analysis runs: the pipeline in a background thread, one run per investigation at a time (spec 8.3, decision D4).

    manager = AnalysisRunManager(registry_factory, settings)
    run_id = manager.start(investigation_id)      # returns at once; the run continues in a worker thread
    run_view(run_row)                             # the run with per-stage status, for polling

A run row is queued, then running, then completed or failed. stages_json holds every stage with its status,
times, summary numbers and error, updated while the run goes on, so a client that polls sees real progress.
Evidence files are processing during a run and ready afterwards; the file that made a run fail is marked failed
with the error, the others go back to their earlier status. A run that was interrupted by a server restart is
marked failed the next time the server starts.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from raven.collectors.evtx_loader import load_evtx
from raven.config import Settings
from raven.database.registry_models import AnalysisRun, EvidenceSource, Investigation
from raven.services.clock import utc_now_iso
from raven.services.errors import ServiceError
from raven.services.pipeline import STAGES, EvidenceInfo, PipelineError, run_full_pipeline
from raven.services.workspace import resolve_workspace

logger = logging.getLogger("raven.runs")

ACTIVE = ("queued", "running")


def _pending_stages() -> list[dict[str, Any]]:
    return [{"name": name, "status": "pending", "started_at": None, "finished_at": None, "summary": None, "error": None} for name in STAGES]


def run_view(run: AnalysisRun) -> dict[str, Any]:
    """The run as a plain dictionary (the shape of the analysis endpoints)."""
    return {
        "id": run.id,
        "investigation_id": run.investigation_id,
        "status": run.status,
        "stage": run.stage,
        "stages": json.loads(run.stages_json) if run.stages_json else [],
        "error": run.error,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
    }


class AnalysisRunManager:
    def __init__(
        self,
        registry_factory: sessionmaker[Session],
        settings: Settings,
        loader: Callable[[Path, Path], int] = load_evtx,
    ) -> None:
        self._factory = registry_factory
        self._settings = settings
        self.loader = loader
        self._lock = threading.Lock()
        self._threads: dict[int, threading.Thread] = {}

    # ------------------------------------------------------------------ control

    def start(self, investigation_id: int) -> int:
        """Queue a run and start its worker thread. Returns the run ID at once."""
        with self._lock:
            with self._factory() as registry:
                if registry.get(Investigation, investigation_id) is None:
                    raise ServiceError(404, "investigation_not_found", "Investigation not found.")
                active = registry.scalar(
                    select(AnalysisRun.id).where(AnalysisRun.investigation_id == investigation_id, AnalysisRun.status.in_(ACTIVE))
                )
                if active is not None:
                    raise ServiceError(409, "analysis_already_running", "An analysis run is already active for this investigation.")
                usable = registry.scalar(
                    select(EvidenceSource.id).where(EvidenceSource.investigation_id == investigation_id, EvidenceSource.status != "failed").limit(1)
                )
                if usable is None:
                    raise ServiceError(409, "no_evidence", "Upload an evidence file before running an analysis.")
                run = AnalysisRun(
                    investigation_id=investigation_id,
                    status="queued",
                    stage=None,
                    stages_json=json.dumps(_pending_stages()),
                )
                registry.add(run)
                registry.commit()
                run_id = run.id
            thread = threading.Thread(target=self._execute, args=(run_id,), name=f"raven-run-{run_id}", daemon=True)
            self._threads[run_id] = thread
            thread.start()
        return run_id

    def wait(self, run_id: int, timeout: float | None = None) -> bool:
        """Wait for the worker thread of a run. True when it has finished."""
        thread = self._threads.get(run_id)
        if thread is None:
            return True
        thread.join(timeout)
        return not thread.is_alive()

    def recover_interrupted(self) -> int:
        """Mark runs that were active when the server stopped as failed. Returns how many."""
        with self._factory() as registry:
            runs = registry.scalars(select(AnalysisRun).where(AnalysisRun.status.in_(ACTIVE))).all()
            for run in runs:
                stages = json.loads(run.stages_json) if run.stages_json else _pending_stages()
                for stage in stages:
                    if stage["status"] in ("running", "pending"):
                        stage["status"] = "failed" if stage["status"] == "running" else "pending"
                        stage["error"] = "Interrupted by a server restart." if stage["status"] == "failed" else None
                run.status = "failed"
                run.error = "Interrupted by a server restart."
                run.finished_at = utc_now_iso()
                run.stages_json = json.dumps(stages)
                for evidence in registry.scalars(
                    select(EvidenceSource).where(EvidenceSource.investigation_id == run.investigation_id, EvidenceSource.status == "processing")
                ):
                    evidence.status = "ready" if evidence.ingested_at else "uploaded"
            registry.commit()
            return len(runs)

    # ------------------------------------------------------------------ worker

    def _save(self, run_id: int, mutate: Callable[[AnalysisRun], None]) -> None:
        with self._factory() as registry:
            run = registry.get(AnalysisRun, run_id)
            if run is not None:
                mutate(run)
                registry.commit()

    def _execute(self, run_id: int) -> None:
        try:
            self._run(run_id)
        except Exception:  # noqa: BLE001 - the worker must never die silently
            logger.exception("analysis run %s stopped unexpectedly", run_id)
            self._fail(run_id, "Unexpected error. See the server log.", None, {})

    def _run(self, run_id: int) -> None:
        with self._factory() as registry:
            run = registry.get(AnalysisRun, run_id)
            investigation = registry.get(Investigation, run.investigation_id)
            workspace = resolve_workspace(self._settings.resolved_data_dir, investigation.workspace_dir)
            evidence = list(
                registry.scalars(
                    select(EvidenceSource).where(EvidenceSource.investigation_id == run.investigation_id, EvidenceSource.status != "failed").order_by(EvidenceSource.id)
                )
            )
            previous = {item.id: item.status for item in evidence}
            infos = [EvidenceInfo(item.id, item.status == "ready", item.events_total) for item in evidence]
            for item in evidence:
                item.status = "processing"
            run.status = "running"
            run.started_at = utc_now_iso()
            registry.commit()

        stages = _pending_stages()
        by_name = {stage["name"]: stage for stage in stages}

        def on_stage(name: str, status: str, summary: dict[str, Any] | None = None, error: str | None = None) -> None:
            stage = by_name[name]
            stage["status"] = status
            if status == "running":
                stage["started_at"] = utc_now_iso()
            else:
                stage["finished_at"] = utc_now_iso()
            if summary is not None:
                stage["summary"] = summary
            if error is not None:
                stage["error"] = error
            snapshot = json.dumps(stages)

            def apply(run: AnalysisRun) -> None:
                run.stage = name
                run.stages_json = snapshot

            self._save(run_id, apply)

        try:
            results = run_full_pipeline(workspace, infos, loader=self.loader, on_stage=on_stage)
        except PipelineError as exc:
            self._fail(run_id, f"Stage {exc.stage} failed: {exc.message}", exc.evidence_id, previous, exc.message)
            return

        counts = {entry["evidence_id"]: entry["records"] for entry in results["collect"]["evidence"]}
        finished = utc_now_iso()
        with self._factory() as registry:
            for item in registry.scalars(select(EvidenceSource).where(EvidenceSource.id.in_(list(previous)))):
                item.status = "ready"
                item.events_total = counts.get(item.id, item.events_total)
                item.error = None
                item.ingested_at = finished
            run = registry.get(AnalysisRun, run_id)
            run.status = "completed"
            run.stage = STAGES[-1]
            run.finished_at = finished
            run.error = None
            registry.commit()

    def _fail(self, run_id: int, message: str, evidence_id: int | None, previous: dict[int, str], evidence_error: str | None = None) -> None:
        with self._factory() as registry:
            for item in registry.scalars(select(EvidenceSource).where(EvidenceSource.status == "processing")):
                run = registry.get(AnalysisRun, run_id)
                if run is None or item.investigation_id != run.investigation_id:
                    continue
                if item.id == evidence_id:
                    item.status = "failed"
                    item.error = (evidence_error or message)[:500]
                else:
                    item.status = previous.get(item.id, "uploaded")
            run = registry.get(AnalysisRun, run_id)
            if run is not None:
                run.status = "failed"
                run.error = message[:500]
                run.finished_at = utc_now_iso()
            registry.commit()
