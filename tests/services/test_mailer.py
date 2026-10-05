"""Unit tests for the SMTP mailer. A fake SMTP client stands in for smtplib.SMTP, so no real network is used."""

import pytest

from raven.config import Settings
from raven.services.mailer import Mailer, MailError


class FakeSMTP:
    """Records what a real smtplib.SMTP would have been asked to do."""

    instances: list["FakeSMTP"] = []

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.ehlo_calls = 0
        self.started_tls = False
        self.login_args = None
        self.sent = []
        self.quit_called = False
        FakeSMTP.instances.append(self)

    def ehlo(self):
        self.ehlo_calls += 1

    def starttls(self):
        self.started_tls = True

    def login(self, username, password):
        self.login_args = (username, password)

    def send_message(self, message):
        self.sent.append(message)

    def quit(self):
        self.quit_called = True


class RefusingSMTP(FakeSMTP):
    def send_message(self, message):
        import smtplib

        raise smtplib.SMTPRecipientsRefused({"nobody@example.com": (550, b"no such user")})


def make_settings(tmp_path, **values):
    values.setdefault("env", "test")
    return Settings(_env_file=None, data_dir=tmp_path / "data", log_level="WARNING", **values)


@pytest.fixture(autouse=True)
def clean_instances():
    FakeSMTP.instances.clear()
    yield
    FakeSMTP.instances.clear()


def test_not_configured_without_a_host_or_a_from_address(tmp_path):
    mailer = Mailer(make_settings(tmp_path), smtp_factory=FakeSMTP)
    assert mailer.configured is False
    with pytest.raises(MailError):
        mailer.send(to="a@example.com", subject="Hi", text_body="Hello")
    assert FakeSMTP.instances == []


def test_sends_a_message_with_starttls_and_login(tmp_path):
    settings = make_settings(
        tmp_path,
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_username="bot@example.com",
        smtp_password="app-password",
        smtp_use_tls=True,
        smtp_from_address="raven@example.com",
        smtp_from_name="RAVEN",
    )
    mailer = Mailer(settings, smtp_factory=FakeSMTP)
    assert mailer.configured is True
    mailer.send(to="ada@example.com", subject="Reset your RAVEN password", text_body="link here", html_body="<p>link here</p>")

    server = FakeSMTP.instances[0]
    assert (server.host, server.port) == ("smtp.example.com", 587)
    assert server.started_tls is True
    assert server.login_args == ("bot@example.com", "app-password")
    assert server.quit_called is True
    message = server.sent[0]
    assert message["To"] == "ada@example.com"
    assert message["From"] == "RAVEN <raven@example.com>"
    assert message["Subject"] == "Reset your RAVEN password"
    assert "link here" in message.get_body(preferencelist=("plain",)).get_content()
    assert "<p>link here</p>" in message.get_body(preferencelist=("html",)).get_content()


def test_skips_tls_and_login_when_not_set(tmp_path):
    settings = make_settings(tmp_path, smtp_host="localhost", smtp_use_tls=False, smtp_from_address="raven@example.com")
    Mailer(settings, smtp_factory=FakeSMTP).send(to="a@example.com", subject="Hi", text_body="Hello")
    server = FakeSMTP.instances[0]
    assert server.started_tls is False
    assert server.login_args is None


def test_a_server_refusal_becomes_a_mail_error_and_still_closes_the_connection(tmp_path):
    settings = make_settings(tmp_path, smtp_host="localhost", smtp_from_address="raven@example.com")
    mailer = Mailer(settings, smtp_factory=RefusingSMTP)
    with pytest.raises(MailError):
        mailer.send(to="nobody@example.com", subject="Hi", text_body="Hello")
    assert FakeSMTP.instances[0].quit_called is True


def test_cannot_connect_becomes_a_mail_error(tmp_path):
    def broken_factory(host, port):
        raise OSError("connection refused")

    settings = make_settings(tmp_path, smtp_host="localhost", smtp_from_address="raven@example.com")
    with pytest.raises(MailError):
        Mailer(settings, smtp_factory=broken_factory).send(to="a@example.com", subject="Hi", text_body="Hello")
