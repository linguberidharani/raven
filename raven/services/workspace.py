"""The workspace of one investigation (spec sections 1 and 5, decision D1).

    <data dir>/investigations/<id>/
        evidence/     uploaded EVTX files, stored as <evidence id>.evtx (the uploaded name is never a file name)
        raw/          raw JSONL of each evidence file
        processed/    normalized, deduplicated and summary files, RARF and report files
        raven.db      the analysis database of this investigation

Every path is built from numeric IDs. A workspace path stored in the registry is checked to lie inside the
investigations folder before it is used, so a damaged or tampered registry cannot point outside it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from raven.database.session import open_workspace_database
from raven.services.errors import ServiceError

INVESTIGATIONS_FOLDER = "investigations"


@dataclass(frozen=True)
class Workspace:
    root: Path

    @property
    def evidence_dir(self) -> Path:
        return self.root / "evidence"

    @property
    def raw_dir(self) -> Path:
        return self.root / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.root / "processed"

    @property
    def db_path(self) -> Path:
        return self.root / "raven.db"

    @property
    def rarf_dir(self) -> Path:
        return self.processed_dir / "rarf"

    @property
    def report_dir(self) -> Path:
        return self.processed_dir / "report"

    def evidence_path(self, evidence_id: int) -> Path:
        return self.evidence_dir / f"{int(evidence_id)}.evtx"

    def raw_path(self, evidence_id: int) -> Path:
        return self.raw_dir / f"evidence-{int(evidence_id)}.jsonl"

    def normalized_path(self, evidence_id: int) -> Path:
        return self.processed_dir / f"evidence-{int(evidence_id)}.normalized.jsonl"

    @property
    def combined_normalized_path(self) -> Path:
        return self.processed_dir / "normalized.jsonl"

    @property
    def deduplicated_path(self) -> Path:
        return self.processed_dir / "deduplicated.jsonl"

    @property
    def duplicates_path(self) -> Path:
        return self.processed_dir / "duplicates.jsonl"

    def summary_path(self, name: str) -> Path:
        return self.processed_dir / f"{name}.json"

    def ensure(self) -> "Workspace":
        for folder in (self.evidence_dir, self.raw_dir, self.processed_dir):
            folder.mkdir(parents=True, exist_ok=True)
        return self

    def open_database(self) -> sessionmaker[Session]:
        return open_workspace_database(self.db_path)


def workspace_dir_name(investigation_id: int) -> str:
    """The workspace folder as stored in the registry (relative to the data folder, forward slashes)."""
    if isinstance(investigation_id, bool) or not isinstance(investigation_id, int) or investigation_id < 1:
        raise ValueError("investigation IDs are positive whole numbers")
    return f"{INVESTIGATIONS_FOLDER}/{investigation_id}"


def resolve_workspace(data_dir: Path, stored: str) -> Workspace:
    """The workspace for a stored folder name. It must lie inside <data dir>/investigations."""
    base = (data_dir / INVESTIGATIONS_FOLDER).resolve()
    candidate = (data_dir / stored).resolve()
    if candidate == base or base not in candidate.parents:
        raise ServiceError(500, "workspace_invalid", "The workspace of this investigation is not valid.")
    return Workspace(candidate)
