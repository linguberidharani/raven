"""Investigation, evidence and analysis endpoints (spec section 8.2). Every route needs a signed-in user."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Path, Query, Response, UploadFile
from sqlalchemy.orm import Session

from raven.api.dependencies import current_user, get_registry, get_runs, get_settings_dep
from raven.api.errors import ApiError
from raven.api.schemas.investigations import (
    AnalysisRunOut,
    EvidenceListOut,
    EvidenceOut,
    InvestigationCreate,
    InvestigationOut,
    InvestigationPage,
    InvestigationUpdate,
)
from raven.config import Settings
from raven.database.registry_models import Investigation, User
from raven.services import evidence as evidence_service
from raven.services import investigations as investigation_service
from raven.services.analysis_runs import AnalysisRunManager, run_view
from raven.services.workspace import resolve_workspace

router = APIRouter(prefix="/api/investigations", tags=["investigations"], dependencies=[Depends(current_user)])

InvestigationId = Path(ge=1, description="Numeric investigation ID")
SEVERITIES = ("HIGH", "MEDIUM", "LOW", "INFO")


def investigation_out(registry: Session, settings: Settings, row: Investigation) -> dict[str, Any]:
    workspace = resolve_workspace(settings.resolved_data_dir, row.workspace_dir)
    facts = investigation_service.workspace_facts(workspace)
    run = investigation_service.latest_run(registry, row.id)
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
            "evidence": investigation_service.evidence_count(registry, row.id),
            "detections": facts.detections,
            "sessions": facts.sessions,
            "timeline_events": facts.timeline_events,
        },
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


@router.post("", status_code=201, response_model=InvestigationOut)
def create_investigation(
    body: InvestigationCreate,
    registry: Session = Depends(get_registry),
    settings: Settings = Depends(get_settings_dep),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Create an investigation with its workspace folder."""
    row = investigation_service.create_investigation(
        registry, settings, analyst_id=user.id, title=body.title, description=body.description, host=body.host
    )
    return investigation_out(registry, settings, row)


@router.get("", response_model=InvestigationPage)
def list_investigations(
    status: str | None = Query(default=None, pattern="^(open|active|closed)$"),
    severity: str | None = Query(default=None, pattern="^(HIGH|MEDIUM|LOW|INFO)$"),
    q: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
    registry: Session = Depends(get_registry),
    settings: Settings = Depends(get_settings_dep),
) -> dict[str, Any]:
    """Investigations, newest first. The severity filter uses the derived severity."""
    if severity is None:
        rows, total = investigation_service.list_investigations(registry, status=status, q=q, page=page, page_size=page_size)
        items = [investigation_out(registry, settings, row) for row in rows]
    else:
        rows, _ = investigation_service.list_investigations(registry, status=status, q=q, page=1, page_size=10_000)
        matching = [item for item in (investigation_out(registry, settings, row) for row in rows) if item["severity"] == severity]
        total = len(matching)
        items = matching[(page - 1) * page_size : page * page_size]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/{investigation_id}", response_model=InvestigationOut)
def get_investigation(
    investigation_id: int = InvestigationId,
    registry: Session = Depends(get_registry),
    settings: Settings = Depends(get_settings_dep),
) -> dict[str, Any]:
    """Header data of one investigation: status, derived severity and stage, and counts."""
    return investigation_out(registry, settings, investigation_service.get_investigation(registry, investigation_id))


@router.patch("/{investigation_id}", response_model=InvestigationOut)
def update_investigation(
    body: InvestigationUpdate,
    investigation_id: int = InvestigationId,
    registry: Session = Depends(get_registry),
    settings: Settings = Depends(get_settings_dep),
) -> dict[str, Any]:
    """Change title, description, host or status."""
    changes = {name: getattr(body, name) for name in body.model_fields_set}
    row = investigation_service.update_investigation(registry, investigation_id, changes)
    return investigation_out(registry, settings, row)


@router.get("/{investigation_id}/evidence", response_model=EvidenceListOut)
def list_evidence(
    investigation_id: int = InvestigationId,
    registry: Session = Depends(get_registry),
    settings: Settings = Depends(get_settings_dep),
) -> dict[str, Any]:
    """Evidence files with their status and counts, and the Sysmon event-type breakdown of the stored events."""
    items = evidence_service.list_evidence(registry, investigation_id)
    row = investigation_service.get_investigation(registry, investigation_id)
    workspace = resolve_workspace(settings.resolved_data_dir, row.workspace_dir)
    return {
        "items": [EvidenceOut.model_validate(item) for item in items],
        "event_breakdown": evidence_service.event_breakdown(workspace),
    }


@router.post("/{investigation_id}/evidence", status_code=201, response_model=EvidenceOut)
def upload_evidence(
    file: UploadFile = File(...),
    investigation_id: int = InvestigationId,
    registry: Session = Depends(get_registry),
    settings: Settings = Depends(get_settings_dep),
):
    """Upload an .evtx file (multipart field "file"). It is validated, hashed with SHA-256 and stored in the workspace."""
    return evidence_service.save_upload(registry, settings, investigation_id, file.filename, file.file)


@router.post("/{investigation_id}/analysis", status_code=202, response_model=AnalysisRunOut)
def start_analysis(
    investigation_id: int = InvestigationId,
    registry: Session = Depends(get_registry),
    runs: AnalysisRunManager = Depends(get_runs),
) -> dict[str, Any]:
    """Start an analysis run. It returns at once; poll GET .../analysis for the progress."""
    run_id = runs.start(investigation_id)
    registry.expire_all()
    run = investigation_service.latest_run(registry, investigation_id)
    if run is None or run.id != run_id:
        raise ApiError(500, "run_missing", "The analysis run could not be read back.")
    return run_view(run)


@router.get("/{investigation_id}/analysis", response_model=AnalysisRunOut | None)
def latest_analysis(
    response: Response,
    investigation_id: int = InvestigationId,
    registry: Session = Depends(get_registry),
) -> dict[str, Any] | None:
    """The latest analysis run with per-stage status (null when there has been none). Meant for polling."""
    investigation_service.get_investigation(registry, investigation_id)
    response.headers["Cache-Control"] = "no-store"
    run = investigation_service.latest_run(registry, investigation_id)
    return run_view(run) if run else None
