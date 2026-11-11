"""Merchant password reset by email link (single use, 1 hour)."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import hash_password
from app.core.config import get_settings
from app.core.exceptions import ValidationError
from app.merchants.models import MerchantAccount, MerchantRefreshToken
from app.notifications import email
from app.notifications.models import MerchantPasswordReset

TOKEN_LIFETIME = timedelta(hours=1)
INVALID_LINK = "This reset link is invalid or has expired. Ask for a new one."


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def request_reset(session: AsyncSession, address: str) -> None:
    """Email a reset link if the account exists. Says nothing either way."""
    account = await session.scalar(
        select(MerchantAccount).where(MerchantAccount.email == address.strip().lower())
    )
    if account is None or account.status != "ACTIVE":
        return
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    session.add(MerchantPasswordReset(account_id=account.id, token_hash=_hash(token), expires_at=now + TOKEN_LIFETIME))
    link = f"{get_settings().console_base_url}/reset-password?token={quote(token)}"
    paragraphs = [
        f"Hi {account.name or 'there'},",
        "Someone (hopefully you) asked to reset the password for your CliQ merchant account.",
        "The link works once, for one hour. If you did not ask, ignore this email: your password stays the same.",
    ]
    await email.enqueue(
        session,
        kind="merchant-password-reset",
        dedupe_key=f"merchant-password-reset:{_hash(token)}",
        to=account.email,
        subject="Reset your password",
        text="\n\n".join(paragraphs + [link]),
        html_body=email.simple_html("Reset your password", paragraphs, ("Choose a new password", link)),
    )
    await session.commit()


async def reset_password(session: AsyncSession, token: str, new_password: str) -> None:
    now = datetime.now(timezone.utc)
    reset = await session.scalar(
        select(MerchantPasswordReset).where(MerchantPasswordReset.token_hash == _hash(token)).with_for_update()
    )
    if reset is None or reset.used_at is not None or reset.expires_at <= now:
        raise ValidationError(INVALID_LINK, details=[{"field": "token", "message": INVALID_LINK}])
    account = await session.get(MerchantAccount, reset.account_id)
    if account is None:
        raise ValidationError(INVALID_LINK, details=[{"field": "token", "message": INVALID_LINK}])
    account.password_hash = await hash_password(new_password)
    reset.used_at = now
    # Every other reset link and every signed-in session ends now.
    await session.execute(
        update(MerchantPasswordReset)
        .where(MerchantPasswordReset.account_id == account.id, MerchantPasswordReset.used_at.is_(None))
        .values(used_at=now)
    )
    await session.execute(
        update(MerchantRefreshToken)
        .where(MerchantRefreshToken.account_id == account.id, MerchantRefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    await session.commit()
