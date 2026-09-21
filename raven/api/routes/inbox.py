"""Inbox and collector endpoints (spec sections 8.3 and 10.3, stage S14). Every route needs a signed-in user."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, Path, Response
from sqlalchemy.orm import Session

from raven.api.dependencies import current_user, get_inbox, get_registry, get_settings_dep
from raven.api.schemas.inbox import CollectorListOut, InboxListOut, LinkRequest, PollOut
from raven.api.schemas.investigations import EvidenceOut
from raven.config import Settings
from raven.services import inbox as inbox_service
from raven.services.inbox import InboxWatcher

router = APIRouter(prefix="/api", tags=["inbox"], dependencies=[Depends(current_user)])

InvestigationId = Path(ge=1, description="Numeric investigation ID")


@router.get("/inbox", response_model=InboxListOut)
def list_inbox(response: Response, registry: Session = Depends(get_registry), settings: Settings = Depends(get_settings_dep)) -> dict[str, Any]:
    """The files in the inbox folder and the investigation each one is linked to (if any)."""
    response.headers["Cache-Control"] = "no-store"
    return {"items": inbox_service.list_inbox(registry, settings)}


@router.post("/inbox/poll", response_model=PollOut)
def poll_inbox(response: Response, watcher: InboxWatcher = Depends(get_inbox)) -> dict[str, Any]:
    """Look at the inbox now (the watcher also does this by itself every few seconds)."""
    response.headers["Cache-Control"] = "no-store"
    outcome = watcher.poll_once()
    return {"results": [asdict(item) for item in outcome.results], "analyses_started": outcome.analyses_started}


@router.get("/investigations/{investigation_id}/collector", response_model=CollectorListOut)
def list_collector_sources(
    response: Response,
    investigation_id: int = InvestigationId,
    registry: Session = Depends(get_registry),
) -> dict[str, Any]:
    """The inbox files linked to this investigation, with their read position."""
    response.headers["Cache-Control"] = "no-store"
    return {"items": inbox_service.collector_sources(registry, investigation_id)}


@router.post("/investigations/{investigation_id}/collector", status_code=201, response_model=EvidenceOut)
def link_collector_source(
    body: LinkRequest,
    investigation_id: int = InvestigationId,
    registry: Session = Depends(get_registry),
    settings: Settings = Depends(get_settings_dep),
):
    """Link an inbox file to this investigation. It becomes an evidence source of type vm_collector."""
    return inbox_service.link_source(registry, settings, investigation_id, body.source_name)
