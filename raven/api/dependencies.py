"""Shared request dependencies: settings, registry session, auth service and the signed-in user."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from raven.api.errors import ApiError
from raven.config import Settings
from raven.database.registry_models import User
from raven.services.analysis_runs import AnalysisRunManager
from raven.services.auth import AuthService
from raven.services.inbox import InboxWatcher

SESSION_COOKIE = "raven_session"


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_auth(request: Request) -> AuthService:
    return request.app.state.auth


def get_runs(request: Request) -> AnalysisRunManager:
    return request.app.state.runs


def get_inbox(request: Request) -> InboxWatcher:
    return request.app.state.inbox


def get_registry(request: Request) -> Iterator[Session]:
    with request.app.state.registry_factory() as session:
        yield session


def current_user(request: Request, registry: Session = Depends(get_registry), auth: AuthService = Depends(get_auth)) -> User:
    """The signed-in user. Every route except health, register and login depends on this."""
    token = request.cookies.get(SESSION_COOKIE)
    user = auth.user_for_token(registry, token) if token else None
    if user is None:
        raise ApiError(401, "not_authenticated", "Authentication required.")
    return user


def session_token(request: Request) -> str:
    return request.cookies.get(SESSION_COOKIE, "")
