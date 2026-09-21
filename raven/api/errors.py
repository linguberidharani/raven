"""One error format for the whole API: {"detail": ..., "code": "<machine code>", "request_id": "<id>"}.

Error responses never contain request bodies, so a rejected password is never echoed back.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from raven.services.auth import AuthError

logger = logging.getLogger("raven.api")

REQUEST_ID_HEADER = "X-Request-ID"

_HTTP_CODES = {400: "bad_request", 401: "not_authenticated", 403: "forbidden", 404: "not_found", 405: "method_not_allowed", 413: "payload_too_large"}


class ApiError(Exception):
    """An error with an HTTP status and a machine-readable code."""

    def __init__(self, status_code: int, code: str, detail: Any) -> None:
        super().__init__(str(detail))
        self.status_code = status_code
        self.code = code
        self.detail = detail


def request_id_of(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def error_response(request: Request, status_code: int, code: str, detail: Any) -> JSONResponse:
    request_id = request_id_of(request)
    return JSONResponse(
        status_code=status_code,
        content={"detail": detail, "code": code, "request_id": request_id},
        headers={REQUEST_ID_HEADER: request_id},
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        return error_response(request, exc.status_code, exc.code, exc.detail)

    @app.exception_handler(AuthError)
    async def handle_auth_error(request: Request, exc: AuthError) -> JSONResponse:
        return error_response(request, exc.status_code, exc.code, exc.detail)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        detail = [
            {"loc": [str(part) for part in error.get("loc", ())], "msg": str(error.get("msg", "invalid value")).removeprefix("Value error, ")}
            for error in exc.errors()
        ]
        return error_response(request, 422, "validation_error", detail)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, "http_error")
        response = error_response(request, exc.status_code, code, str(exc.detail))
        for name, value in (exc.headers or {}).items():
            response.headers[name] = value
        return response

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled error request_id=%s path=%s", request_id_of(request), request.url.path, exc_info=exc)
        return error_response(request, 500, "internal_error", "Internal server error")
