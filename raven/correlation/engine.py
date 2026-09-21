"""Correlation engine (spec sections 6.6 and 7). Pure code: no database, no files.

For every rule and every value of the rule's match key (for example one process ID), the events
of that value are put in time order. A rule matches when its steps are found, in order, with at
least min_count events each, inside the rule's time window. Every match is a correlation group:

    group ID = "{rule_id}:{match_key_value}:{window_start}"      window_start = timestamp of the
                                                                  event that opened the window

Everything is deterministic: same events and same rules always give the same groups.

The spec fixes the ID format, the steps, the window and the match key, but leaves open a few details
of how a window is searched. EngineOptions makes each of them explicit:

    step_order      strict: the events of each step come after the events of the step before it
                    loose:  the steps only need their counts inside the window, in any order
    group_policy    first:         one group per key value (the first match)
                    skip_window:   after a match, continue with the first event after that window
                    skip_matched:  after a match, continue with the event after its last matched event
                    all:           every event that opens a match starts a group (windows overlap)
    membership      minimal: the group holds exactly the matched events (min_count per step)
                    window:  the group holds every event of the rule's step types inside the window
    inclusive_window  an event exactly time_window_seconds after the window start is inside (True)
                    or outside (False)

The defaults are the settings that reproduce the reference numbers of the spec (see explore.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from raven.correlation.rule_schema import Rule
from raven.parsers.time_utils import parse_timestamp

STEP_ORDERS = ("strict", "loose")
GROUP_POLICIES = ("first", "skip_window", "skip_matched", "all")
MEMBERSHIPS = ("minimal", "window")

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def timestamp_to_ms(timestamp: str) -> int:
    """Milliseconds since 1970-01-01 UTC of a timestamp such as 2026-09-13T08:39:49.695Z."""
    return (parse_timestamp(timestamp) - _EPOCH) // timedelta(milliseconds=1)


@dataclass(frozen=True)
class EngineOptions:
    step_order: str = "strict"
    group_policy: str = "skip_window"
    membership: str = "minimal"
    inclusive_window: bool = True

    def __post_init__(self) -> None:
        if self.step_order not in STEP_ORDERS:
            raise ValueError("step_order must be one of " + ", ".join(STEP_ORDERS))
        if self.group_policy not in GROUP_POLICIES:
            raise ValueError("group_policy must be one of " + ", ".join(GROUP_POLICIES))
        if self.membership not in MEMBERSHIPS:
            raise ValueError("membership must be one of " + ", ".join(MEMBERSHIPS))

    def label(self) -> str:
        return f"{self.step_order}/{self.group_policy}/{self.membership}/{'inclusive' if self.inclusive_window else 'exclusive'}"


@dataclass(frozen=True)
class EventPoint:
    """The few fields of an event that the engine needs."""

    row_id: int
    raw_event_ref: str
    event_type: str
    timestamp: str
    time_ms: int
    process_id: int | None
    process_guid: str | None

    @classmethod
    def create(
        cls,
        row_id: int,
        raw_event_ref: str,
        event_type: str,
        timestamp: str,
        process_id: int | None = None,
        process_guid: str | None = None,
    ) -> "EventPoint":
        return cls(row_id, raw_event_ref, event_type, timestamp, timestamp_to_ms(timestamp), process_id, process_guid)


@dataclass(frozen=True)
class Group:
    group_id: str
    rule_id: str
    match_key: str
    match_value: str
    window_start: str
    window_end: str
    event_row_ids: tuple[int, ...]
    step_counts: tuple[int, ...]


def _sorted_events(events: list[EventPoint]) -> list[EventPoint]:
    return sorted(events, key=lambda e: (e.time_ms, e.row_id))


def _match_from(rule: Rule, evs: list[EventPoint], anchor: int, options: EngineOptions) -> list[int] | None:
    """Try to match the rule with the window opened by evs[anchor]. Return the matched indexes or None."""
    limit = evs[anchor].time_ms + rule.window_ms
    end = anchor
    while end < len(evs) and (evs[end].time_ms <= limit if options.inclusive_window else evs[end].time_ms < limit):
        end += 1
    window = list(range(anchor, end))

    matched: list[int] = []
    if options.step_order == "strict":
        position = 0
        for step in rule.steps:
            picked: list[int] = []
            k = position
            while k < len(window) and len(picked) < step.min_count:
                if evs[window[k]].event_type == step.event_type:
                    picked.append(window[k])
                k += 1
            if len(picked) < step.min_count:
                return None
            matched.extend(picked)
            position = k
    else:
        used: set[int] = set()
        for step in rule.steps:
            picked = [i for i in window if evs[i].event_type == step.event_type and i not in used][: step.min_count]
            if len(picked) < step.min_count:
                return None
            used.update(picked)
            matched.extend(picked)

    if options.membership == "window":
        types = {step.event_type for step in rule.steps}
        return [i for i in window if evs[i].event_type in types]
    return sorted(matched)


def find_groups(rule: Rule, events: list[EventPoint], options: EngineOptions = EngineOptions()) -> list[Group]:
    """All correlation groups of one rule, ordered by window start, then match value."""
    by_key: dict[Any, list[EventPoint]] = {}
    for event in events:
        value = getattr(event, rule.match_key)
        if value is not None:
            by_key.setdefault(value, []).append(event)

    anchor_type = rule.steps[0].event_type
    groups: list[Group] = []
    for value in sorted(by_key):
        evs = _sorted_events(by_key[value])
        seen_ids: set[str] = set()
        i = 0
        while i < len(evs):
            if evs[i].event_type != anchor_type:
                i += 1
                continue
            matched = _match_from(rule, evs, i, options)
            if matched is None:
                i += 1
                continue
            start = evs[i].timestamp
            group_id = f"{rule.rule_id}:{value}:{start}"
            if group_id not in seen_ids:
                seen_ids.add(group_id)
                members = [evs[k] for k in matched]
                groups.append(
                    Group(
                        group_id=group_id,
                        rule_id=rule.rule_id,
                        match_key=rule.match_key,
                        match_value=str(value),
                        window_start=start,
                        window_end=members[-1].timestamp,
                        event_row_ids=tuple(m.row_id for m in members),
                        step_counts=tuple(sum(1 for m in members if m.event_type == s.event_type) for s in rule.steps),
                    )
                )
            if options.group_policy == "first":
                break
            if options.group_policy == "skip_matched":
                i = max(matched) + 1
            elif options.group_policy == "skip_window":
                limit = evs[i].time_ms + rule.window_ms
                i += 1
                while i < len(evs) and (evs[i].time_ms <= limit if options.inclusive_window else evs[i].time_ms < limit):
                    i += 1
            else:
                i += 1
    groups.sort(key=lambda g: (g.window_start, g.match_value, g.group_id))
    return groups


def find_all_groups(rules: list[Rule], events: list[EventPoint], options: EngineOptions = EngineOptions()) -> list[Group]:
    """The groups of every rule, in rule order."""
    groups: list[Group] = []
    for rule in rules:
        groups.extend(find_groups(rule, events, options))
    return groups


def explain_group(rule: Rule, group: Group, events_by_row_id: dict[int, EventPoint]) -> dict[str, Any]:
    """Why a group matched: the rule, the steps with required and found counts, the window and the events."""
    members = [events_by_row_id[row_id] for row_id in group.event_row_ids]
    return {
        "group_id": group.group_id,
        "rule_id": rule.rule_id,
        "rule_name": rule.rule_name,
        "severity": rule.severity,
        "confidence": rule.confidence,
        "match_key": group.match_key,
        "match_value": group.match_value,
        "time_window_seconds": rule.time_window_seconds,
        "window_start": group.window_start,
        "window_end": group.window_end,
        "steps": [
            {"event_type": step.event_type, "required": step.min_count, "found": found}
            for step, found in zip(rule.steps, group.step_counts)
        ],
        "event_count": len(members),
        "event_refs": [member.raw_event_ref for member in members],
    }
