"""Accounts and login sessions (spec sections 4 and 6.5, decision D6).

Passwords are hashed with Argon2 (argon2id); a plain password is never stored, logged or returned. A login
creates a server-side session: a random token goes to the browser in an HttpOnly cookie and only the SHA-256
hash of the token is stored, so a copy of the registry database cannot be used to sign in.

Login errors are the same for an unknown email and a wrong password, and an unknown email costs the same
hashing time, so the answer does not tell whether an account exists.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from collections.abc import Callable
from datetime import datetime

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from raven.database.registry_models import User, UserSession
from raven.services.clock import in_hours, iso, utc_now

MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 128
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthError(Exception):
    """A sign-up or sign-in problem that the API turns into an error response."""

    def __init__(self, code: str, detail: str, status_code: int) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status_code = status_code


# ---------------------------------------------------------------------------- input rules


def validate_name(name: str) -> str:
    cleaned = name.strip()
    if not 1 <= len(cleaned) <= 100:
        raise ValueError("name must have 1 to 100 characters")
    return cleaned


def validate_organization(organization: str | None) -> str | None:
    if organization is None:
        return None
    cleaned = organization.strip()
    if len(cleaned) > 100:
        raise ValueError("organization must have at most 100 characters")
    return cleaned or None


def normalize_email(email: str) -> str:
    return email.strip().lower()


def validate_email(email: str) -> str:
    cleaned = normalize_email(email)
    if len(cleaned) > 254 or not _EMAIL_PATTERN.match(cleaned):
        raise ValueError("email must be a valid email address")
    return cleaned


def validate_password(password: str) -> str:
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise ValueError(f"password must have {MIN_PASSWORD_LENGTH} to {MAX_PASSWORD_LENGTH} characters")
    if not password.strip():
        raise ValueError("password must not be only spaces")
    return password


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------- service


class AuthService:
    def __init__(
        self,
        hasher: PasswordHasher | None = None,
        session_hours: int = 12,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self.hasher = hasher or PasswordHasher()
        self.session_hours = session_hours
        self._now = now
        self._dummy_hash = self.hasher.hash("raven-dummy-password-for-timing")

    def register(self, session: Session, *, name: str, email: str, organization: str | None, password: str) -> User:
        user = User(
            name=validate_name(name),
            email=validate_email(email),
            organization=validate_organization(organization),
            password_hash=self.hasher.hash(validate_password(password)),
            created_at=iso(self._now()),
        )
        session.add(user)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise AuthError("email_already_registered", "An account with this email already exists.", 409) from exc
        return user

    def login(self, session: Session, *, email: str, password: str) -> tuple[User, str]:
        """Check the credentials and start a session. Return the user and the new session token."""
        user = session.scalars(select(User).where(User.email == normalize_email(email))).one_or_none()
        if user is None:
            try:
                self.hasher.verify(self._dummy_hash, password)
            except VerificationError:
                pass
            raise self._invalid_credentials()
        try:
            self.hasher.verify(user.password_hash, password)
        except (VerifyMismatchError, InvalidHashError, VerificationError) as exc:
            raise self._invalid_credentials() from exc
        if self.hasher.check_needs_rehash(user.password_hash):
            user.password_hash = self.hasher.hash(password)

        now = self._now()
        session.execute(delete(UserSession).where(UserSession.user_id == user.id, UserSession.expires_at <= iso(now)))
        token = secrets.token_urlsafe(32)
        session.add(
            UserSession(
                user_id=user.id,
                token_hash=hash_token(token),
                created_at=iso(now),
                expires_at=in_hours(self.session_hours, now),
            )
        )
        session.commit()
        return user, token

    def user_for_token(self, session: Session, token: str) -> User | None:
        """The user of a valid, unexpired session token, or None."""
        row = session.scalars(select(UserSession).where(UserSession.token_hash == hash_token(token))).one_or_none()
        if row is None:
            return None
        if row.expires_at <= iso(self._now()):
            session.delete(row)
            session.commit()
            return None
        return session.get(User, row.user_id)

    def logout(self, session: Session, token: str) -> None:
        session.execute(delete(UserSession).where(UserSession.token_hash == hash_token(token)))
        session.commit()

    @staticmethod
    def _invalid_credentials() -> AuthError:
        return AuthError("invalid_credentials", "Email or password is not correct.", 401)
