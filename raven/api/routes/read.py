"""Read endpoints (spec section 8.2, stage S13): dashboard, rules, detections, reconstruction, timeline, events,
impact, RARF and report. Every route needs a signed-in user. They only read what the pipeline stored."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Path, Query, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from raven.api.dependencies import current_user, get_registry, get_settings_dep
from raven.api.schemas.read import (
    DashboardOut,
    DetectionsOut,
    EventDetailOut,
    ImpactOut,
    ReconstructionOut,
    RulesOut,
    TimelinePage,
)
from raven.config import Settings
from raven.correlation.rule_schema import load_rules
from raven.database.registry_models import EvidenceSource
from raven.services import dashboard as dashboard_service
from raven.services import investigations as investigation_service
from raven.services import readers
from raven.services.clock import utc_now_iso
from raven.services.errors import ServiceError
from raven.services.workspace import Workspace, resolve_workspace

router = APIRouter(prefix="/api", tags=["read"], dependencies=[Depends(current_user)])

InvestigationId = Path(ge=1, description="Numeric investigation ID")
_NO_STORE = {"Cache-Control": "no-store"}


def workspace_of(investigation_id: int, registry: Session, settings: Settings) -> Workspace:
    row = investigation_service.get_investigation(registry, investigation_id)
    return resolve_workspace(settings.resolved_data_dir, row.workspace_dir)


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(response: Response, registry: Session = Depends(get_registry), settings: Settings = Depends(get_settings_dep)) -> dict[str, Any]:
    """Totals, splits, recent investigations, alerts, recent activity and the evidence queue, counted from real records."""
    response.headers.update(_NO_STORE)
    return dashboard_service.build_dashboard(registry, settings)


@router.get("/rules", response_model=RulesOut)
def shipped_rules(response: Response) -> dict[str, Any]:
    """The shipped correlation rule definitions."""
    response.headers.update(_NO_STORE)
    return {"rules": [rule.to_definition() for rule in load_rules()]}


@router.get("/investigations/{investigation_id}/detections", response_model=DetectionsOut)
def detections(
    response: Response,
    investigation_id: int = InvestigationId,
    rule: str | None = Query(default=None, max_length=64, description="Only groups of this rule ID"),
    severity: str | None = Query(default=None, pattern="^(HIGH|MEDIUM|LOW|INFO)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    registry: Session = Depends(get_registry),
    settings: Settings = Depends(get_settings_dep),
) -> dict[str, Any]:
    """Rules, correlation groups (paged, filterable) and why each group matched."""
    response.headers.update(_NO_STORE)
    workspace = workspace_of(investigation_id, registry, settings)
    return readers.detections(workspace, rule_id=rule, severity=severity, page=page, page_size=page_size)


@router.get("/investigations/{investigation_id}/reconstruction", response_model=ReconstructionOut)
def reconstruction(
    response: Response,
    investigation_id: int = InvestigationId,
    registry: Session = Depends(get_registry),
    settings: Settings = Depends(get_settings_dep),
) -> dict[str, Any]:
    """Attack sessions with their groups in time order (the attack chain) and the process tree."""
    response.headers.update(_NO_STORE)
    return readers.reconstruction(workspace_of(investigation_id, registry, settings))


@router.get("/investigations/{investigation_id}/timeline", response_model=TimelinePage)
def timeline(
    response: Response,
    investigation_id: int = InvestigationId,
    session: str | None = Query(default=None, max_length=200, description="Only this attack session ID"),
    event_type: str | None = Query(default=None, pattern="^(process_creation|network_connection|file_create)$"),
    rule: str | None = Query(default=None, max_length=64, description="Only events of groups of this rule ID"),
    q: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
    registry: Session = Depends(get_registry),
    settings: Settings = Depends(get_settings_dep),
) -> dict[str, Any]:
    """The ordered timeline events (paged, filterable)."""
    response.headers.update(_NO_STORE)
    workspace = workspace_of(investigation_id, registry, settings)
    return readers.timeline(workspace, session_id=session, event_type=event_type, rule_id=rule, q=q, page=page, page_size=page_size)


@router.get("/investigations/{investigation_id}/events/{event_ref}", response_model=EventDetailOut)
def event_detail(
    response: Response,
    investigation_id: int = InvestigationId,
    event_ref: str = Path(pattern=r"^\d+:\d+$", description="Raw event reference <evidence id>:<record id>"),
    registry: Session = Depends(get_registry),
    settings: Settings = Depends(get_settings_dep),
) -> dict[str, Any]:
    """One event: the normalized fields, the raw fields and the original XML."""
    response.headers.update(_NO_STORE)
    workspace = workspace_of(investigation_id, registry, settings)
    evidence = registry.get(EvidenceSource, int(event_ref.partition(":")[0]))
    if evidence is None or evidence.investigation_id != investigation_id:
        raise ServiceError(404, "event_not_found", "No stored event has this reference.")
    return readers.event_detail(workspace, event_ref)


@router.get("/investigations/{investigation_id}/impact", response_model=ImpactOut)
def impact(
    response: Response,
    investigation_id: int = InvestigationId,
    registry: Session = Depends(get_registry),
    settings: Settings = Depends(get_settings_dep),
) -> dict[str, Any]:
    """Impact per category: observed counts and assets, and the derived score, with the activity over time."""
    response.headers.update(_NO_STORE)
    return readers.impact(workspace_of(investigation_id, registry, settings))


def _artifact(workspace: Workspace, session: str | None, folder_name: str, prefix: str, missing_code: str) -> tuple[dict[str, Any], str]:
    ids = readers.session_ids(workspace)
    if not ids:
        raise ServiceError(404, "not_analysed", "Run an analysis first.")
    chosen = session or ids[0]
    if chosen not in ids:
        raise ServiceError(404, "session_not_found", "No attack session has this ID.")
    folder = workspace.rarf_dir if folder_name == "rarf" else workspace.report_dir
    path = readers.artifact_path(folder, prefix, chosen)
    if path is None:
        raise ServiceError(404, missing_code, "The file of this session is not available; run the analysis again.")
    return json.loads(path.read_text(encoding="utf-8")), path.name


@router.get("/investigations/{investigation_id}/rarf", response_model=None)
def rarf(
    investigation_id: int = InvestigationId,
    session: str | None = Query(default=None, max_length=200, description="Attack session ID (default: the first session)"),
    download: bool = Query(default=False, description="Send as a file download"),
    registry: Session = Depends(get_registry),
    settings: Settings = Depends(get_settings_dep),
) -> JSONResponse:
    """The RARF document of a session, as written by the pipeline."""
    document, name = _artifact(workspace_of(investigation_id, registry, settings), session, "rarf", "RARF", "rarf_not_found")
    headers = dict(_NO_STORE)
    if download:
        headers["Content-Disposition"] = f'attachment; filename="{name}"'
    return JSONResponse(content=document, headers=headers)


@router.get("/investigations/{investigation_id}/report", response_model=None)
def report(
    investigation_id: int = InvestigationId,
    session: str | None = Query(default=None, max_length=200, description="Attack session ID (default: the first session)"),
    registry: Session = Depends(get_registry),
    settings: Settings = Depends(get_settings_dep),
) -> JSONResponse:
    """The deterministic report of a session. generated_at is set now; nothing else changes between requests."""
    document, _name = _artifact(workspace_of(investigation_id, registry, settings), session, "report", "REPORT", "report_not_found")
    document["generated_at"] = utc_now_iso()
    return JSONResponse(content=document, headers=_NO_STORE)
