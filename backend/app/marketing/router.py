"""Brand console: customers' marketing consent and email campaigns.
Storefront: one-click unsubscribe."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.dependencies import AUDITED
from app.auth.dependencies import require_permission
from app.auth.permissions import Permission
from app.core.database import get_db
from app.core.responses import ApiResponse, ok
from app.marketing import service
from app.marketing.models import EmailCampaign
from app.tenants.resolver import CurrentTenant
from app.users.models import User

router = APIRouter(prefix="/admin/marketing", tags=["Admin-Marketing"], dependencies=AUDITED)
public_router = APIRouter(prefix="/storefront", tags=["Storefront-Marketing"])

CanView = Depends(require_permission(Permission.CUSTOMERS_VIEW, legacy_staff=True))
CanSend = Depends(require_permission(Permission.CUSTOMERS_MANAGE))


class Segment(BaseModel):
    kind: Literal["ALL", "ORDERED_WITHIN", "NO_ORDERS", "TAG"] = "ALL"
    days: int | None = Field(default=None, ge=1, le=3650)
    tag: str | None = Field(default=None, max_length=50)


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=20_000)
    segment: Segment = Segment()

    @field_validator("name", "subject", "body")
    @classmethod
    def _strip(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value.strip()


class CampaignRead(BaseModel):
    id: UUID
    name: str
    subject: str
    body: str
    segment: dict
    status: str
    recipients: int
    sent_at: datetime | None
    created_at: datetime
    audience: int | None = None  # who would get it now (drafts)


class MarketingSummary(BaseModel):
    customers: int
    subscribed: int


async def _read(session: AsyncSession, c: EmailCampaign) -> CampaignRead:
    read = CampaignRead.model_validate(c, from_attributes=True)
    if c.status == "DRAFT":
        read.audience = await service.segment_size(session, c.tenant_id, c.segment)
    return read


@router.get("/summary", response_model=ApiResponse[MarketingSummary], summary="Customers and how many get marketing email")
async def summary(tenant: CurrentTenant, session: AsyncSession = Depends(get_db), user: User = CanView):
    return ok(MarketingSummary(**await service.consent_counts(session, user.tenant_id)), message="Marketing")


@router.post("/audience", response_model=ApiResponse[dict[str, int]], summary="How many customers a segment reaches")
async def audience(segment: Segment, tenant: CurrentTenant, session: AsyncSession = Depends(get_db), user: User = CanView):
    return ok({"count": await service.segment_size(session, user.tenant_id, segment.model_dump())}, message="Audience")


@router.get("/campaigns", response_model=ApiResponse[list[CampaignRead]], summary="Campaigns")
async def list_campaigns(tenant: CurrentTenant, session: AsyncSession = Depends(get_db), user: User = CanView):
    rows = (
        await session.scalars(
            select(EmailCampaign).where(EmailCampaign.tenant_id == user.tenant_id).order_by(EmailCampaign.created_at.desc()).limit(100)
        )
    ).all()
    return ok([await _read(session, c) for c in rows], message="Campaigns")


@router.post("/campaigns", response_model=ApiResponse[CampaignRead], status_code=201, summary="Draft a campaign")
async def create_campaign(data: CampaignCreate, tenant: CurrentTenant, session: AsyncSession = Depends(get_db), user: User = CanSend):
    campaign = EmailCampaign(
        tenant_id=user.tenant_id, name=data.name, subject=data.subject, body=data.body,
        segment=data.segment.model_dump(), created_by_id=user.id,
    )  # fmt: skip
    session.add(campaign)
    await session.commit()
    await session.refresh(campaign)
    return ok(await _read(session, campaign), message="Campaign drafted")


@router.post("/campaigns/{campaign_id}/send", response_model=ApiResponse[CampaignRead], summary="Send a drafted campaign")
async def send_campaign(campaign_id: UUID, tenant: CurrentTenant, session: AsyncSession = Depends(get_db), user: User = CanSend):
    campaign = await service.send_campaign(session, user.tenant_id, campaign_id)
    return ok(await _read(session, campaign), message=f"Sending to {campaign.recipients} customers")


class Unsubscribe(BaseModel):
    u: UUID
    t: str = Field(min_length=8, max_length=64)


@public_router.post("/unsubscribe", response_model=ApiResponse[None], summary="Stop marketing email (link from an email)")
async def unsubscribe(data: Unsubscribe, tenant: CurrentTenant, session: AsyncSession = Depends(get_db)):
    await service.unsubscribe(session, tenant.id, data.u, data.t)
    return ok(None, message="You won't get marketing email from us any more.")
