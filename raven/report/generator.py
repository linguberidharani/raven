"""Deterministic report generator (spec sections 6.11 and 7).

    generate_report(rarf, attack_session_id=None) -> report document (see schema.py)

The report is built from the RARF document only, in controlled wording: every finding is a fixed sentence
with numbers and names taken from the RARF, marked "observed" (a direct fact or a count of recorded events)
or "derived" (a conclusion of RAVEN, such as a rule match, the session severity or a calculated metric), and
linked to the evidence it rests on. The same RARF always gives the same report, byte for byte. generated_at
is null: the API sets it when a report is requested.

Nothing in the report claims intent, malware identity, data exfiltration or complete encryption. The section
confidence_limitations says so.

Run from the command line:

    python -m raven.report.generator <RARF-....json> <output folder> [--print]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from raven.collectors.raw_jsonl import sha256_file
from raven.fileio import write_text_atomic
from raven.rarf.schema import validate_rarf
from raven.report.evidence import ReportSource, format_duration, group_match_value
from raven.report.schema import SECTION_IDS, SECTION_TITLES, validate_report

_TYPE_WORDS = {
    "process_creation": "process creation",
    "network_connection": "network connection",
    "file_create": "file creation",
}
_MATCH_LABELS = {"process_id": "process ID", "process_guid": "process GUID"}
_EXAMPLES = 3


class ReportError(ValueError):
    """The report cannot be generated."""


def _finding(statement: str, basis: str, evidence: dict[str, list[Any]]) -> dict[str, Any]:
    return {"statement": statement, "basis": basis, "evidence": evidence}


def _plural(number: int, singular: str, plural: str | None = None) -> str:
    return f"{number} {singular if number == 1 else (plural or singular + 's')}"


def _minute_label(minute: str) -> str:
    return f"{minute[:10]} {minute[11:16]}"


def _steps_text(definition: dict[str, Any]) -> str:
    return ", then ".join(
        f"at least {step['min_count']} {_TYPE_WORDS[step['event_type']]} event(s)" for step in definition["steps"]
    )


def _examples(assets: list[str]) -> str:
    shown = assets[:_EXAMPLES]
    return "; ".join(shown) + (f"; and {len(assets) - len(shown)} more" if len(assets) > len(shown) else "")


# ---------------------------------------------------------------------------- sections


def _executive_summary(src: ReportSource) -> list[dict[str, Any]]:
    session = src.session
    all_events = src.all_events()
    all_groups = [group["correlation_group_id"] for group in src.groups]
    counts = {name: len(src.events_of_type(name)) for name in _TYPE_WORDS}
    rule_ids = [rule["rule_id"] for rule in src.rules]
    rule_names = [f"{rule['rule_id']} ({rule['rule_name']})" for rule in src.rules]
    impact_ids = [category["impact_analysis_id"] for category in src.categories.values()]
    return [
        _finding(
            f"Based on the available evidence, {src.event_count} recorded events from the computer {session['computer']} "
            f"between {session['start_time']} and {session['end_time']} (UTC) belong to one reconstructed session.",
            "observed",
            src.evidence(all_events, all_groups),
        ),
        _finding(
            f"These events are {_plural(counts['file_create'], 'file creation event')}, "
            f"{_plural(counts['network_connection'], 'network connection event')} and "
            f"{_plural(counts['process_creation'], 'process creation event')}.",
            "observed",
            src.evidence(all_events, (), impact_ids),
        ),
        _finding(
            f"RAVEN matched {_plural(len(src.groups), 'correlation group')} from {_plural(len(src.rules), 'rule')} "
            f"({', '.join(rule_ids)}) and grouped them into one session with the severity {session['severity']}. "
            "The session severity is the highest severity of the matching rules.",
            "derived",
            src.evidence(all_events, all_groups),
        ),
        _finding(
            "The recorded activity is consistent with the pattern(s) described by the matching rule(s): "
            + "; ".join(rule_names)
            + ". A matching pattern alone does not show the purpose of the activity.",
            "derived",
            src.evidence(all_events, all_groups),
        ),
    ]


def _session_overview(src: ReportSource) -> list[dict[str, Any]]:
    session = src.session
    confidence = session["confidence"]
    confidence_text = (
        "No confidence value is assigned to this session; RAVEN does not claim one."
        if confidence is None
        else f"The confidence value assigned to this session is {confidence}."
    )
    return [
        _finding(f"Session ID: {session['session_id']}. Computer: {session['computer']}.", "observed", src.evidence()),
        _finding(
            f"The first recorded event of the session is at {src.first_timestamp} and the last at {src.last_timestamp} (UTC).",
            "observed",
            src.evidence([src.timeline[0]["event_id"], src.timeline[-1]["event_id"]]),
        ),
        _finding(
            f"The time between the first and the last recorded event is {format_duration(src.duration_ms())}.",
            "derived",
            src.evidence([src.timeline[0]["event_id"], src.timeline[-1]["event_id"]]),
        ),
        _finding(
            f"The session severity is {session['severity']}: the highest severity of the matching rules.",
            "derived",
            src.evidence((), [group["correlation_group_id"] for group in src.groups]),
        ),
        _finding(confidence_text, "observed", src.evidence()),
        _finding(f"Description recorded for the session: {session['description']}", "observed", src.evidence()),
    ]


def _detection_evidence(src: ReportSource) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for rule in src.rules:
        definition = rule["rule_definition"]
        rule_id = rule["rule_id"]
        groups = src.groups_of_rule(rule_id)
        group_ids = [group["correlation_group_id"] for group in groups]
        events = src.events_of_groups(groups)
        label = _MATCH_LABELS.get(definition["match_key"], definition["match_key"])
        values = {group_match_value(group_id) for group_id in group_ids}
        findings.append(
            _finding(
                f"Rule {rule_id} ({rule['rule_name']}, severity {definition['severity']}, rule confidence "
                f"{definition['confidence']}) matched {_plural(len(groups), 'correlation group')}. For one {label} it looks for "
                f"{_steps_text(definition)} within {definition['time_window_seconds']} seconds.",
                "derived",
                src.evidence(events, group_ids),
            )
        )
        findings.append(
            _finding(
                f"The correlation group(s) of rule {rule_id} involve {len(values)} different "
                f"{label}(s) and {len(events)} distinct recorded events.",
                "observed",
                src.evidence(events, group_ids),
            )
        )
    all_events = src.all_events()
    entries = src.group_event_entries()
    findings.append(
        _finding(
            f"In total {_plural(len(src.groups), 'correlation group')} contain {entries} event entries, of which "
            f"{len(all_events)} are distinct recorded events. An event can belong to the groups of several rules.",
            "observed",
            src.evidence(all_events, [group["correlation_group_id"] for group in src.groups]),
        )
    )
    return findings


def _timeline_summary(src: ReportSource) -> list[dict[str, Any]]:
    all_events = src.all_events()
    minutes = src.events_per_minute()
    busiest, busiest_count = src.busiest_minute()
    ordered = src.ordered_groups()
    first_group, last_group = ordered[0], ordered[-1]
    findings = [
        _finding(
            f"The timeline lists {src.event_count} events in time order, from {src.first_timestamp} to {src.last_timestamp} (UTC).",
            "observed",
            src.evidence(all_events),
        ),
        _finding(
            "Recorded events per minute (UTC): " + "; ".join(f"{_minute_label(m)}: {n}" for m, n in minutes) + ".",
            "observed",
            src.evidence(all_events),
        ),
        _finding(
            f"The busiest minute is {_minute_label(busiest)} with {busiest_count} recorded events.",
            "observed",
            src.evidence([e["event_id"] for e in src.timeline if e["timestamp"][:16] == busiest]),
        ),
        _finding(
            f"The first correlation group starts at {src.group_span(first_group)[0]} ({first_group['correlation_group_id']}); "
            f"the last starts at {src.group_span(last_group)[0]} ({last_group['correlation_group_id']}).",
            "observed",
            src.evidence(
                set(first_group["event_ids"]) | set(last_group["event_ids"]),
                [first_group["correlation_group_id"], last_group["correlation_group_id"]],
            ),
        ),
    ]
    for event_type, label in (("process_creation", "process creation"), ("network_connection", "network connection")):
        events = src.events_of_type(event_type)
        if events:
            first, last = events[0], events[-1]
            findings.append(
                _finding(
                    f"The first {label} event of the timeline is at {first['timestamp']} (raw event reference "
                    f"{first['raw_event_ref']}); the last is at {last['timestamp']} (raw event reference {last['raw_event_ref']}).",
                    "observed",
                    src.evidence([first["event_id"], last["event_id"]]),
                )
            )
    return findings


def _impact_analysis(src: ReportSource) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    files = src.category("files_affected")
    network = src.category("network_activity")
    process = src.category("process_activity")
    unsupported = src.category("unsupported_events")

    def evidence_of(category: dict[str, Any]) -> dict[str, list[Any]]:
        return src.evidence(category["analysis"]["event_ids"], (), [category["impact_analysis_id"]])

    if files["analysis"]["event_count"]:
        details = files["analysis"]["details"]
        findings.append(
            _finding(
                f"File creation: {files['analysis']['event_count']} file creation event(s) cover {files['impact_score']} distinct "
                f"file path(s) and were recorded for {details['distinct_processes']} distinct process image(s). "
                f"Examples: {_examples(files['affected_assets'])}.",
                "observed",
                evidence_of(files),
            )
        )
    if network["analysis"]["event_count"]:
        protocols = ", ".join(network["analysis"]["details"].get("protocols_seen", [])) or "none recorded"
        findings.append(
            _finding(
                f"Network connection: {network['analysis']['event_count']} network connection event(s) cover "
                f"{network['impact_score']} distinct destination(s) (address:port); protocols seen: {protocols}. "
                f"Examples: {_examples(network['affected_assets'])}.",
                "observed",
                evidence_of(network),
            )
        )
    if process["analysis"]["event_count"]:
        findings.append(
            _finding(
                f"Process creation: {process['analysis']['event_count']} process creation event(s) cover "
                f"{process['impact_score']} distinct process image(s). Examples: {_examples(process['affected_assets'])}.",
                "observed",
                evidence_of(process),
            )
        )
    if unsupported["analysis"]["event_count"]:
        findings.append(
            _finding(
                f"Other event types: {unsupported['analysis']['event_count']} events of types that RAVEN does not interpret "
                f"belong to this session (Sysmon event IDs: {', '.join(unsupported['affected_assets'])}).",
                "observed",
                evidence_of(unsupported),
            )
        )
    else:
        findings.append(
            _finding(
                "No events of types that RAVEN does not interpret belong to this session.",
                "observed",
                src.evidence((), (), [unsupported["impact_analysis_id"]]),
            )
        )
    impact_ids = [category["impact_analysis_id"] for category in src.categories.values()]
    findings.append(
        _finding(
            "RAVEN calculates an impact score for each category as the number of distinct affected assets (files "
            f"{files['impact_score']}, network destinations {network['impact_score']}, process images {process['impact_score']}, "
            f"other event types {unsupported['impact_score']}). The score is a calculated count. It does not measure damage, "
            "and no monetary or business impact is calculated.",
            "derived",
            src.evidence((), (), impact_ids),
        )
    )
    return findings


def _evidence_traceability(src: ReportSource) -> list[dict[str, Any]]:
    trace = src.traceability
    first = src.timeline[0]
    first_group = src.ordered_groups()[0]
    first_rule = next(rule for rule in src.rules if rule["rule_id"] == first_group["correlation_type"])
    match_label = _MATCH_LABELS.get(first_rule["rule_definition"]["match_key"], first_rule["rule_definition"]["match_key"])
    return [
        _finding(
            f"This report rests on {len(trace['event_ids'])} event IDs, {len(trace['raw_event_refs'])} raw event references, "
            f"{len(trace['correlation_group_ids'])} correlation group IDs, {len(trace['timeline_event_ids'])} timeline event IDs "
            f"and {len(trace['impact_analysis_ids'])} impact analysis IDs, all listed in the evidence record {src.rarf['rarf_id']}.",
            "observed",
            src.evidence(src.all_events(), trace["correlation_group_ids"], trace["impact_analysis_ids"]),
        ),
        _finding(
            f"A raw event reference such as {first['raw_event_ref']} identifies one record of the original Sysmon log file; "
            "the original XML of that record is kept with the raw data.",
            "observed",
            src.evidence([first["event_id"]]),
        ),
        _finding(
            f"A correlation group ID such as {first_group['correlation_group_id']} names the rule, the {match_label} "
            "and the start time of the group.",
            "observed",
            src.evidence(first_group["event_ids"], [first_group["correlation_group_id"]]),
        ),
    ]


def _confidence_limitations(src: ReportSource) -> list[dict[str, Any]]:
    unsupported = src.category("unsupported_events")
    return [
        _finding(
            "Based on the available evidence, this report does not establish the intent of the activity, the identity of any "
            "malware, any transfer of data out of the environment (exfiltration) or complete encryption of data. "
            "None of these is concluded here.",
            "derived",
            src.evidence(),
        ),
        _finding(
            "Rule matches and the reconstructed session are patterns in recorded events. Bursts of file creation, process "
            "creation and network connections also occur in normal system activity, so a match alone does not show that the "
            "activity was unwanted.",
            "derived",
            src.evidence(),
        ),
        _finding(
            "Only Sysmon events of the types process creation (1), network connection (3) and file creation (11) are analysed. "
            f"Events of other types are stored but not interpreted; {unsupported['analysis']['event_count']} of them belong to this session.",
            "observed",
            src.evidence((), (), [unsupported["impact_analysis_id"]]),
        ),
        _finding(
            "The correlation rules look at events of one process ID. They do not follow a process through other process IDs, "
            "and events of other kinds (for example registry or DNS activity) are not analysed.",
            "derived",
            src.evidence(),
        ),
        _finding("Times are shown in UTC as recorded by the event log.", "observed", src.evidence()),
        _finding("No monetary or business impact is calculated in this report.", "observed", src.evidence()),
    ]


_BUILDERS = {
    "executive_summary": _executive_summary,
    "session_overview": _session_overview,
    "detection_evidence": _detection_evidence,
    "timeline_summary": _timeline_summary,
    "impact_analysis": _impact_analysis,
    "evidence_traceability": _evidence_traceability,
    "confidence_limitations": _confidence_limitations,
}


def generate_report(rarf: dict[str, Any], attack_session_id: int | None = None) -> dict[str, Any]:
    """The report of one attack session, built from its RARF document."""
    problems = validate_rarf(rarf)
    if problems:
        raise ReportError("the RARF document is not valid: " + "; ".join(problems))
    if not rarf["timeline"]["events"] or not rarf["detection"]["correlation_groups"]:
        raise ReportError("the RARF document has no timeline events or no correlation groups")
    source = ReportSource(rarf)
    session_id = rarf["attack_session"]["session_id"]
    return {
        "report_title": f"Investigation Report: {session_id}",
        "attack_session_id": attack_session_id,
        "session_id": session_id,
        "generated_at": None,
        "sections": [
            {"section_id": section_id, "title": SECTION_TITLES[section_id], "findings": _BUILDERS[section_id](source)}
            for section_id in SECTION_IDS
        ],
    }


def report_text(report: dict[str, Any]) -> str:
    """The deterministic JSON text of a report (fixed key order, 2-space indent, ASCII, LF)."""
    return json.dumps(report, indent=2, ensure_ascii=True) + "\n"


def render_text(report: dict[str, Any]) -> str:
    """A plain-text rendering for reading in a terminal."""
    lines = [report["report_title"], ""]
    for section in report["sections"]:
        lines.append(f"== {section['title']} ==")
        for finding in section["findings"]:
            evidence = finding["evidence"]
            refs = f" [{len(evidence['event_ids'])} events, {len(evidence['correlation_group_ids'])} groups, {len(evidence['impact_analysis_ids'])} impact]"
            lines.append(f"[{finding['basis'].upper()}] {finding['statement']}{refs}")
        lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m raven.report.generator",
        description="Generate the report of an attack session from its RARF file.",
    )
    parser.add_argument("rarf_file")
    parser.add_argument("output_dir")
    parser.add_argument("--print", dest="print_text", action="store_true", help="also print the report as plain text")
    args = parser.parse_args(argv)
    try:
        rarf = json.loads(Path(args.rarf_file).read_text(encoding="utf-8"))
        report = generate_report(rarf)
        problems = validate_report(report, rarf)
        if problems:
            raise ReportError("the report is not valid: " + "; ".join(problems))
        path = Path(args.output_dir) / f"REPORT-{report['session_id']}.json"
        write_text_atomic(path, report_text(report))
    except (OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    findings = [finding for section in report["sections"] for finding in section["findings"]]
    print(f"file: {path}")
    print(f"  bytes:  {path.stat().st_size}")
    print(f"  sha256: {sha256_file(path)}")
    print(f"  report_title: {report['report_title']}")
    print(f"  generated_at: {report['generated_at']}")
    print("  validation: valid")
    print(f"  sections: {len(report['sections'])}, findings: {len(findings)}")
    for basis in ("observed", "derived"):
        print(f"  {basis} findings: {sum(1 for f in findings if f['basis'] == basis)}")
    if args.print_text:
        print()
        print(render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
