"""Auth endpoints: register, login, logout, me (spec section 8.2, decision D6: server-side session cookie)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from raven.api.dependencies import (
    SESSION_COOKIE,
    current_user,
    get_auth,
    get_password_reset,
    get_registry,
    get_settings_dep,
    session_token,
)
from raven.api.schemas.auth import ForgotPasswordRequest, LoginRequest, MessageOut, RegisterRequest, ResetPasswordRequest, UserOut
from raven.config import Settings
from raven.database.registry_models import User
from raven.services.auth import AuthService
from raven.services.password_reset import PasswordResetService

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


@router.post("/forgot-password", status_code=202, response_model=MessageOut)
def forgot_password(
    body: ForgotPasswordRequest,
    response: Response,
    registry: Session = Depends(get_registry),
    password_reset: PasswordResetService = Depends(get_password_reset),
) -> MessageOut:
    """Request a password reset email. The answer is the same whether or not the address has an account,
    and an email is sent only when it does, so this cannot be used to test which addresses are registered."""
    response.headers.update(_NO_STORE)
    password_reset.request_reset(registry, body.email)
    return MessageOut(detail="If an account exists for that address, a password reset email has been sent.")


@router.post("/reset-password", response_model=MessageOut)
def reset_password(
    body: ResetPasswordRequest,
    response: Response,
    registry: Session = Depends(get_registry),
    password_reset: PasswordResetService = Depends(get_password_reset),
) -> MessageOut:
    """Set a new password from the token in a reset email. Every other session of the account is signed out."""
    response.headers.update(_NO_STORE)
    password_reset.reset_password(registry, body.token, body.password.get_secret_value())
    return MessageOut(detail="Your password has been updated. Sign in with your new password.")


@router.get("/me", response_model=UserOut)
def me(response: Response, user: User = Depends(current_user)) -> User:
    """The signed-in user."""
    response.headers.update(_NO_STORE)
    return user
