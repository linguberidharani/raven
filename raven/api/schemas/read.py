"""Response shapes of the read endpoints (stage S13). They are documented in docs/api-contract.md and enforced by tests."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from raven.api.schemas.investigations import InvestigationOut


class EvidenceRefs(BaseModel):
    event_ids: list[int]
    raw_event_refs: list[str]


class StepOut(BaseModel):
    event_type: str
    min_count: int


class StepFound(BaseModel):
    event_type: str
    required: int
    found: int


class Why(BaseModel):
    basis: str
    text: str
    steps: list[StepFound]


class Interpretation(BaseModel):
    basis: str
    text: str


class GroupOut(BaseModel):
    group_id: str
    rule_id: str
    rule_name: str
    severity: str
    confidence: int
    match_key: str
    match_value: str
    time_window_seconds: int
    window_start: str
    window_end: str
    event_count: int
    why: Why
    interpretation: Interpretation
    evidence: EvidenceRefs


class RuleOut(BaseModel):
    rule_id: str
    rule_name: str
    description: str
    severity: str
    confidence: int
    match_key: str
    time_window_seconds: int
    steps: list[StepOut]
    enabled: bool
    groups: int


class DetectionCounts(BaseModel):
    total_groups: int
    by_rule: dict[str, int]
    by_severity: dict[str, int]


class DetectionsOut(BaseModel):
    analysed: bool
    rules: list[RuleOut]
    counts: DetectionCounts
    groups: list[GroupOut]
    total: int
    page: int
    page_size: int


class ShippedRuleOut(BaseModel):
    rule_id: str
    rule_name: str
    description: str
    steps: list[StepOut]
    match_key: str
    time_window_seconds: int
    severity: str
    confidence: int


class RulesOut(BaseModel):
    rules: list[ShippedRuleOut]


# ---------------------------------------------------------------------------- reconstruction


class ChainEvent(BaseModel):
    event_id: int
    raw_event_ref: str
    timestamp: str
    event_type: str
    description: str


class ChainGroup(BaseModel):
    group_id: str
    rule_id: str
    rule_name: str
    severity: str
    match_value: str
    start_time: str
    end_time: str
    event_count: int
    events: list[ChainEvent]
    interpretation: Interpretation


class ProcessNode(BaseModel):
    process_guid: str
    process_id: int | None
    image: str | None
    user: str | None
    parent_process_guid: str | None
    parent_process_id: int | None
    parent_image: str | None
    first_seen: str | None
    last_seen: str | None
    event_counts: dict[str, int]
    group_ids: list[str]
    in_session: bool
    basis: str
    child_guids: list[str]


class ProcessTree(BaseModel):
    nodes: list[ProcessNode]
    roots: list[str]


class ReconstructedSession(BaseModel):
    session_id: str
    computer: str | None
    start_time: str
    end_time: str
    duration_ms: int
    severity: str | None
    confidence: int | None
    description: str | None
    group_count: int
    rule_ids: list[str]
    chain: list[ChainGroup]
    process_tree: ProcessTree


class ReconstructionOut(BaseModel):
    sessions: list[ReconstructedSession]


# ---------------------------------------------------------------------------- timeline and events


class GroupRef(BaseModel):
    group_id: str
    rule_id: str
    basis: str


class TimelineItem(BaseModel):
    timeline_event_id: int
    session_id: str
    sequence_number: int
    timestamp: str
    description: str
    computer: str
    event_type: str
    event_id: int
    sysmon_event_id: int
    raw_event_ref: str
    basis: str
    groups: list[GroupRef]


class TimelinePage(BaseModel):
    items: list[TimelineItem]
    total: int
    page: int
    page_size: int


class RawOut(BaseModel):
    event_id: int
    time_created: str
    computer: str
    record_id: int
    event_data: dict[str, Any]


class TimelineRef(BaseModel):
    session_id: str
    sequence_number: int
    description: str


class EventDetailOut(BaseModel):
    raw_event_ref: str
    event: dict[str, Any]
    raw: RawOut
    raw_xml: str
    groups: list[GroupRef]
    timeline: TimelineRef | None


# ---------------------------------------------------------------------------- impact


class TopAsset(BaseModel):
    asset: str
    events: int


class ObservedImpact(BaseModel):
    basis: str
    event_count: int
    affected_assets: list[str]
    top_assets: list[TopAsset]
    details: dict[str, Any]


class DerivedImpact(BaseModel):
    basis: str
    impact_score: int
    definition: str


class ImpactCategory(BaseModel):
    category: str
    impact_analysis_id: int
    observed: ObservedImpact
    derived: DerivedImpact
    evidence: EvidenceRefs


class ActivityBucket(BaseModel):
    start: str
    file_create: int
    network_connection: int
    process_creation: int
    total: int


class ImpactActivity(BaseModel):
    basis: str
    bucket_seconds: int
    buckets: list[ActivityBucket]


class ImpactSessionOut(BaseModel):
    session_id: str
    categories: list[ImpactCategory]
    activity: ImpactActivity


class ImpactOut(BaseModel):
    sessions: list[ImpactSessionOut]


# ---------------------------------------------------------------------------- dashboard


class DashboardTotals(BaseModel):
    investigations: int
    active_investigations: int
    open_cases: int
    evidence_items: int
    sessions: int
    high_severity_findings: int


class ChainStep(BaseModel):
    rule_id: str
    rule_name: str
    severity: str
    groups: int
    first_start: str


class LatestSession(BaseModel):
    investigation_id: int
    code: str
    session_id: str
    start_time: str
    end_time: str
    severity: str | None
    chain: list[ChainStep]


class AlertOut(BaseModel):
    investigation_id: int
    code: str
    group_id: str
    rule_id: str
    rule_name: str
    severity: str
    window_start: str
    event_count: int


class ActivityItem(BaseModel):
    time: str
    kind: str
    investigation_id: int
    code: str | None
    text: str


class QueueItem(BaseModel):
    id: int
    investigation_id: int
    code: str | None
    filename: str
    status: str
    size_bytes: int
    error: str | None
    created_at: str


class DashboardOut(BaseModel):
    totals: DashboardTotals
    cases_by_severity: dict[str, int]
    cases_by_status: dict[str, int]
    findings_by_severity: dict[str, int]
    evidence_by_status: dict[str, int]
    recent_investigations: list[InvestigationOut]
    latest_session: LatestSession | None
    alerts: list[AlertOut]
    recent_activity: list[ActivityItem]
    evidence_queue: list[QueueItem]
