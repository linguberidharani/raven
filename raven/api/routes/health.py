"""Health endpoints (no sign-in needed)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

import raven
from raven.api.dependencies import get_registry, get_settings_dep
from raven.config import Settings
from raven.correlation.rule_schema import RuleError, load_rules
from raven.rarf.schema import RARF_VERSION

router = APIRouter()


@router.get("/api/health", tags=["health"])
def health(response: Response, settings: Settings = Depends(get_settings_dep), registry: Session = Depends(get_registry)) -> dict[str, object]:
    """Service and artifact status: the registry database and the shipped rules."""
    try:
        registry.execute(text("SELECT 1"))
        registry_status = "ok"
    except Exception:  # noqa: BLE001 - any failure means the registry is not usable
        registry_status = "unavailable"
    try:
        rules_loaded = len(load_rules())
    except RuleError:
        rules_loaded = 0
    healthy = registry_status == "ok" and rules_loaded > 0
    if not healthy:
        response.status_code = 503
    return {
        "status": "ok" if healthy else "degraded",
        "service": "raven-api",
        "version": raven.__version__,
        "environment": settings.env,
        "registry": registry_status,
        "rules_loaded": rules_loaded,
        "rarf_version": RARF_VERSION,
    }


@router.get("/health", tags=["health"], include_in_schema=False)
def legacy_health() -> dict[str, str]:
    """Legacy path for tooling."""
    return {"status": "ok"}
