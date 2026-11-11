"""Queue emails in the outbox and send them over SMTP.

Callers only ever `enqueue()` (inside their own transaction), so a mail
provider outage can never fail the API request that caused the email. The
scheduler's `emails` job delivers due emails over one SMTP connection per
batch:

- provider-wide failures (cannot connect, timeout, TLS or login refused,
  sending quota reached) leave every email PENDING with its attempts
  unchanged and raise `EmailProviderError`, so the job shows as failed in the
  System tab and the alert webhook fires;
- a permanent rejection of one message (5xx: bad recipient, rejected
  content) marks that email FAILED at once;
- any other per-message failure (4xx, dropped connection) is retried with
  backoff, and after EMAIL_MAX_ATTEMPTS the email is marked FAILED.

Logs carry the outbox id, kind, tenant and SMTP code, never the recipient,
the body (reset links) or credentials.
"""

from __future__ import annotations

import asyncio
import html
import logging
import smtplib
import ssl
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.notifications.models import EmailStatus, OutboxEmail

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    return bool(get_settings().smtp_host)


async def enqueue(
    session: AsyncSession,
    *,
    kind: str,
    dedupe_key: str,
    to: str,
    subject: str,
    text: str,
    html_body: str | None = None,
    tenant_id: uuid.UUID | None = None,
    from_name: str | None = None,
    reply_to: str | None = None,
) -> bool:
    """Add one email unless an email with this dedupe key exists. Caller commits."""
    settings = get_settings()
    result = await session.execute(
        insert(OutboxEmail)
        .values(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            kind=kind,
            dedupe_key=dedupe_key[:200],
            to_address=to.strip(),
            from_name=(from_name or settings.email_from_name)[:150],
            reply_to=reply_to,
            subject=subject[:255],
            text_body=text,
            html_body=html_body,
            status=EmailStatus.PENDING,
            attempts=0,
            send_after=datetime.now(timezone.utc),
        )
        .on_conflict_do_nothing(constraint="uq_email_outbox_dedupe_key")
    )
    return bool(result.rowcount)


def simple_html(title: str, paragraphs: list[str], button: tuple[str, str] | None = None) -> str:
    """A plain, mail-client-safe layout. Text is escaped; links are attributes."""
    body = "".join(f'<p style="margin:0 0 14px">{html.escape(p)}</p>' for p in paragraphs)
    if button:
        label, url = button
        body += (
            f'<p style="margin:22px 0"><a href="{html.escape(url, quote=True)}" '
            'style="background:#111;color:#fff;padding:12px 20px;border-radius:6px;'
            f'text-decoration:none;display:inline-block">{html.escape(label)}</a></p>'
        )
    return (
        '<!doctype html><html><body style="font-family:Arial,Helvetica,sans-serif;'
        'color:#222;background:#f6f6f6;margin:0;padding:24px">'
        '<div style="max-width:560px;margin:0 auto;background:#fff;padding:28px;border-radius:8px">'
        f'<h1 style="font-size:20px;margin:0 0 18px">{html.escape(title)}</h1>{body}</div></body></html>'
    )


def _build(email: OutboxEmail) -> EmailMessage:
    settings = get_settings()
    message = EmailMessage()
    message["From"] = formataddr((email.from_name, settings.email_from_address))
    message["To"] = email.to_address
    message["Subject"] = email.subject
    message["Date"] = formatdate(localtime=False, usegmt=True)
    message["Message-ID"] = make_msgid(domain=settings.email_from_address.split("@")[-1])
    if email.reply_to:
        message["Reply-To"] = email.reply_to
    message.set_content(email.text_body)
    if email.html_body:
        message.add_alternative(email.html_body, subtype="html")
    return message


class EmailProviderError(RuntimeError):
    """The SMTP provider itself is unusable right now; nothing was marked failed."""


class SmtpConnectError(smtplib.SMTPException):
    """Connecting, TLS or login failed (the original error is the __cause__)."""

    def __init__(self, cause: BaseException) -> None:
        super().__init__(f"{type(cause).__name__}: {_detail(cause)}")
        self.cause = cause
        self.smtp_code = _smtp_code(cause)


class SmtpTransport:
    """One authenticated SMTP connection, opened lazily and reused for a batch."""

    def __init__(self) -> None:
        self.client: smtplib.SMTP | None = None
        self.tls: dict[str, str | None] = {}

    def open(self) -> None:
        settings = get_settings()
        context = ssl.create_default_context()  # verifies the certificate and host name
        if settings.smtp_security == "ssl":
            client: smtplib.SMTP = smtplib.SMTP_SSL(
                settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds, context=context
            )
        else:
            client = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds)
        try:
            client.ehlo()
            if settings.smtp_security == "starttls":
                client.starttls(context=context)  # raises SMTPNotSupportedError if the server cannot
                client.ehlo()
            sock = getattr(client, "sock", None)
            if isinstance(sock, ssl.SSLSocket):
                self.tls = {"version": sock.version(), "cipher": (sock.cipher() or (None,))[0]}
            if settings.smtp_username:
                client.login(settings.smtp_username, settings.smtp_password or "")
        except BaseException:
            _quietly_close(client)
            raise
        self.client = client

    def send(self, message: EmailMessage) -> None:
        if self.client is None:
            try:
                self.open()
            except (smtplib.SMTPException, OSError) as exc:  # refused, timeout, TLS, login
                raise SmtpConnectError(exc) from exc
        assert self.client is not None
        self.client.send_message(message)

    def reset(self) -> None:
        """Drop a connection that may be broken; the next send reconnects."""
        if self.client is not None:
            _quietly_close(self.client)
            self.client = None

    def close(self) -> None:
        if self.client is not None:
            try:
                self.client.quit()
            except Exception:
                _quietly_close(self.client)
            self.client = None


def _quietly_close(client: smtplib.SMTP) -> None:
    try:
        client.close()
    except Exception:
        pass


# Swappable in tests (a fake transport, or a fake smtplib.SMTP underneath).
open_transport = SmtpTransport


def _smtp_code(exc: BaseException) -> int | None:
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        codes = [code for code, _ in exc.recipients.values()]
        return max(codes) if codes else None
    code = getattr(exc, "smtp_code", None)
    return code if isinstance(code, int) else None


def _detail(exc: BaseException) -> str:
    error = getattr(exc, "smtp_error", None)
    if isinstance(error, bytes):
        return error.decode("utf-8", "replace")
    return str(exc)


def classify(exc: BaseException) -> str:
    """'provider' (stop the batch, keep emails), 'permanent' (this email failed) or 'retry'."""
    code = _smtp_code(exc)
    detail = _detail(exc)
    if isinstance(exc, (smtplib.SMTPAuthenticationError, smtplib.SMTPNotSupportedError, smtplib.SMTPHeloError)):
        return "provider"
    if isinstance(exc, (SmtpConnectError, smtplib.SMTPConnectError)):
        return "provider"
    # Gmail answers 550 5.4.5 / 421 4.7.0 when the account's daily quota or rate is exceeded.
    if "5.4.5" in detail or "4.7.0" in detail or code == 421:
        return "provider"
    if isinstance(exc, (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPDataError)):
        return "permanent" if code is not None and 500 <= code < 600 else "retry"
    return "retry"  # disconnects, timeouts mid-send, 4xx, malformed message (ValueError)


def _error_name(exc: BaseException) -> str:
    return type(exc.cause).__name__ if isinstance(exc, SmtpConnectError) else type(exc).__name__


def _backoff(attempts: int) -> timedelta:
    return timedelta(minutes=min(2 ** attempts, 240))


def _log(level: int, event: str, email: OutboxEmail | None = None, **fields: object) -> None:
    extra = {"event": event, **fields}
    if email is not None:
        extra.update(email_id=str(email.id), kind=email.kind, tenant_id=str(email.tenant_id) if email.tenant_id else None, attempts=email.attempts)
    logger.log(level, event, extra=extra)


async def send_due(session: AsyncSession, *, limit: int = 50) -> dict[str, int]:
    """Deliver due emails. Rows are locked (SKIP LOCKED) so two senders never double-send."""
    if not is_configured():
        return {"sent": 0, "failed": 0, "skipped_unconfigured": 1}
    settings = get_settings()
    now = datetime.now(timezone.utc)
    rows = (
        await session.scalars(
            select(OutboxEmail)
            .where(OutboxEmail.status == EmailStatus.PENDING, OutboxEmail.send_after <= now)
            .order_by(OutboxEmail.send_after)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    ).all()
    if not rows:
        return {"sent": 0, "failed": 0}
    transport = open_transport()
    sent = failed = retrying = 0
    provider_error: BaseException | None = None
    try:
        for email in rows:
            try:
                await asyncio.to_thread(transport.send, _build(email))
            except (smtplib.SMTPException, OSError, ValueError) as exc:
                kind = classify(exc)
                if kind == "provider":
                    provider_error = exc
                    _log(logging.ERROR, "email.provider_unavailable", email, error=_error_name(exc), smtp_code=_smtp_code(exc))
                    break  # this email and the rest stay PENDING, attempts unchanged
                email.attempts += 1
                email.last_error = f"{type(exc).__name__}: {_detail(exc)}"[:500]
                if kind == "permanent" or email.attempts >= settings.email_max_attempts:
                    email.status = EmailStatus.FAILED
                    failed += 1
                    _log(logging.WARNING, "email.failed", email, error=type(exc).__name__, smtp_code=_smtp_code(exc))
                else:
                    email.send_after = now + _backoff(email.attempts)
                    retrying += 1
                    _log(logging.WARNING, "email.retry", email, error=type(exc).__name__, smtp_code=_smtp_code(exc))
                await asyncio.to_thread(transport.reset)
                continue
            email.attempts += 1
            email.status = EmailStatus.SENT
            email.sent_at = datetime.now(timezone.utc)
            email.last_error = None
            sent += 1
            _log(logging.INFO, "email.sent", email)
    finally:
        await asyncio.to_thread(transport.close)
        await session.commit()
    if provider_error is not None:
        cause = provider_error.cause if isinstance(provider_error, SmtpConnectError) else provider_error
        code = _smtp_code(provider_error)
        raise EmailProviderError(
            f"SMTP provider unavailable ({_error_name(provider_error)}"
            + (f" {code}" if code else "")
            + f": {_detail(cause)[:200]}); {sent} sent, the rest stay queued"
        ) from provider_error
    return {"sent": sent, "failed": failed, "retrying": retrying}
