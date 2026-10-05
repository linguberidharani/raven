"""Password reset by email (spec section 8.2, an extension of decision D6).

A reset link is single-use and time-limited; its token is stored only as a SHA-256 hash (the same rule as a
session token), so a copy of the registry database cannot be used to reset an account. Whether an email address
has an account on this installation is never revealed: requesting a reset always answers the same way, and only
sends mail when the address is known.

Resetting the password signs the account out everywhere (every existing session is deleted), the same as
changing a password on most real services.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Callable
from datetime import datetime

from argon2 import PasswordHasher
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from raven.database.registry_models import PasswordResetToken, User, UserSession
from raven.services.auth import AuthError, hash_token, normalize_email, validate_password
from raven.services.clock import in_hours, iso, utc_now
from raven.services.mailer import Mailer, MailError

logger = logging.getLogger("raven.password_reset")

RESET_TOKEN_BYTES = 32


def _invalid_token() -> AuthError:
    return AuthError("invalid_reset_token", "This password reset link is invalid or has expired. Request a new one.", 400)


class PasswordResetService:
    def __init__(
        self,
        mailer: Mailer,
        hasher: PasswordHasher | None = None,
        hours: int = 1,
        base_url: str = "http://localhost:5173",
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self.mailer = mailer
        self.hasher = hasher or PasswordHasher()
        self.hours = hours
        self.base_url = base_url.rstrip("/")
        self._now = now

    def request_reset(self, session: Session, email: str) -> None:
        """Email a reset link when the address has an account. Never raises: every caller gets the same answer,
        whether or not the address is registered, and whether or not sending the email succeeded."""
        user = session.scalars(select(User).where(User.email == normalize_email(email))).one_or_none()
        if user is None:
            logger.info("password reset requested for an address with no account on this installation")
            return

        session.execute(
            delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
        )
        token = secrets.token_urlsafe(RESET_TOKEN_BYTES)
        now = self._now()
        session.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=hash_token(token),
                created_at=iso(now),
                expires_at=in_hours(self.hours, now),
            )
        )
        session.commit()

        link = f"{self.base_url}/reset-password?token={token}"
        hours_text = "1 hour" if self.hours == 1 else f"{self.hours} hours"
        text_body = (
            f"Hello {user.name},\n\n"
            f"A password reset was requested for your RAVEN account ({user.email}).\n"
            f"Open this link to choose a new password. It works once, and only for the next {hours_text}:\n\n"
            f"{link}\n\n"
            "If you did not request this, you can ignore this email; your password has not been changed."
        )
        html_body = (
            f"<p>Hello {user.name},</p>"
            f"<p>A password reset was requested for your RAVEN account ({user.email}).</p>"
            f'<p><a href="{link}">Choose a new password</a>. It works once, and only for the next {hours_text}.</p>'
            "<p>If you did not request this, you can ignore this email; your password has not been changed.</p>"
        )
        try:
            self.mailer.send(to=user.email, subject="Reset your RAVEN password", text_body=text_body, html_body=html_body)
        except MailError as exc:
            logger.warning("could not send the password reset email: %s", exc)

    def reset_password(self, session: Session, token: str, new_password: str) -> None:
        """Set a new password from a reset link and sign the account out everywhere."""
        row = session.scalars(select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(token))).one_or_none()
        now_iso = iso(self._now())
        if row is None or row.used_at is not None or row.expires_at <= now_iso:
            raise _invalid_token()
        user = session.get(User, row.user_id)
        if user is None:
            raise _invalid_token()

        user.password_hash = self.hasher.hash(validate_password(new_password))
        row.used_at = now_iso
        session.execute(delete(UserSession).where(UserSession.user_id == user.id))
        session.commit()
