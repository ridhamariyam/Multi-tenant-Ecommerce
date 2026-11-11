"""SMTP delivery: the real transport against a local SMTP server and a scripted
fake, failure handling (auth, timeout, unavailable, quota, bad recipient),
retries, message format, and that the API never depends on the mail server."""

from __future__ import annotations

import base64
import email as email_lib
import logging
import smtplib
import socket
import socketserver
import threading
from email import policy

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.notifications import email
from app.notifications.models import EmailStatus, OutboxEmail

PASSWORD = "abcdefghijklmnop"


# --- a minimal real SMTP server (plain, AUTH PLAIN/LOGIN) ------------------


class _Handler(socketserver.StreamRequestHandler):
    def _say(self, line: str) -> None:
        self.wfile.write((line + "\r\n").encode())

    def handle(self) -> None:
        server = self.server
        self._say("220 test.local ESMTP")
        data_mode, lines, sender, rcpts = False, [], None, []
        while True:
            raw = self.rfile.readline()
            if not raw:
                return
            line = raw.decode().rstrip("\r\n")
            if data_mode:
                if line == ".":
                    server.messages.append({"from": sender, "to": list(rcpts), "data": "\r\n".join(lines)})
                    data_mode, lines, rcpts = False, [], []
                    self._say("250 2.0.0 queued")
                else:
                    lines.append(line[1:] if line.startswith("..") else line)
                continue
            verb = line.split(" ", 1)[0].upper()
            if verb in ("EHLO", "HELO"):
                self.wfile.write(b"250-test.local\r\n250-AUTH PLAIN LOGIN\r\n250 8BITMIME\r\n")
            elif verb == "AUTH":
                parts = line.split(" ")
                if parts[1].upper() == "PLAIN":
                    payload = parts[2] if len(parts) > 2 else None
                    if payload is None:
                        self._say("334 ")
                        payload = self.rfile.readline().decode().strip()
                    _, user, password = base64.b64decode(payload).decode().split("\0")
                else:  # LOGIN
                    self._say("334 VXNlcm5hbWU6")
                    user = base64.b64decode(self.rfile.readline().strip()).decode()
                    self._say("334 UGFzc3dvcmQ6")
                    password = base64.b64decode(self.rfile.readline().strip()).decode()
                server.logins.append(user)
                if (user, password) == server.credentials:
                    self._say("235 2.7.0 Accepted")
                else:
                    self._say("535 5.7.8 Username and Password not accepted")
            elif verb == "MAIL":
                sender = line.split(":", 1)[1].strip().strip("<>").split(">")[0]
                self._say("250 OK")
            elif verb == "RCPT":
                address = line.split(":", 1)[1].strip().strip("<>")
                if address.startswith("nobody@"):
                    self._say("550 5.1.1 No such user")
                else:
                    rcpts.append(address)
                    self._say("250 OK")
            elif verb == "DATA":
                data_mode = True
                self._say("354 go ahead")
            elif verb == "RSET":
                rcpts = []
                self._say("250 OK")
            elif verb == "QUIT":
                self._say("221 bye")
                return
            else:
                self._say("250 OK")


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


@pytest.fixture
def smtp_server(monkeypatch):
    server = _Server(("127.0.0.1", 0), _Handler)
    server.messages, server.logins = [], []
    server.credentials = ("orders@cliq.test", PASSWORD)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    s = get_settings()
    for name, value in {
        "smtp_host": "127.0.0.1",
        "smtp_port": server.server_address[1],
        "smtp_security": "none",  # the local test server has no TLS; STARTTLS is covered below
        "smtp_username": "orders@cliq.test",
        "smtp_password": PASSWORD,
        "smtp_timeout_seconds": 5.0,
        "email_from_address": "orders@cliq.test",
    }.items():
        monkeypatch.setattr(s, name, value)
    yield server
    server.shutdown()
    server.server_close()


async def _queue(session, n: int = 1, to: str = "shopper@example.net", **extra) -> None:
    for i in range(n):
        await email.enqueue(
            session, kind="test", dedupe_key=f"t-{to}-{i}", to=to, subject=f"Order {i} confirmed",
            text=f"Thanks for order {i}.", html_body=email.simple_html("Order confirmed", [f"Thanks {i}"]), **extra,
        )
    await session.commit()


async def _rows(session):
    return (await session.scalars(select(OutboxEmail).order_by(OutboxEmail.subject))).all()


# --- successful submission ---------------------------------------------------


async def test_emails_are_submitted_over_one_authenticated_connection(session, smtp_server):
    await _queue(session, 3)

    result = await email.send_due(session)

    assert result == {"sent": 3, "failed": 0, "retrying": 0}
    assert smtp_server.logins == ["orders@cliq.test"]  # one login for the whole batch
    assert len(smtp_server.messages) == 3
    first = smtp_server.messages[0]
    assert first["from"] == "orders@cliq.test" and first["to"] == ["shopper@example.net"]
    assert all(r.status == EmailStatus.SENT and r.attempts == 1 and r.sent_at for r in await _rows(session))


async def test_the_message_has_text_and_html_parts_and_correct_headers(session, smtp_server):
    await _queue(session, reply_to="help@brand.example.net", from_name="Harbor Lane")

    await email.send_due(session)

    message = email_lib.message_from_string(smtp_server.messages[0]["data"], policy=policy.default)
    assert message["From"] == "Harbor Lane <orders@cliq.test>"
    assert message["To"] == "shopper@example.net"
    assert message["Reply-To"] == "help@brand.example.net"
    assert message["Date"] and message["Message-ID"].endswith("@cliq.test>")
    assert message.get_content_type() == "multipart/alternative"
    assert "Thanks for order 0." in message.get_body(("plain",)).get_content()
    html = message.get_body(("html",)).get_content()
    assert html.startswith("<!doctype html>") and "Order confirmed" in html


# --- failures ------------------------------------------------------------------


async def test_wrong_credentials_keep_every_email_queued_and_raise(session, smtp_server, monkeypatch, caplog):
    monkeypatch.setattr(get_settings(), "smtp_password", "wrong-password-x")
    await _queue(session, 2)

    with caplog.at_level(logging.INFO), pytest.raises(email.EmailProviderError, match="SMTPAuthenticationError 535"):
        await email.send_due(session)

    rows = await _rows(session)
    assert all(r.status == EmailStatus.PENDING and r.attempts == 0 for r in rows)  # nothing burned
    assert smtp_server.messages == []
    logged = caplog.text
    assert "wrong-password-x" not in logged and PASSWORD not in logged and "shopper@example.net" not in logged


async def test_a_server_that_never_answers_times_out(session, smtp_server, monkeypatch):
    silent = socket.socket()
    silent.bind(("127.0.0.1", 0))
    silent.listen(1)  # accepts the connection, never sends the 220 greeting
    monkeypatch.setattr(get_settings(), "smtp_port", silent.getsockname()[1])
    monkeypatch.setattr(get_settings(), "smtp_timeout_seconds", 0.5)
    await _queue(session)
    try:
        # smtplib reports a greeting timeout as "Connection unexpectedly closed: timed out".
        with pytest.raises(email.EmailProviderError, match="timed out"):
            await email.send_due(session)
    finally:
        silent.close()
    (row,) = await _rows(session)
    assert row.status == EmailStatus.PENDING and row.attempts == 0


async def test_an_unreachable_server_keeps_emails_queued(session, smtp_server, monkeypatch):
    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    port = closed.getsockname()[1]
    closed.close()  # nothing listens here
    monkeypatch.setattr(get_settings(), "smtp_port", port)
    await _queue(session)

    with pytest.raises(email.EmailProviderError, match="ConnectionRefusedError"):
        await email.send_due(session)
    (row,) = await _rows(session)
    assert row.status == EmailStatus.PENDING and row.attempts == 0


async def test_a_rejected_recipient_fails_that_email_only(session, smtp_server):
    await _queue(session, 1, to="nobody@example.net")
    await _queue(session, 1, to="shopper@example.net")

    result = await email.send_due(session)

    assert result == {"sent": 1, "failed": 1, "retrying": 0}
    bad = await session.scalar(select(OutboxEmail).where(OutboxEmail.to_address == "nobody@example.net"))
    assert bad.status == EmailStatus.FAILED and "550" in bad.last_error  # permanent: no retries
    assert len(smtp_server.messages) == 1


# --- scripted fake smtplib.SMTP: STARTTLS order, quota, transient errors --------


class FakeSMTP:
    script: dict = {}
    instances: list = []

    def __init__(self, host, port, timeout):
        self.calls = [("connect", host, port, timeout)]
        self.sock = None
        FakeSMTP.instances.append(self)
        self._maybe_fail("connect")

    def _maybe_fail(self, step):
        failures = FakeSMTP.script.get(step)
        if failures:
            raise failures.pop(0)

    def ehlo(self):
        self.calls.append(("ehlo",))

    def starttls(self, context):
        self.calls.append(("starttls", context.verify_mode, context.check_hostname))
        self._maybe_fail("starttls")

    def login(self, user, password):
        self.calls.append(("login", user))
        self._maybe_fail("login")

    def send_message(self, message):
        self.calls.append(("send", message["To"]))
        self._maybe_fail("send")

    def quit(self):
        self.calls.append(("quit",))

    def close(self):
        self.calls.append(("close",))


@pytest.fixture
def fake_smtp(monkeypatch):
    FakeSMTP.script, FakeSMTP.instances = {}, []
    monkeypatch.setattr(email.smtplib, "SMTP", FakeSMTP)
    s = get_settings()
    for name, value in {
        "smtp_host": "smtp.gmail.com", "smtp_port": 587, "smtp_security": "starttls",
        "smtp_username": "orders@cliq.test", "smtp_password": PASSWORD, "smtp_timeout_seconds": 20.0,
        "email_from_address": "orders@cliq.test",
    }.items():
        monkeypatch.setattr(s, name, value)
    return FakeSMTP


async def test_starttls_with_certificate_checks_comes_before_login(session, fake_smtp):
    import ssl

    await _queue(session)
    await email.send_due(session)

    calls = fake_smtp.instances[0].calls
    assert calls[0] == ("connect", "smtp.gmail.com", 587, 20.0)
    steps = [c[0] for c in calls]
    assert steps.index("starttls") < steps.index("login") < steps.index("send")
    assert calls[steps.index("starttls")][1:] == (ssl.CERT_REQUIRED, True)
    assert steps[-1] == "quit"


async def test_a_server_without_starttls_is_a_provider_error(session, fake_smtp):
    fake_smtp.script["starttls"] = [smtplib.SMTPNotSupportedError("STARTTLS extension not supported by server.")]
    await _queue(session)

    with pytest.raises(email.EmailProviderError):
        await email.send_due(session)
    assert "login" not in [c[0] for c in fake_smtp.instances[0].calls]  # never sends credentials in clear


async def test_gmail_daily_quota_stops_the_batch_without_failing_emails(session, fake_smtp):
    fake_smtp.script["send"] = [smtplib.SMTPDataError(550, b"5.4.5 Daily user sending limit exceeded.")]
    await _queue(session, 3)

    with pytest.raises(email.EmailProviderError):
        await email.send_due(session)
    assert all(r.status == EmailStatus.PENDING and r.attempts == 0 for r in await _rows(session))


async def test_a_dropped_connection_retries_with_backoff_and_reconnects(session, fake_smtp, monkeypatch):
    monkeypatch.setattr(get_settings(), "email_max_attempts", 3)
    fake_smtp.script["send"] = [smtplib.SMTPServerDisconnected("Connection unexpectedly closed")]
    await _queue(session, 2)

    result = await email.send_due(session)

    assert result == {"sent": 1, "failed": 0, "retrying": 1}
    first, second = await _rows(session)
    assert first.status == EmailStatus.PENDING and first.attempts == 1 and first.send_after > first.created_at
    assert "SMTPServerDisconnected" in first.last_error
    assert second.status == EmailStatus.SENT
    assert len(fake_smtp.instances) == 2  # reconnected after the drop


async def test_a_temporary_4xx_rejection_is_retried_then_given_up(session, fake_smtp, monkeypatch):
    monkeypatch.setattr(get_settings(), "email_max_attempts", 2)
    fake_smtp.script["send"] = [smtplib.SMTPDataError(451, b"4.3.0 Try again later")] * 2
    await _queue(session)

    assert (await email.send_due(session))["retrying"] == 1
    (row,) = await _rows(session)
    row.send_after = row.created_at
    await session.commit()
    assert (await email.send_due(session))["failed"] == 1
    await session.refresh(row)
    assert row.status == EmailStatus.FAILED and row.attempts == 2


@pytest.mark.parametrize(
    ("exc", "kind"),
    [
        (smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted"), "provider"),
        (email.SmtpConnectError(TimeoutError("timed out")), "provider"),
        (smtplib.SMTPDataError(550, b"5.4.5 Daily user sending limit exceeded"), "provider"),
        (smtplib.SMTPRecipientsRefused({"x@y.z": (550, b"5.1.1 no such user")}), "permanent"),
        (smtplib.SMTPDataError(552, b"5.7.0 message rejected"), "permanent"),
        (smtplib.SMTPDataError(451, b"4.3.0 later"), "retry"),
        (smtplib.SMTPServerDisconnected("closed"), "retry"),
        (TimeoutError("timed out"), "retry"),
    ],
)
def test_errors_are_classified(exc, kind):
    assert email.classify(exc) == kind


# --- the live-check command (same transport) -------------------------------------


def test_smtp_check_reports_without_secrets(smtp_server, capsys):
    from app.commands import smtp_check

    report = smtp_check.run("shopper@example.net")

    assert report["connected"] and report["authenticated"] and report["message_id"]
    assert report["username"] == "o***@cliq.test" and report["sent_to"] == "s***@example.net"
    assert PASSWORD not in str(report)
    assert len(smtp_server.messages) == 1


def test_smtp_check_explains_a_login_failure(smtp_server, monkeypatch):
    from app.commands import smtp_check

    monkeypatch.setattr(get_settings(), "smtp_password", "wrong-password-x")
    report = smtp_check.run(None)

    assert report["error"].startswith("SMTPAuthenticationError") and report["classified_as"] == "provider"
    assert "wrong-password-x" not in str(report)
