"""Each brand's own Razorpay account.

Shoppers pay the brand directly: the brand pastes its Razorpay key id, key
secret and webhook secret in its console. Secrets are stored encrypted and
never returned. Brands listed in RAZORPAY_PLATFORM_TENANT_SLUGS (default: the
operator's own seeded store) use the platform's keys from the environment.
"""

from __future__ import annotations

import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core import secret_box
from app.core.config import get_settings
from app.core.error_codes import PaymentErrorCode
from app.core.exceptions import ServiceUnavailableError, ValidationError
from app.models.base import Base, IdMixin, TenantMixin, TimestampMixin
from app.payments import razorpay
from app.tenants.models import Tenant

KEY_ID_PATTERN = re.compile(r"^rzp_(test|live)_[A-Za-z0-9]{6,40}$")


class PaymentGatewayAccount(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "payment_gateway_accounts"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_payment_gateway_accounts_tenant_id"),)

    provider: Mapped[str] = mapped_column(String(20), nullable=False, default="RAZORPAY", server_default="RAZORPAY")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    key_id: Mapped[str] = mapped_column(String(64), nullable=False)
    key_secret_encrypted: Mapped[str] = mapped_column(String(500), nullable=False)
    webhook_secret_encrypted: Mapped[str | None] = mapped_column(String(500), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", name="fk_payment_gateway_accounts_updated_by_users", ondelete="SET NULL"),
        nullable=True,
    )

    @property
    def is_live(self) -> bool:
        return self.key_id.startswith("rzp_live_")


async def _tenant_slug(session: AsyncSession, tenant_id: uuid.UUID) -> str | None:
    return await session.scalar(select(Tenant.slug).where(Tenant.id == tenant_id))


async def uses_platform_keys(session: AsyncSession, tenant_id: uuid.UUID) -> bool:
    return (await _tenant_slug(session, tenant_id)) in get_settings().platform_payment_slugs


async def account_for(session: AsyncSession, tenant_id: uuid.UUID) -> PaymentGatewayAccount | None:
    return await session.scalar(
        select(PaymentGatewayAccount).where(PaymentGatewayAccount.tenant_id == tenant_id)
    )


async def resolve(session: AsyncSession, tenant_id: uuid.UUID) -> razorpay.Scope:
    """The Razorpay account this brand's payments use (or none)."""
    settings = get_settings()
    account = await account_for(session, tenant_id)
    if account is not None and account.is_enabled:
        try:
            secret = secret_box.decrypt(account.key_secret_encrypted)
            webhook = (
                secret_box.decrypt(account.webhook_secret_encrypted)
                if account.webhook_secret_encrypted
                else None
            )
        except secret_box.SecretUnreadable:
            return razorpay.Scope(credentials=None, webhook_secret=None)
        return razorpay.Scope(
            credentials=razorpay.Credentials(
                key_id=account.key_id,
                key_secret=secret,
                api_url=settings.razorpay_api_url.rstrip("/"),
                timeout_seconds=settings.razorpay_timeout_seconds,
            ),
            webhook_secret=webhook,
        )
    if await uses_platform_keys(session, tenant_id):
        return razorpay.Scope(credentials=razorpay.env_credentials(), webhook_secret=settings.razorpay_webhook_secret)
    return razorpay.Scope(credentials=None, webhook_secret=None)


@asynccontextmanager
async def scoped(session: AsyncSession, tenant_id: uuid.UUID):
    """Run Razorpay calls inside with this brand's own account."""
    with razorpay.use_scope(await resolve(session, tenant_id)):
        yield


async def public_key_id(session: AsyncSession, tenant_id: uuid.UUID) -> str | None:
    """What the storefront needs to open Razorpay Checkout (public by design)."""
    scope = await resolve(session, tenant_id)
    return scope.credentials.key_id if scope.credentials else None


async def check_keys(key_id: str, key_secret: str) -> None:
    """Ask Razorpay whether the pair works (a read-only orders listing)."""
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=settings.razorpay_timeout_seconds) as client:
            response = await client.get(
                f"{settings.razorpay_api_url.rstrip('/')}/orders",
                params={"count": 1},
                auth=(key_id, key_secret),
            )
    except httpx.HTTPError as exc:
        raise ServiceUnavailableError(
            "Could not reach Razorpay to check the keys. Try again shortly.",
            error_code=PaymentErrorCode.GATEWAY_UNAVAILABLE,
        ) from exc
    if response.status_code in (401, 403):
        raise ValidationError(
            "Razorpay rejected these keys. Copy the Key Id and Key Secret again from Razorpay Dashboard → Account & Settings → API Keys.",
            error_code=PaymentErrorCode.VERIFICATION_FAILED,
            details=[{"field": "key_secret", "message": "Rejected by Razorpay"}],
        )
    if response.status_code != 200:
        raise ServiceUnavailableError(
            "Razorpay could not check the keys right now. Try again shortly.",
            error_code=PaymentErrorCode.GATEWAY_UNAVAILABLE,
        )


async def save_account(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    key_id: str,
    key_secret: str | None,
    webhook_secret: str | None,
    is_enabled: bool,
    user_id: uuid.UUID | None,
) -> PaymentGatewayAccount:
    key_id = key_id.strip()
    if not KEY_ID_PATTERN.match(key_id):
        raise ValidationError(
            "A Razorpay Key Id looks like rzp_live_XXXXXXXX or rzp_test_XXXXXXXX.",
            details=[{"field": "key_id", "message": "Not a Razorpay Key Id"}],
        )
    account = await account_for(session, tenant_id)
    if key_secret is None or not key_secret.strip():
        if account is None or account.key_id != key_id:
            raise ValidationError(
                "Enter the Key Secret that goes with this Key Id.",
                details=[{"field": "key_secret", "message": "Required"}],
            )
        secret = secret_box.decrypt(account.key_secret_encrypted)
    else:
        secret = key_secret.strip()

    await check_keys(key_id, secret)

    if account is None:
        account = PaymentGatewayAccount(tenant_id=tenant_id, key_id=key_id, key_secret_encrypted="")
    account.key_id = key_id
    account.key_secret_encrypted = secret_box.encrypt(secret)
    if webhook_secret is not None and webhook_secret.strip():
        account.webhook_secret_encrypted = secret_box.encrypt(webhook_secret.strip())
    account.is_enabled = is_enabled
    account.verified_at = datetime.now(timezone.utc)
    account.updated_by_id = user_id
    session.add(account)
    await session.commit()
    await session.refresh(account)
    return account
