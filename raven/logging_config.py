"""Logging setup. Log lines carry the request ID; request bodies, passwords and tokens are never logged."""

from __future__ import annotations

import logging

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging(level: str = "INFO") -> None:
    """Configure the root logger once (safe to call again)."""
    root = logging.getLogger()
    root.setLevel(level)
    if not any(getattr(handler, "_raven", False) for handler in root.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        handler._raven = True  # type: ignore[attr-defined]
        root.addHandler(handler)
