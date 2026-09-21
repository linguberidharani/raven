"""Report structure and wording checks (spec section 6.11).

    report_title, attack_session_id, session_id, generated_at,
    sections[ {section_id, title, findings[ {statement, basis, evidence{...}} ]} ]

basis is "observed" (a direct fact or a count of recorded events) or "derived" (RAVEN's conclusion).
evidence holds event_ids, correlation_group_ids, timeline_event_ids, impact_analysis_ids and raw_event_refs.
generated_at is null in the generated content: the API sets it when a report is requested, and it is not part
of the deterministic content.

validate_report also enforces the product wording rules: no forbidden phrases anywhere, and the words about
encryption only inside the confidence_limitations section, where the report must say that intent, malware
identity, exfiltration and complete encryption are not established.
"""

from __future__ import annotations

from typing import Any

SECTION_IDS = (
    "executive_summary",
    "session_overview",
    "detection_evidence",
    "timeline_summary",
    "impact_analysis",
    "evidence_traceability",
    "confidence_limitations",
)
SECTION_TITLES = {
    "executive_summary": "Executive summary",
    "session_overview": "Session overview",
    "detection_evidence": "Detection evidence",
    "timeline_summary": "Timeline summary",
    "impact_analysis": "Impact analysis",
    "evidence_traceability": "Evidence traceability",
    "confidence_limitations": "Confidence and limitations",
}
BASES = ("observed", "derived")
REPORT_FIELDS = ("report_title", "attack_session_id", "session_id", "generated_at", "sections")
FINDING_FIELDS = ("statement", "basis", "evidence")
EVIDENCE_FIELDS = ("event_ids", "correlation_group_ids", "timeline_event_ids", "impact_analysis_ids", "raw_event_refs")

FORBIDDEN_PHRASES = (
    "encrypt files",
    "decrypt files",
    "encryption engine",
    "encryption service",
    "automatically detects and prevents ransomware",
    "real-time protection",
)
REQUIRED_LIMITATION_WORDS = ("intent", "malware", "exfiltration", "encryption")


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_report(report: Any, rarf: dict[str, Any] | None = None) -> list[str]:
    """Return the problems found in a report. With the RARF it was built from, also check its evidence."""
    if not isinstance(report, dict):
        return ["report must be an object"]
    problems: list[str] = []
    missing = [name for name in REPORT_FIELDS if name not in report]
    extra = [name for name in report if name not in REPORT_FIELDS]
    if missing:
        problems.append("report: missing " + ", ".join(missing))
    if extra:
        problems.append("report: unexpected " + ", ".join(sorted(map(str, extra))))
    if missing or extra:
        return problems

    if not isinstance(report["report_title"], str) or not report["report_title"]:
        problems.append("report_title must be a non-empty string")
    if report["attack_session_id"] is not None and not _is_int(report["attack_session_id"]):
        problems.append("attack_session_id must be null or an integer")
    if not isinstance(report["session_id"], str) or not report["session_id"]:
        problems.append("session_id must be a non-empty string")
    if report["generated_at"] is not None and not isinstance(report["generated_at"], str):
        problems.append("generated_at must be null or a string")

    sections = report["sections"]
    if not isinstance(sections, list) or [s.get("section_id") if isinstance(s, dict) else None for s in sections] != list(SECTION_IDS):
        problems.append("sections must be " + ", ".join(SECTION_IDS) + " in this order")
        return problems

    known_events: set[int] = set()
    known_groups: set[str] = set()
    known_timeline: set[int] = set()
    known_impact: set[int] = set()
    ref_of: dict[int, str] = {}
    if rarf is not None:
        trace = rarf["traceability"]
        known_events, known_groups = set(trace["event_ids"]), set(trace["correlation_group_ids"])
        known_timeline, known_impact = set(trace["timeline_event_ids"]), set(trace["impact_analysis_ids"])
        ref_of = dict(zip(trace["event_ids"], trace["raw_event_refs"]))
        if report["session_id"] != rarf["attack_session"]["session_id"]:
            problems.append("session_id must be the session ID of the RARF")

    limitation_text = ""
    for section in sections:
        section_id = section["section_id"]
        if set(section) != {"section_id", "title", "findings"}:
            problems.append(f"{section_id}: a section needs exactly section_id, title and findings")
            continue
        if section["title"] != SECTION_TITLES[section_id]:
            problems.append(f"{section_id}: the title must be {SECTION_TITLES[section_id]!r}")
        findings = section["findings"]
        if not isinstance(findings, list) or not findings:
            problems.append(f"{section_id}: findings must be a non-empty list")
            continue
        for number, finding in enumerate(findings, start=1):
            where = f"{section_id} finding {number}"
            if not isinstance(finding, dict) or set(finding) != set(FINDING_FIELDS):
                problems.append(f"{where}: needs exactly statement, basis and evidence")
                continue
            statement = finding["statement"]
            if not isinstance(statement, str) or not statement.strip():
                problems.append(f"{where}: the statement must be a non-empty string")
                continue
            if finding["basis"] not in BASES:
                problems.append(f"{where}: basis must be observed or derived")
            lowered = statement.lower()
            for phrase in FORBIDDEN_PHRASES:
                if phrase in lowered:
                    problems.append(f"{where}: forbidden wording: {phrase}")
            if "encrypt" in lowered and section_id != "confidence_limitations":
                problems.append(f"{where}: words about encryption may only appear in confidence_limitations")
            if section_id == "confidence_limitations":
                limitation_text += " " + lowered

            evidence = finding["evidence"]
            if not isinstance(evidence, dict) or list(evidence) != list(EVIDENCE_FIELDS):
                problems.append(f"{where}: evidence must have exactly " + ", ".join(EVIDENCE_FIELDS) + " in this order")
                continue
            if not all(isinstance(evidence[k], list) for k in EVIDENCE_FIELDS):
                problems.append(f"{where}: every evidence entry must be a list")
                continue
            if not all(_is_int(i) for i in evidence["event_ids"] + evidence["timeline_event_ids"] + evidence["impact_analysis_ids"]):
                problems.append(f"{where}: event, timeline and impact IDs must be integers")
                continue
            if len(evidence["raw_event_refs"]) != len(evidence["event_ids"]):
                problems.append(f"{where}: one raw event reference per event ID is required")
            if rarf is not None:
                if not set(evidence["event_ids"]) <= known_events:
                    problems.append(f"{where}: evidence names events that are not in the RARF")
                elif [ref_of[i] for i in evidence["event_ids"]] != evidence["raw_event_refs"]:
                    problems.append(f"{where}: raw event references do not belong to the event IDs")
                if not set(evidence["correlation_group_ids"]) <= known_groups:
                    problems.append(f"{where}: evidence names correlation groups that are not in the RARF")
                if not set(evidence["timeline_event_ids"]) <= known_timeline:
                    problems.append(f"{where}: evidence names timeline events that are not in the RARF")
                if not set(evidence["impact_analysis_ids"]) <= known_impact:
                    problems.append(f"{where}: evidence names impact analyses that are not in the RARF")

    for word in REQUIRED_LIMITATION_WORDS:
        if word not in limitation_text:
            problems.append(f"confidence_limitations must state that {word} is not established")
    return problems
