"""Registry database schema: 6 tables (spec section 6.5).

One registry database (data/registry.db) holds the accounts, the sessions and the list of investigations with
their evidence and analysis runs. The analysis data of an investigation lives in its own workspace database
(see models.py). Timestamps are text in the format 2026-09-13T08:39:49.545Z.

    users              accounts (email unique, Argon2 password hash, never a plain password)
    sessions           server-side login sessions (the SHA-256 hash of the cookie token, never the token)
    investigations     cases (code INV-YYYY-NNN, status, analyst, workspace folder)
    evidence_sources   uploaded or collected evidence files of a case
    analysis_runs      runs of the processing pipeline with per-stage status
    collector_cursors  read positions in the VM collector files
    password_reset_tokens  single-use, time-limited tokens emailed to reset a forgotten password

Only users and sessions are used from stage S11; the other tables are created for the stages that follow.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class RegistryBase(DeclarativeBase):
    pass


class User(RegistryBase):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    organization: Mapped[str | None] = mapped_column(String)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)


class UserSession(RegistryBase):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[str] = mapped_column(String, nullable=False)


class PasswordResetToken(RegistryBase):
    """A password reset link. Only the SHA-256 hash of the token is stored, the same as a session token."""

    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[str] = mapped_column(String, nullable=False)
    used_at: Mapped[str | None] = mapped_column(String)


class Investigation(RegistryBase):
    __tablename__ = "investigations"
    __table_args__ = (CheckConstraint("status IN ('open', 'active', 'closed')", name="ck_investigations_status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    host: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, nullable=False, default="open")
    analyst_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)
    workspace_dir: Mapped[str] = mapped_column(String, nullable=False)


class EvidenceSource(RegistryBase):
    __tablename__ = "evidence_sources"
    __table_args__ = (
        CheckConstraint("source_type IN ('evtx_upload', 'vm_collector')", name="ck_evidence_sources_type"),
        CheckConstraint("status IN ('uploaded', 'processing', 'ready', 'failed')", name="ck_evidence_sources_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    investigation_id: Mapped[int] = mapped_column(ForeignKey("investigations.id"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    sha256: Mapped[str] = mapped_column(String, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="uploaded")
    events_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    ingested_at: Mapped[str | None] = mapped_column(String)


class AnalysisRun(RegistryBase):
    __tablename__ = "analysis_runs"
    __table_args__ = (CheckConstraint("status IN ('queued', 'running', 'completed', 'failed')", name="ck_analysis_runs_status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    investigation_id: Mapped[int] = mapped_column(ForeignKey("investigations.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="queued")
    stage: Mapped[str | None] = mapped_column(String)
    stages_json: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[str | None] = mapped_column(String)
    finished_at: Mapped[str | None] = mapped_column(String)


class CollectorCursor(RegistryBase):
    __tablename__ = "collector_cursors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    investigation_id: Mapped[int] = mapped_column(ForeignKey("investigations.id"), nullable=False, index=True)
    source_name: Mapped[str] = mapped_column(String, nullable=False)
    last_offset: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_record_id: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


REGISTRY_TABLES: tuple[str, ...] = (
    "users",
    "sessions",
    "investigations",
    "evidence_sources",
    "analysis_runs",
    "collector_cursors",
    "password_reset_tokens",
)
