"""Analysis database schema: 7 tables (spec section 6.4).

One such database exists per investigation workspace (data/investigations/<id>/raven.db).

    events              the deduplicated normalized events (the 27 normalized fields plus an id)
    correlation_rules   rule definitions used by a run
    correlated_events   which events belong to which correlation group
    attack_sessions     reconstructed sessions (confidence stays null, decision D5)
    timeline_events     ordered events of a session with generated descriptions
    impact_analysis     observed counts and derived score per category
    reports             generated report text

Timestamps are stored as text in the format 2026-09-13T08:39:49.545Z (ISO-8601 UTC, milliseconds).
That format sorts correctly as text. JSON values are stored as text.
Only the events table is filled at stage S4; the other tables are created empty.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_timestamp", "timestamp"),
        Index("ix_events_type_process", "event_type", "process_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    raw_event_ref: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    event_id: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[str] = mapped_column(String, nullable=False)
    computer: Mapped[str] = mapped_column(String, nullable=False)
    process_guid: Mapped[str | None] = mapped_column(String)
    process_id: Mapped[int | None] = mapped_column(Integer)
    process_name: Mapped[str | None] = mapped_column(Text)
    parent_process_guid: Mapped[str | None] = mapped_column(String)
    parent_process_id: Mapped[int | None] = mapped_column(Integer)
    parent_process_name: Mapped[str | None] = mapped_column(Text)
    command_line: Mapped[str | None] = mapped_column(Text)
    parent_command_line: Mapped[str | None] = mapped_column(Text)
    user: Mapped[str | None] = mapped_column(String)
    integrity_level: Mapped[str | None] = mapped_column(String)
    hash_sha256: Mapped[str | None] = mapped_column(String)
    hash_md5: Mapped[str | None] = mapped_column(String)
    hash_imphash: Mapped[str | None] = mapped_column(String)
    hashes_raw: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(String)
    port: Mapped[int | None] = mapped_column(Integer)
    source_ip: Mapped[str | None] = mapped_column(String)
    source_port: Mapped[int | None] = mapped_column(Integer)
    protocol: Mapped[str | None] = mapped_column(String)
    initiated: Mapped[bool | None] = mapped_column(Boolean)
    file_path: Mapped[str | None] = mapped_column(Text)
    normalization_status: Mapped[str] = mapped_column(String, nullable=False)


class CorrelationRule(Base):
    __tablename__ = "correlation_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rule_name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    rule_definition: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class CorrelatedEvent(Base):
    __tablename__ = "correlated_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("correlation_rules.id"), nullable=False)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False)
    correlation_group_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    correlation_type: Mapped[str] = mapped_column(String, nullable=False)


class AttackSession(Base):
    __tablename__ = "attack_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    start_time: Mapped[str] = mapped_column(String, nullable=False)
    end_time: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str | None] = mapped_column(String)
    confidence: Mapped[int | None] = mapped_column(Integer)


class TimelineEvent(Base):
    __tablename__ = "timeline_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attack_session_id: Mapped[int] = mapped_column(ForeignKey("attack_sessions.id"), nullable=False)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    timeline_timestamp: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)


class ImpactAnalysis(Base):
    __tablename__ = "impact_analysis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attack_session_id: Mapped[int] = mapped_column(ForeignKey("attack_sessions.id"), nullable=False)
    impact_category: Mapped[str] = mapped_column(String, nullable=False)
    impact_score: Mapped[int] = mapped_column(Integer, nullable=False)
    affected_assets: Mapped[str] = mapped_column(Text, nullable=False)
    analysis: Mapped[str] = mapped_column(Text, nullable=False)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attack_session_id: Mapped[int] = mapped_column(ForeignKey("attack_sessions.id"), nullable=False)
    report_title: Mapped[str] = mapped_column(String, nullable=False)
    report_text: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[str | None] = mapped_column(String)


EXPECTED_TABLES: tuple[str, ...] = (
    "events",
    "correlation_rules",
    "correlated_events",
    "attack_sessions",
    "timeline_events",
    "impact_analysis",
    "reports",
)
