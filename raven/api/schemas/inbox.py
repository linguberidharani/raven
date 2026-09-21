"""Request and response shapes of the inbox and collector endpoints (see docs/api-contract.md)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator

from raven.collectors.inbox import valid_source_name


class InboxFileOut(BaseModel):
    source_name: str
    size_bytes: int
    modified_at: str
    investigation_id: int | None
    investigation_code: str | None


class InboxListOut(BaseModel):
    items: list[InboxFileOut]


class LinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_name: str

    @field_validator("source_name")
    @classmethod
    def _name(cls, value: str) -> str:
        if not valid_source_name(value):
            raise ValueError("source_name must be a plain file name ending in .jsonl (letters, digits, dot, underscore, dash)")
        return value


class CollectorSourceOut(BaseModel):
    source_name: str
    evidence_id: int
    last_offset: int
    last_record_id: int | None
    updated_at: str
    status: str
    events_total: int
    error: str | None


class CollectorListOut(BaseModel):
    items: list[CollectorSourceOut]


class SourceResultOut(BaseModel):
    source_name: str
    investigation_id: int
    records_added: int
    rejected: int
    offset: int
    error: str | None
    skipped: str | None


class PollOut(BaseModel):
    results: list[SourceResultOut]
    analyses_started: list[int]
