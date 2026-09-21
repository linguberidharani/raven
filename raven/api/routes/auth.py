"""Auth endpoints: register, login, logout, me (spec section 8.2, decision D6: server-side session cookie)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from raven.api.dependencies import SESSION_COOKIE, current_user, get_auth, get_registry, get_settings_dep, session_token
from raven.api.schemas.auth import LoginRequest, RegisterRequest, UserOut
from raven.config import Settings
from raven.database.registry_models import User
from raven.services.auth import AuthService

router = APIRouter(prefix="/api/auth", tags=["auth"])

_NO_STORE = {"Cache-Control": "no-store"}


@router.post("/register", status_code=201, response_model=UserOut)
def register(
    body: RegisterRequest,
    response: Response,
    registry: Session = Depends(get_registry),
    auth: AuthService = Depends(get_auth),
) -> User:
    """Create an account. It does not sign in; call login next."""
    response.headers.update(_NO_STORE)
    return auth.register(
        registry,
        name=body.name,
        email=body.email,
        organization=body.organization,
        password=body.password.get_secret_value(),
    )


@router.post("/login", response_model=UserOut)
def login(
    body: LoginRequest,
    response: Response,
    registry: Session = Depends(get_registry),
    auth: AuthService = Depends(get_auth),
    settings: Settings = Depends(get_settings_dep),
) -> User:
    """Sign in. The session token is set in an HttpOnly, SameSite=Lax cookie."""
    user, token = auth.login(registry, email=body.email, password=body.password.get_secret_value())
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=settings.session_hours * 3600,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )
    response.headers.update(_NO_STORE)
    return user


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    registry: Session = Depends(get_registry),
    auth: AuthService = Depends(get_auth),
    settings: Settings = Depends(get_settings_dep),
    _user: User = Depends(current_user),
) -> Response:
    """Sign out: the session is deleted on the server and the cookie is cleared."""
    auth.logout(registry, session_token(request))
    response = Response(status_code=204, headers=_NO_STORE)
    response.delete_cookie(key=SESSION_COOKIE, path="/", httponly=True, samesite="lax", secure=settings.cookie_secure)
    return response


@router.get("/me", response_model=UserOut)
def me(response: Response, user: User = Depends(current_user)) -> User:
    """The signed-in user."""
    response.headers.update(_NO_STORE)
    return user
