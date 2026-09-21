"""Orchestration of the processing pipeline for one investigation workspace (spec section 7).

    run_full_pipeline(workspace, evidence, loader=load_evtx, on_stage=None) -> {stage name: summary}

The stages run in this order, each on the files and the database of THIS workspace only:

    collect      EVTX -> raw JSONL (an evidence file that is already collected is not read again)
    normalize    raw JSONL -> normalized JSONL (raw_event_ref = <evidence id>:<record id>)
    deduplicate  all normalized files together -> one deduplicated file
    ingest       deduplicated file -> events table (skips events that are already there)
    correlate    rules -> correlation groups
    reconstruct  groups -> attack sessions
    timeline     sessions -> ordered events with descriptions
    impact       timeline -> impact analysis
    rarf         database -> RARF file per session
    report       RARF -> report file per session

Every stage reports its numbers through on_stage(name, status, summary, error), so a run shows real per-stage
progress. Running the pipeline again on the same evidence gives the same results.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select

from raven.collectors.evtx_loader import EvtxLoadError, load_evtx
from raven.correlation.runner import run_correlation
from raven.database.ingest import ingest_events
from raven.database.models import AttackSession
from raven.fileio import write_lines_atomic, write_text_atomic
from raven.impact.persist import run_impact
from raven.parsers.deduplicate import deduplicate
from raven.parsers.normalizer import normalize_all
from raven.rarf.exporter import export_rarf
from raven.reconstruction.persist import run_reconstruction
from raven.report.generator import generate_report, report_text
from raven.report.schema import validate_report
from raven.services.workspace import Workspace
from raven.timeline.persist import run_timeline

STAGES: tuple[str, ...] = (
    "collect",
    "normalize",
    "deduplicate",
    "ingest",
    "correlate",
    "reconstruct",
    "timeline",
    "impact",
    "rarf",
    "report",
)

StageCallback = Callable[[str, str, "dict[str, Any] | None", "str | None"], None]


@dataclass(frozen=True)
class EvidenceInfo:
    """An evidence file of the run. ready + events_total let an already collected file be reused.

    A vm_collector source has no EVTX file: the inbox watcher keeps its raw JSONL file up to date, so it is always
    "collected" and only counted.
    """

    id: int
    ready: bool = False
    events_total: int = 0
    source_type: str = "evtx_upload"


class PipelineError(Exception):
    def __init__(self, stage: str, message: str, evidence_id: int | None = None) -> None:
        super().__init__(f"{stage}: {message}")
        self.stage = stage
        self.message = message
        self.evidence_id = evidence_id


def _count_lines(path: Path) -> int:
    if not path.is_file():
        return 0
    with open(path, "r", encoding="utf-8", newline="\n") as handle:
        return sum(1 for line in handle if line.strip())


def _lines(paths: list[Path]) -> Iterator[str]:
    for path in paths:
        with open(path, "r", encoding="utf-8", newline="\n") as handle:
            for line in handle:
                yield line.rstrip("\n")


def run_full_pipeline(
    workspace: Workspace,
    evidence: list[EvidenceInfo],
    *,
    loader: Callable[[Path, Path], int] = load_evtx,
    on_stage: StageCallback | None = None,
) -> dict[str, dict[str, Any]]:
    workspace.ensure()
    ordered = sorted(evidence, key=lambda item: item.id)
    notify = on_stage or (lambda *_args: None)
    results: dict[str, dict[str, Any]] = {}
    factory = None
    current = {"stage": "", "evidence_id": None}

    def begin(name: str) -> None:
        current["stage"], current["evidence_id"] = name, None
        notify(name, "running", None, None)

    def finish(name: str, summary: dict[str, Any]) -> None:
        results[name] = summary
        notify(name, "completed", summary, None)

    try:
        # ------------------------------------------------------------ collect
        begin("collect")
        collected: list[dict[str, Any]] = []
        for item in ordered:
            current["evidence_id"] = item.id
            raw = workspace.raw_path(item.id)
            if item.source_type == "vm_collector":
                collected.append({"evidence_id": item.id, "records": _count_lines(raw), "reused": True})
            elif item.ready and raw.is_file():
                collected.append({"evidence_id": item.id, "records": item.events_total, "reused": True})
            else:
                collected.append({"evidence_id": item.id, "records": loader(workspace.evidence_path(item.id), raw), "reused": False})
        current["evidence_id"] = None
        finish("collect", {"evidence": collected, "records": sum(entry["records"] for entry in collected)})

        # ------------------------------------------------------------ normalize
        begin("normalize")
        total = 0
        statuses: Counter[str] = Counter()
        types: Counter[str] = Counter()
        with_raw = [item for item in ordered if workspace.raw_path(item.id).is_file()]
        for item in with_raw:
            summary = normalize_all(workspace.raw_path(item.id), workspace.normalized_path(item.id), item.id)
            total += summary["total"]
            statuses.update(summary["status_counts"])
            types.update(summary["event_type_counts"])
        finish("normalize", {"events": total, "status_counts": dict(sorted(statuses.items())), "event_type_counts": dict(sorted(types.items()))})

        # ------------------------------------------------------------ deduplicate
        begin("deduplicate")
        write_lines_atomic(workspace.combined_normalized_path, _lines([workspace.normalized_path(item.id) for item in with_raw]))
        outcome = deduplicate(workspace.combined_normalized_path, workspace.deduplicated_path, workspace.duplicates_path)
        finish("deduplicate", {"input": outcome.input_count, "unique": outcome.unique_count, "removed": outcome.removed_count})

        # ------------------------------------------------------------ database stages
        factory = workspace.open_database()

        begin("ingest")
        finish("ingest", ingest_events(workspace.deduplicated_path, workspace.summary_path("ingest"), factory))

        begin("correlate")
        correlation = run_correlation(factory, workspace.summary_path("correlation"))
        finish(
            "correlate",
            {
                "groups": correlation["totals"]["groups"],
                "groups_by_rule": {rule["rule_id"]: rule["groups"] for rule in correlation["rules"]},
                "distinct_events": correlation["totals"]["distinct_events"],
                "distinct_events_by_type": correlation["totals"]["distinct_events_by_type"],
            },
        )

        begin("reconstruct")
        sessions = run_reconstruction(factory, workspace.summary_path("sessions_mapping"))
        finish("reconstruct", {"sessions": sessions["totals"]["sessions"], "groups": sessions["totals"]["groups"]})

        begin("timeline")
        timeline = run_timeline(factory, workspace.summary_path("timeline"))
        finish("timeline", {"timeline_events": timeline["totals"]["timeline_events"]})

        begin("impact")
        impact = run_impact(factory, workspace.summary_path("impact"))
        finish(
            "impact",
            {
                "sessions": [
                    {
                        "session_id": item["session_id"],
                        "scores": {c["category"]: c["impact_score"] for c in item["categories"]},
                        "events": {c["category"]: c["event_count"] for c in item["categories"]},
                    }
                    for item in impact["sessions"]
                ]
            },
        )

        begin("rarf")
        exported = export_rarf(factory, workspace.rarf_dir)
        finish(
            "rarf",
            {
                "files": [item.path.name for item in exported],
                "traceability": [{name: len(values) for name, values in item.document["traceability"].items()} for item in exported],
            },
        )

        begin("report")
        with factory() as session:
            database_ids = {row.session_id: row.id for row in session.scalars(select(AttackSession))}
        report_files: list[str] = []
        observed = derived = 0
        for item in exported:
            report = generate_report(item.document, attack_session_id=database_ids[item.session_id])
            problems = validate_report(report, item.document)
            if problems:
                raise ValueError("the report is not valid: " + "; ".join(problems))
            path = workspace.report_dir / f"REPORT-{item.session_id}.json"
            write_text_atomic(path, report_text(report))
            report_files.append(path.name)
            findings = [f for section in report["sections"] for f in section["findings"]]
            observed += sum(1 for f in findings if f["basis"] == "observed")
            derived += sum(1 for f in findings if f["basis"] == "derived")
        finish("report", {"files": report_files, "observed_findings": observed, "derived_findings": derived})
    except PipelineError:
        raise
    except EvtxLoadError as exc:
        notify(current["stage"], "failed", None, str(exc))
        raise PipelineError(current["stage"], str(exc), current["evidence_id"]) from exc
    except Exception as exc:  # noqa: BLE001 - every failure is reported with its stage
        message = str(exc) or exc.__class__.__name__
        notify(current["stage"], "failed", None, message)
        raise PipelineError(current["stage"], message, current["evidence_id"]) from exc
    finally:
        if factory is not None:
            factory.kw["bind"].dispose()
    return results

