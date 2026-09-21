"""Attack reconstruction: merge correlation groups into attack sessions (spec section 6.7). Pure code.

Groups are merged per computer. They are sorted by start time (then group ID); a group whose start is
within merge_gap_seconds (default 300) of the current session end joins that session, otherwise it starts
a new session. The session end is the latest end of its groups.

    session ID  = RAVEN-SESSION-{computer}-{first group ID}   (in both parts every character that is not a
                                                                 letter or digit becomes "-")
    severity    = the highest severity among the member groups (HIGH > MEDIUM > LOW > INFO)
    confidence  = null (decision D5: no unsupported claim)
    description = "Reconstructed attack session containing N correlation group(s) from rule(s): ..."

A session is DERIVED information: it is a way of grouping detections in time, not a finding about intent.
The same groups always give the same sessions and the same IDs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

SEVERITY_ORDER = ("INFO", "LOW", "MEDIUM", "HIGH")  # lowest to highest
DEFAULT_MERGE_GAP_SECONDS = 300

_NON_ALPHANUMERIC = re.compile(r"[^A-Za-z0-9]")


class ReconstructionError(ValueError):
    """The groups cannot be turned into sessions."""


@dataclass(frozen=True)
class GroupInfo:
    """What the sequencer needs to know about one correlation group."""

    group_id: str
    rule_id: str
    severity: str
    computer: str
    start_time: str
    end_time: str
    start_ms: int
    end_ms: int
    event_count: int


@dataclass(frozen=True)
class SessionPlan:
    session_id: str
    computer: str
    start_time: str
    end_time: str
    severity: str
    confidence: None
    description: str
    groups: tuple[GroupInfo, ...]

    @property
    def rule_ids(self) -> tuple[str, ...]:
        return tuple(sorted({group.rule_id for group in self.groups}))


def sanitize_id_part(text: str) -> str:
    """Replace every character that is not a letter or a digit with "-"."""
    return _NON_ALPHANUMERIC.sub("-", text)


def highest_severity(severities: list[str]) -> str:
    unknown = [s for s in severities if s not in SEVERITY_ORDER]
    if unknown:
        raise ReconstructionError("unknown severity: " + ", ".join(sorted(set(unknown))))
    return max(severities, key=SEVERITY_ORDER.index)


def describe(groups: tuple[GroupInfo, ...]) -> str:
    rules = ", ".join(sorted({group.rule_id for group in groups}))
    return f"Reconstructed attack session containing {len(groups)} correlation group(s) from rule(s): {rules}."


def _plan(computer: str, groups: list[GroupInfo]) -> SessionPlan:
    members = tuple(groups)  # already in start order
    latest = max(members, key=lambda group: group.end_ms)
    return SessionPlan(
        session_id=f"RAVEN-SESSION-{sanitize_id_part(computer)}-{sanitize_id_part(members[0].group_id)}",
        computer=computer,
        start_time=members[0].start_time,
        end_time=latest.end_time,
        severity=highest_severity([group.severity for group in members]),
        confidence=None,
        description=describe(members),
        groups=members,
    )


def build_sessions(groups: list[GroupInfo], merge_gap_seconds: int = DEFAULT_MERGE_GAP_SECONDS) -> list[SessionPlan]:
    """Merge groups into sessions. Sessions are returned in order of start time, then session ID."""
    if isinstance(merge_gap_seconds, bool) or not isinstance(merge_gap_seconds, int) or merge_gap_seconds < 0:
        raise ReconstructionError("merge_gap_seconds must be a whole number of at least 0")
    gap_ms = merge_gap_seconds * 1000

    by_computer: dict[str, list[GroupInfo]] = {}
    for group in groups:
        by_computer.setdefault(group.computer, []).append(group)

    plans: list[SessionPlan] = []
    for computer in sorted(by_computer):
        ordered = sorted(by_computer[computer], key=lambda group: (group.start_ms, group.group_id))
        current: list[GroupInfo] = []
        session_end = 0
        for group in ordered:
            if current and group.start_ms - session_end <= gap_ms:
                current.append(group)
                session_end = max(session_end, group.end_ms)
            else:
                if current:
                    plans.append(_plan(computer, current))
                current = [group]
                session_end = group.end_ms
        if current:
            plans.append(_plan(computer, current))
    plans.sort(key=lambda plan: (plan.start_time, plan.session_id))
    return plans
