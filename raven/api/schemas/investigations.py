"""Request and response shapes of the investigation, evidence and analysis endpoints (see docs/api-contract.md)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from raven.services.investigations import validate_description, validate_host, validate_status, validate_title


class InvestigationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    description: str | None = None
    host: str | None = None

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        return validate_title(value)

    @field_validator("description")
    @classmethod
    def _description(cls, value: str | None) -> str | None:
        return validate_description(value)

    @field_validator("host")
    @classmethod
    def _host(cls, value: str | None) -> str | None:
        return validate_host(value)


class InvestigationUpdate(BaseModel):
    """Only the fields that are sent are changed (send null to clear description or host)."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    description: str | None = None
    host: str | None = None
    status: str | None = None

    @field_validator("title")
    @classmethod
    def _title(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("title cannot be cleared")
        return validate_title(value)

    @field_validator("description")
    @classmethod
    def _description(cls, value: str | None) -> str | None:
        return validate_description(value)

    @field_validator("host")
    @classmethod
    def _host(cls, value: str | None) -> str | None:
        return validate_host(value)

    @field_validator("status")
    @classmethod
    def _status(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("status cannot be cleared")
        return validate_status(value)


class AnalystOut(BaseModel):
    id: int
    name: str


class CountsOut(BaseModel):
    evidence: int
    detections: int
    sessions: int
    timeline_events: int


class InvestigationOut(BaseModel):
    id: int
    code: str
    title: str
    description: str | None
    host: str | None
    status: str
    severity: str | None
    stage: str | None
    analysis_status: str | None
    analyst: AnalystOut
    counts: CountsOut
    created_at: str
    updated_at: str


class InvestigationPage(BaseModel):
    items: list[InvestigationOut]
    total: int
    page: int
    page_size: int


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    investigation_id: int
    filename: str
    sha256: str
    size_bytes: int
    source_type: str
    status: str
    events_total: int
    error: str | None
    created_at: str
    ingested_at: str | None


class EventCountOut(BaseModel):
    event_id: int
    event_type: str
    count: int


class EvidenceListOut(BaseModel):
    items: list[EvidenceOut]
    event_breakdown: list[EventCountOut]


class StageOut(BaseModel):
    name: str
    status: str
    started_at: str | None
    finished_at: str | None
    summary: dict[str, Any] | None
    error: str | None


class AnalysisRunOut(BaseModel):
    id: int
    investigation_id: int
    status: str
    stage: str | None
    stages: list[StageOut]
    error: str | None
    started_at: str | None
    finished_at: str | None
