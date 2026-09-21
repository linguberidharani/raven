"""Application settings (typed, from environment variables and the .env file).

Every setting has the prefix RAVEN_ (for example RAVEN_PORT=8000). The .env file in the project root is read
when it exists; real environment variables win over it. No secrets live here: passwords are stored hashed and
sessions use random server-side tokens.

Relative paths (RAVEN_DATA_DIR) are resolved against the project root, never against the current folder, so the
server finds the same data folder wherever it is started from.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RAVEN_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Literal["development", "production", "test"] = "development"
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    data_dir: Path = Path("data")
    log_level: LogLevel = "INFO"
    max_upload_mb: int = Field(default=200, ge=1, le=10_000)
    session_hours: int = Field(default=12, ge=1, le=24 * 30)
    cookie_secure: bool = False
    inbox_dir: Path = Path("data/inbox")
    inbox_poll_seconds: int = Field(default=5, ge=0, le=3600)

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_case_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @field_validator("host")
    @classmethod
    def _local_host_only(cls, value: str) -> str:
        if value not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("RAVEN_HOST must be a loopback address (the server is local only)")
        return value

    @property
    def resolved_data_dir(self) -> Path:
        path = self.data_dir
        return path if path.is_absolute() else PROJECT_ROOT / path

    @property
    def resolved_inbox_dir(self) -> Path:
        path = self.inbox_dir
        return path if path.is_absolute() else PROJECT_ROOT / path

    @property
    def registry_path(self) -> Path:
        return self.resolved_data_dir / "registry.db"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def docs_enabled(self) -> bool:
        return self.env == "development"


@lru_cache
def get_settings() -> Settings:
    """The settings of this process (read once)."""
    return Settings()
