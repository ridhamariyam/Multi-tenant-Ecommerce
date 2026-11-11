"""A brand connects its own Razorpay account (Settings → Payments)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.dependencies import AUDITED
from app.auth.dependencies import require_permission
from app.auth.permissions import Permission
from app.core.config import get_settings
from app.core.database import get_db
from app.core.responses import ApiResponse, ok
from app.payments import gateway
from app.tenants.resolver import CurrentTenant
from app.users.models import User

router = APIRouter(prefix="/admin/payment-gateway", tags=["Admin-Payments"], dependencies=AUDITED)


class GatewayRead(BaseModel):
    # "own": the brand's Razorpay account; "platform": the operator's (own store only);
    # "none": online payment is off until the brand connects an account.
    source: str
    connected: bool
    is_enabled: bool
    key_id: str | None
    mode: str | None  # "live" | "test"
    has_webhook_secret: bool
    verified_at: datetime | None
    webhook_url: str


class GatewayUpdate(BaseModel):
    key_id: str = Field(min_length=8, max_length=64)
    # Leave empty to keep the stored secret (same key id only).
    key_secret: str | None = Field(default=None, max_length=200)
    webhook_secret: str | None = Field(default=None, max_length=200)
    is_enabled: bool = True


def webhook_url(tenant_id) -> str:
    settings = get_settings()
    base = (settings.public_api_url or f"https://api.{settings.platform_root_domain}").rstrip("/")
    return f"{base}{settings.api_v1_prefix}/payments/razorpay/webhook/{tenant_id}"


async def _read(session: AsyncSession, tenant_id) -> GatewayRead:
    account = await gateway.account_for(session, tenant_id)
    if account is not None:
        return GatewayRead(
            source="own",
            connected=account.is_enabled,
            is_enabled=account.is_enabled,
            key_id=account.key_id,
            mode="live" if account.is_live else "test",
            has_webhook_secret=account.webhook_secret_encrypted is not None,
            verified_at=account.verified_at,
            webhook_url=webhook_url(tenant_id),
        )
    platform = await gateway.uses_platform_keys(session, tenant_id)
    key_id = get_settings().razorpay_key_id if platform else None
    return GatewayRead(
        source="platform" if platform else "none",
        connected=bool(platform and key_id),
        is_enabled=bool(platform and key_id),
        key_id=key_id,
        mode=("live" if key_id.startswith("rzp_live_") else "test") if key_id else None,
        has_webhook_secret=bool(platform and get_settings().razorpay_webhook_secret),
        verified_at=None,
        webhook_url=webhook_url(tenant_id),
    )


@router.get("", response_model=ApiResponse[GatewayRead], summary="This store's Razorpay account")
async def get_gateway(
    tenant: CurrentTenant,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.SETTINGS_VIEW, legacy_staff=True)),
) -> ApiResponse[GatewayRead]:
    return ok(await _read(session, user.tenant_id), message="Payment gateway")


@router.put("", response_model=ApiResponse[GatewayRead], summary="Connect or update the Razorpay account")
async def put_gateway(
    data: GatewayUpdate,
    tenant: CurrentTenant,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.SETTINGS_MANAGE)),
) -> ApiResponse[GatewayRead]:
    await gateway.save_account(
        session,
        user.tenant_id,
        key_id=data.key_id,
        key_secret=data.key_secret,
        webhook_secret=data.webhook_secret,
        is_enabled=data.is_enabled,
        user_id=user.id,
    )
    return ok(await _read(session, user.tenant_id), message="Razorpay account connected")


@router.delete("", response_model=ApiResponse[GatewayRead], summary="Disconnect the Razorpay account")
async def delete_gateway(
    tenant: CurrentTenant,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.SETTINGS_MANAGE)),
) -> ApiResponse[GatewayRead]:
    account = await gateway.account_for(session, user.tenant_id)
    if account is not None:
        await session.delete(account)
        await session.commit()
    return ok(await _read(session, user.tenant_id), message="Razorpay account disconnected")
