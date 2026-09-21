"""Creating and opening the SQLite database of one investigation workspace.

    session_factory = open_workspace_database(path_to_raven_db)

Creation is idempotent: opening a database that already exists changes nothing and keeps its data.
Foreign keys are enforced (SQLite needs that switched on for every connection).
Call engine.dispose() when a database is no longer needed (this matters on Windows, where an open
database file cannot be deleted).
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker

from raven.database.models import Base
from raven.database.registry_models import RegistryBase


def create_workspace_engine(db_path: str | os.PathLike[str]) -> Engine:
    """Create the engine for a database file. The folder is created when it does not exist."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(URL.create("sqlite", database=str(path)))

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def initialize_database(engine: Engine) -> None:
    """Create the 7 analysis tables when they are missing. Existing tables and data are left alone."""
    Base.metadata.create_all(engine)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def open_workspace_database(db_path: str | os.PathLike[str]) -> sessionmaker[Session]:
    """Create (if needed) and open the database at a path; return a session factory.

    The engine is available as session_factory.kw["bind"] for disposal.
    """
    engine = create_workspace_engine(db_path)
    initialize_database(engine)
    return create_session_factory(engine)


def initialize_registry(engine: Engine) -> None:
    """Create the 6 registry tables when they are missing. Existing tables and data are left alone."""
    RegistryBase.metadata.create_all(engine)


def open_registry_database(db_path: str | os.PathLike[str]) -> sessionmaker[Session]:
    """Create (if needed) and open the registry database at a path; return a session factory.

    The engine is available as session_factory.kw["bind"] for disposal.
    """
    engine = create_workspace_engine(db_path)
    initialize_registry(engine)
    return create_session_factory(engine)
