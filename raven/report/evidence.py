"""Evidence extractor for the report (spec section 6.11). Pure code.

The report is built from the RARF document only. ReportSource reads a RARF document once and answers the
questions the generator asks: counts, times, groups of a rule, impact of a category, and, for every
statement, the exact evidence references (event IDs, raw event references, correlation group IDs, timeline
event IDs and impact analysis IDs) that the statement rests on.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from raven.correlation.engine import timestamp_to_ms


def format_duration(milliseconds: int) -> str:
    """For example 199943 -> "3 min 19.943 s"."""
    total_seconds, millis = divmod(milliseconds, 1000)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    seconds_text = f"{seconds}.{millis:03d}"
    if hours:
        return f"{hours} h {minutes} min {seconds_text} s"
    if minutes:
        return f"{minutes} min {seconds_text} s"
    return f"{seconds_text} s"


def group_match_value(group_id: str) -> str:
    """The match value of a correlation group ID {rule_id}:{value}:{window_start}."""
    parts = group_id.split(":", 2)
    return parts[1] if len(parts) == 3 else ""


class ReportSource:
    """Facts and evidence references read from one RARF document."""

    def __init__(self, rarf: dict[str, Any]) -> None:
        self.rarf = rarf
        self.session: dict[str, Any] = rarf["attack_session"]
        self.timeline: list[dict[str, Any]] = rarf["timeline"]["events"]
        self.groups: list[dict[str, Any]] = rarf["detection"]["correlation_groups"]
        self.rules: list[dict[str, Any]] = rarf["detection"]["rules"]
        self.categories: dict[str, Any] = rarf["impact"]["categories"]
        self.traceability: dict[str, Any] = rarf["traceability"]
        self.by_event = {entry["event_id"]: entry for entry in self.timeline}

    # ------------------------------------------------------------------ evidence references

    def evidence(
        self,
        event_ids: Any = (),
        group_ids: Any = (),
        impact_ids: Any = (),
    ) -> dict[str, list[Any]]:
        """The evidence object of a statement, in the fixed key order of the spec."""
        events = sorted(set(event_ids))
        groups: list[str] = []
        for group_id in group_ids:
            if group_id not in groups:
                groups.append(group_id)
        return {
            "event_ids": events,
            "correlation_group_ids": groups,
            "timeline_event_ids": sorted(self.by_event[event_id]["timeline_event_id"] for event_id in events),
            "impact_analysis_ids": sorted(set(impact_ids)),
            "raw_event_refs": [self.by_event[event_id]["raw_event_ref"] for event_id in events],
        }

    def all_events(self) -> list[int]:
        return list(self.traceability["event_ids"])

    # ------------------------------------------------------------------ counts and times

    @property
    def event_count(self) -> int:
        return len(self.timeline)

    @property
    def first_timestamp(self) -> str:
        return self.timeline[0]["timestamp"]

    @property
    def last_timestamp(self) -> str:
        return self.timeline[-1]["timestamp"]

    def duration_ms(self) -> int:
        return timestamp_to_ms(self.last_timestamp) - timestamp_to_ms(self.first_timestamp)

    def events_of_type(self, event_type: str) -> list[dict[str, Any]]:
        return [entry for entry in self.timeline if entry["event_type"] == event_type]

    def events_per_minute(self) -> list[tuple[str, int]]:
        counts = Counter(entry["timestamp"][:16] for entry in self.timeline)
        return sorted(counts.items())

    def busiest_minute(self) -> tuple[str, int]:
        minutes = self.events_per_minute()
        return max(minutes, key=lambda item: (item[1], -minutes.index(item)))

    # ------------------------------------------------------------------ groups and rules

    def group_span(self, group: dict[str, Any]) -> tuple[str, str]:
        stamps = sorted(self.by_event[event_id]["timestamp"] for event_id in group["event_ids"])
        return stamps[0], stamps[-1]

    def ordered_groups(self) -> list[dict[str, Any]]:
        return sorted(self.groups, key=lambda group: (self.group_span(group)[0], group["correlation_group_id"]))

    def groups_of_rule(self, rule_id: str) -> list[dict[str, Any]]:
        return [group for group in self.groups if group["correlation_type"] == rule_id]

    def events_of_groups(self, groups: list[dict[str, Any]]) -> list[int]:
        return sorted({event_id for group in groups for event_id in group["event_ids"]})

    def group_event_entries(self) -> int:
        return sum(len(group["event_ids"]) for group in self.groups)

    # ------------------------------------------------------------------ impact

    def category(self, name: str) -> dict[str, Any]:
        return self.categories[name]
