"""Dashboard figures (spec section 8.2): counted from the registry and from the workspaces, never invented.

Severity here means the rule severity of correlation groups (HIGH, MEDIUM, LOW, INFO) and the derived severity of an
investigation (the highest severity of its attack sessions, or none before an analysis).
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from raven.config import Settings
from raven.database.registry_models import AnalysisRun, EvidenceSource, Investigation
from raven.services.investigations import investigation_view
from raven.services.readers import workspace_overview
from raven.services.workspace import resolve_workspace

SEVERITIES = ("HIGH", "MEDIUM", "LOW", "INFO")
STATUSES = ("open", "active", "closed")
EVIDENCE_STATUSES = ("uploaded", "processing", "ready", "failed")
RECENT = 5


def build_dashboard(registry: Session, settings: Settings) -> dict[str, Any]:
    investigations = list(registry.scalars(select(Investigation).order_by(Investigation.id.desc())))
    codes = {row.id: row.code for row in investigations}
    views = [investigation_view(registry, settings, row) for row in investigations]

    findings: Counter[str] = Counter()
    alerts: list[dict[str, Any]] = []
    latest: dict[str, Any] | None = None
    sessions_total = 0
    for row in investigations:
        overview = workspace_overview(resolve_workspace(settings.resolved_data_dir, row.workspace_dir))
        sessions_total += len(overview["sessions"])
        for group in overview["groups"]:
            findings[group["severity"]] += 1
            if group["severity"] == "HIGH":
                alerts.append(
                    {
                        "investigation_id": row.id,
                        "code": row.code,
                        "group_id": group["group_id"],
                        "rule_id": group["rule_id"],
                        "rule_name": group["rule_name"],
                        "severity": group["severity"],
                        "window_start": group["window_start"],
                        "event_count": group["event_count"],
                    }
                )
        for session in overview["sessions"]:
            if latest is None or (session["start_time"], row.id) > (latest["start_time"], latest["investigation_id"]):
                members = [g for g in overview["groups"] if session["start_time"] <= g["window_start"] and g["window_end"] <= session["end_time"]]
                chain: dict[str, dict[str, Any]] = {}
                for group in members:
                    entry = chain.setdefault(
                        group["rule_id"],
                        {"rule_id": group["rule_id"], "rule_name": group["rule_name"], "severity": group["severity"], "groups": 0, "first_start": group["window_start"]},
                    )
                    entry["groups"] += 1
                latest = {
                    "investigation_id": row.id,
                    "code": row.code,
                    "session_id": session["session_id"],
                    "start_time": session["start_time"],
                    "end_time": session["end_time"],
                    "severity": session["severity"],
                    "chain": sorted(chain.values(), key=lambda e: (e["first_start"], e["rule_id"])),
                }
    alerts.sort(key=lambda a: (a["window_start"], a["group_id"]), reverse=True)

    evidence = list(registry.scalars(select(EvidenceSource).order_by(EvidenceSource.id.desc())))
    evidence_status = Counter(item.status for item in evidence)
    queue = [
        {
            "id": item.id,
            "investigation_id": item.investigation_id,
            "code": codes.get(item.investigation_id),
            "filename": item.filename,
            "status": item.status,
            "size_bytes": item.size_bytes,
            "error": item.error,
            "created_at": item.created_at,
        }
        for item in evidence
        if item.status != "ready"
    ][:10]

    activity: list[dict[str, Any]] = []
    for row in investigations:
        activity.append({"time": row.created_at, "kind": "investigation_created", "investigation_id": row.id, "code": row.code, "text": f"Investigation {row.code} was created."})
    for item in evidence:
        activity.append(
            {"time": item.created_at, "kind": "evidence_uploaded", "investigation_id": item.investigation_id, "code": codes.get(item.investigation_id), "text": f"Evidence file {item.filename} was uploaded to {codes.get(item.investigation_id)}."}
        )
    for run in registry.scalars(select(AnalysisRun).where(AnalysisRun.status.in_(("completed", "failed")), AnalysisRun.finished_at.is_not(None))):
        activity.append(
            {"time": run.finished_at, "kind": f"analysis_{run.status}", "investigation_id": run.investigation_id, "code": codes.get(run.investigation_id), "text": f"Analysis {run.status} for {codes.get(run.investigation_id)}."}
        )
    activity.sort(key=lambda a: (a["time"], a["kind"], a["investigation_id"]), reverse=True)

    case_severity = Counter(view["severity"] or "none" for view in views)
    case_status = Counter(view["status"] for view in views)
    return {
        "totals": {
            "investigations": len(views),
            "active_investigations": case_status.get("active", 0),
            "open_cases": case_status.get("open", 0),
            "evidence_items": len(evidence),
            "sessions": sessions_total,
            "high_severity_findings": findings.get("HIGH", 0),
        },
        "cases_by_severity": {name: case_severity.get(name, 0) for name in (*SEVERITIES, "none")},
        "cases_by_status": {name: case_status.get(name, 0) for name in STATUSES},
        "findings_by_severity": {name: findings.get(name, 0) for name in SEVERITIES},
        "evidence_by_status": {name: evidence_status.get(name, 0) for name in EVIDENCE_STATUSES},
        "recent_investigations": views[:RECENT],
        "latest_session": latest,
        "alerts": alerts[:RECENT],
        "recent_activity": activity[:10],
        "evidence_queue": queue,
    }
