"""The RAVEN API application (spec section 8).

    create_app(settings=None, password_hasher=None) -> FastAPI

Conventions: all routes under /api (plus the legacy /health); JSON with snake_case names; every response has an
X-Request-ID header; every error is {"detail", "code", "request_id"}; every route except health, register and
login needs a signed-in user (session cookie). The server binds to 127.0.0.1 only (see scripts/run_backend.ps1).

Start it with:  python -m uvicorn raven.api.main:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from argon2 import PasswordHasher
from fastapi import FastAPI, Request
from starlette.responses import Response

import raven
from raven.api.errors import REQUEST_ID_HEADER, error_response, install_error_handlers
from raven.api.routes import auth as auth_routes
from raven.api.routes import health as health_routes
from raven.api.routes import inbox as inbox_routes
from raven.api.routes import investigations as investigation_routes
from raven.api.routes import read as read_routes
from raven.config import Settings, get_settings
from raven.database.session import open_registry_database
from raven.logging_config import configure_logging
from raven.services.analysis_runs import AnalysisRunManager
from raven.services.auth import AuthService
from raven.services.inbox import InboxWatcher
from raven.services.mailer import Mailer
from raven.services.password_reset import PasswordResetService

logger = logging.getLogger("raven.api")

_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_BODY_ALLOWANCE = 1024 * 1024  # room for the multipart framing around an upload


def create_app(
    settings: Settings | None = None,
    password_hasher: PasswordHasher | None = None,
    mailer: Mailer | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    registry_factory = open_registry_database(settings.registry_path)

    hasher = password_hasher or PasswordHasher()
    mailer = mailer or Mailer(settings)
    runs = AnalysisRunManager(registry_factory, settings)
    watcher = InboxWatcher(registry_factory, settings, runs)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        interrupted = runs.recover_interrupted()
        if interrupted:
            logger.warning("%s analysis run(s) were interrupted by the last shutdown and are marked failed", interrupted)
        watcher.start()
        yield
        watcher.stop()
        registry_factory.kw["bind"].dispose()

    app = FastAPI(
        title="RAVEN API",
        version=raven.__version__,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.registry_factory = registry_factory
    app.state.auth = AuthService(hasher, settings.session_hours)
    app.state.mailer = mailer
    app.state.password_reset = PasswordResetService(
        mailer,
        hasher,
        hours=settings.password_reset_hours,
        base_url=settings.frontend_base_url,
    )
    app.state.runs = runs
    app.state.inbox = watcher

    @app.middleware("http")
    async def request_context(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        supplied = request.headers.get(REQUEST_ID_HEADER, "")
        request.state.request_id = supplied if _REQUEST_ID.match(supplied) else uuid.uuid4().hex
        started = time.perf_counter()
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > settings.max_upload_bytes + _BODY_ALLOWANCE:
            response = error_response(request, 413, "payload_too_large", f"The request is larger than {settings.max_upload_mb} MB.")
            response.headers["X-Content-Type-Options"] = "nosniff"
            return response
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        logger.info(
            "request_id=%s %s %s -> %s in %.1f ms",
            request.state.request_id,
            request.method,
            request.url.path,
            response.status_code,
            (time.perf_counter() - started) * 1000,
        )
        return response

    install_error_handlers(app)
    app.include_router(health_routes.router)
    app.include_router(auth_routes.router)
    app.include_router(investigation_routes.router)
    app.include_router(read_routes.router)
    app.include_router(inbox_routes.router)
    return app


def __getattr__(name: str) -> Any:
    """`raven.api.main:app` for uvicorn: the application is created when it is first asked for."""
    if name == "app":
        application = create_app()
        globals()["app"] = application
        return application
    raise AttributeError(name)
