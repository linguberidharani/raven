"""Sends real email over SMTP (spec section 8.2: password reset).

Configured with the RAVEN_SMTP_* settings (host, port, username, password, use_tls, from address). When
RAVEN_SMTP_HOST or RAVEN_SMTP_FROM_ADDRESS is not set, RAVEN still runs: a reset request is accepted as usual
(so a missing account is never revealed), but Mailer.send raises MailError instead of contacting a server, and
the caller logs a warning instead of failing the request.

The SMTP client is injectable (smtp_factory) so tests can send to a fake server or capture the message without
a network connection; the default factory opens a real connection with smtplib.
"""

from __future__ import annotations

import smtplib
from collections.abc import Callable
from email.message import EmailMessage

from raven.config import Settings

SMTPFactory = Callable[[str, int], smtplib.SMTP]


class MailError(Exception):
    """The message was not sent: RAVEN is not configured for email, or the SMTP server refused it."""


def _default_factory(host: str, port: int) -> smtplib.SMTP:
    return smtplib.SMTP(host, port, timeout=10)


class Mailer:
    def __init__(self, settings: Settings, smtp_factory: SMTPFactory | None = None) -> None:
        self.settings = settings
        self._smtp_factory = smtp_factory or _default_factory

    @property
    def configured(self) -> bool:
        return self.settings.mail_configured

    def send(self, *, to: str, subject: str, text_body: str, html_body: str | None = None) -> None:
        """Send one email. Raises MailError when RAVEN has no SMTP settings, or the server rejects the message."""
        if not self.configured:
            raise MailError("RAVEN_SMTP_HOST and RAVEN_SMTP_FROM_ADDRESS are not set; no email was sent.")

        message = EmailMessage()
        message["Subject"] = subject
        from_address = self.settings.smtp_from_address
        message["From"] = f"{self.settings.smtp_from_name} <{from_address}>" if self.settings.smtp_from_name else from_address
        message["To"] = to
        message.set_content(text_body)
        if html_body:
            message.add_alternative(html_body, subtype="html")

        try:
            server = self._smtp_factory(self.settings.smtp_host, self.settings.smtp_port)
        except OSError as exc:
            raise MailError(f"Could not connect to the SMTP server: {exc}") from exc
        try:
            server.ehlo()
            if self.settings.smtp_use_tls:
                server.starttls()
                server.ehlo()
            if self.settings.smtp_username and self.settings.smtp_password:
                server.login(self.settings.smtp_username, self.settings.smtp_password)
            server.send_message(message)
        except (smtplib.SMTPException, OSError) as exc:
            raise MailError(f"Sending the email failed: {exc}") from exc
        finally:
            try:
                server.quit()
            except Exception:  # noqa: BLE001 - closing the connection must never mask the real error above
                pass
