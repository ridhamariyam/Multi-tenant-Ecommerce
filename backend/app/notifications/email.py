"""Queue emails in the outbox and send them over SMTP.

Callers only ever `enqueue()` (inside their own transaction). The scheduler's
`send-emails` job delivers due emails; a failure is retried with backoff and
after EMAIL_MAX_ATTEMPTS the email is marked FAILED (visible to operators).
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
from email.utils import formataddr, make_msgid

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
    message["Message-ID"] = make_msgid(domain=settings.email_from_address.split("@")[-1])
    if email.reply_to:
        message["Reply-To"] = email.reply_to
    message.set_content(email.text_body)
    if email.html_body:
        message.add_alternative(email.html_body, subtype="html")
    return message


def _smtp_send(message: EmailMessage) -> None:
    settings = get_settings()
    context = ssl.create_default_context()
    if settings.smtp_security == "ssl":
        client: smtplib.SMTP = smtplib.SMTP_SSL(
            settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds, context=context
        )
    else:
        client = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds)
    with client:
        if settings.smtp_security == "starttls":
            client.starttls(context=context)
        if settings.smtp_username:
            client.login(settings.smtp_username, settings.smtp_password or "")
        client.send_message(message)


# Swappable in tests.
send_message = _smtp_send


def _backoff(attempts: int) -> timedelta:
    return timedelta(minutes=min(2 ** attempts, 240))


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
    sent = failed = 0
    for email in rows:
        email.attempts += 1
        try:
            await asyncio.to_thread(send_message, _build(email))
        except (smtplib.SMTPException, OSError, ValueError) as exc:
            failed += 1
            email.last_error = f"{type(exc).__name__}: {exc}"[:500]
            if email.attempts >= settings.email_max_attempts:
                email.status = EmailStatus.FAILED
            else:
                email.send_after = now + _backoff(email.attempts)
            logger.warning("email %s to tenant %s failed: %s", email.kind, email.tenant_id, type(exc).__name__)
            continue
        email.status = EmailStatus.SENT
        email.sent_at = datetime.now(timezone.utc)
        email.last_error = None
        sent += 1
    await session.commit()
    return {"sent": sent, "failed": failed}
