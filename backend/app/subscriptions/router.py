"""Plan & billing for brands; plan administration for platform operators."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_platform_action
from app.brands.dependencies import BrandManager
from app.core.config import get_settings
from app.core.database import get_db
from app.core.error_codes import BrandErrorCode
from app.core.exceptions import NotFoundError
from app.core.responses import ApiResponse, ok
from app.merchants.dependencies import PlatformAdmin
from app.subscriptions import billing
from app.subscriptions.constants import FEATURES, SubscriptionStatus
from app.subscriptions.models import SubscriptionPlan
from app.subscriptions.service import SubscriptionService, gross_amount, lapsed, plan_by_code
from app.tenants.models import Tenant
from app.tenants.resolver import CurrentTenant

router = APIRouter(tags=["Billing"])


class PlanRead(BaseModel):
    code: str
    name: str
    monthly_price: int  # paise, before GST
    monthly_price_with_gst: int  # paise, what Razorpay charges
    currency: str
    monthly_ai_credits: int
    product_limit: int | None
    staff_limit: int | None
    features: dict[str, bool]
    is_active: bool


class SubscriptionRead(BaseModel):
    status: str
    billing_provider: str
    current_period_start: datetime
    current_period_end: datetime
    cancel_at_period_end: bool
    trial_used: bool
    lapsed: bool


class BillingRead(BaseModel):
    plan: PlanRead | None
    effective_plan: PlanRead | None
    subscription: SubscriptionRead | None
    # The storefront is closed to the public until the brand pays.
    paused: bool
    trial_ends_at: datetime | None
    trial_days_left: int | None
    gst_percent: int
    usage: dict[str, int]
    plans: list[PlanRead]
    online_billing: bool


class CheckoutCreate(BaseModel):
    plan_code: str = Field(min_length=2, max_length=30)


class CheckoutConfirm(BaseModel):
    razorpay_payment_id: str = Field(min_length=4, max_length=64)
    razorpay_subscription_id: str = Field(min_length=4, max_length=64)
    razorpay_signature: str = Field(min_length=16, max_length=200)


def plan_read(plan: SubscriptionPlan | None) -> PlanRead | None:
    if plan is None:
        return None
    return PlanRead(
        code=plan.code, name=plan.name, monthly_price=plan.monthly_price,
        monthly_price_with_gst=gross_amount(plan.monthly_price), currency=plan.currency,
        monthly_ai_credits=plan.monthly_ai_credits, product_limit=plan.product_limit,
        staff_limit=plan.staff_limit, features={f: bool(plan.features.get(f)) for f in FEATURES},
        is_active=plan.is_active,
    )  # fmt: skip


async def _billing_read(session: AsyncSession, tenant_id: UUID) -> BillingRead:
    data = await billing.overview(session, tenant_id)
    sub = data["subscription"]
    now = datetime.now(timezone.utc)
    trialing = sub is not None and sub.status == SubscriptionStatus.TRIALING.value
    trial_end = sub.current_period_end if trialing else None
    return BillingRead(
        paused=bool(sub) and lapsed(sub),
        trial_ends_at=trial_end,
        trial_days_left=max(0, math.ceil((trial_end - now).total_seconds() / 86400)) if trial_end else None,
        gst_percent=get_settings().platform_gst_percent,
        plan=plan_read(data["plan"]),
        effective_plan=plan_read(data["effective_plan"]),
        subscription=SubscriptionRead(
            status=sub.status, billing_provider=sub.billing_provider,
            current_period_start=sub.current_period_start, current_period_end=sub.current_period_end,
            cancel_at_period_end=sub.cancel_at_period_end, trial_used=sub.trial_used, lapsed=lapsed(sub),
        ) if sub else None,  # fmt: skip
        usage=data["usage"],
        plans=[plan_read(p) for p in data["plans"]],
        online_billing=data["online_billing"],
    )


@router.get("/brand/billing", response_model=ApiResponse[BillingRead], summary="This brand's plan, usage and plans")
async def get_billing(tenant: CurrentTenant, user: BrandManager, session: AsyncSession = Depends(get_db)):
    return ok(await _billing_read(session, tenant.id), message="Billing")


@router.post("/brand/billing/checkout", response_model=ApiResponse[dict[str, Any]], summary="Start paying for a plan")
async def checkout(data: CheckoutCreate, tenant: CurrentTenant, user: BrandManager, session: AsyncSession = Depends(get_db)):
    return ok(await billing.start_checkout(session, tenant, data.plan_code), message="Checkout ready")


@router.post("/brand/billing/confirm", response_model=ApiResponse[BillingRead], summary="Confirm an authorised subscription")
async def confirm(data: CheckoutConfirm, tenant: CurrentTenant, user: BrandManager, session: AsyncSession = Depends(get_db)):
    await billing.confirm_checkout(
        session, tenant.id, payment_id=data.razorpay_payment_id,
        subscription_id=data.razorpay_subscription_id, signature=data.razorpay_signature,
    )  # fmt: skip
    return ok(await _billing_read(session, tenant.id), message="Plan updated")


@router.post("/brand/billing/cancel", response_model=ApiResponse[BillingRead], summary="Stop renewing the paid plan")
async def cancel(tenant: CurrentTenant, user: BrandManager, session: AsyncSession = Depends(get_db)):
    await billing.cancel(session, tenant.id)
    return ok(await _billing_read(session, tenant.id), message="Subscription cancelled")


@router.post("/billing/razorpay/webhook", response_model=ApiResponse[dict[str, str]], summary="Razorpay subscription events")
async def webhook(
    request: Request,
    signature: str | None = Header(default=None, alias="X-Razorpay-Signature"),
    event_id: str | None = Header(default=None, alias="X-Razorpay-Event-Id"),
    session: AsyncSession = Depends(get_db),
):
    result = await billing.handle_webhook(session, await request.body(), signature, event_id)
    return ok({"result": result}, message="Webhook received")


# ------------------------------------------------------------ platform operators


class PlanUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    monthly_price: int = Field(ge=0, le=100_000_000)
    monthly_ai_credits: int = Field(ge=0, le=1_000_000)
    product_limit: int | None = Field(default=None, ge=0)
    staff_limit: int | None = Field(default=None, ge=1)
    features: dict[str, bool]
    is_active: bool


class AssignPlan(BaseModel):
    plan_code: str = Field(min_length=2, max_length=30)


@router.get("/platform/admin/plans", response_model=ApiResponse[list[PlanRead]], summary="Every plan")
async def list_plans(admin: PlatformAdmin, session: AsyncSession = Depends(get_db)):
    plans = (await session.scalars(select(SubscriptionPlan).order_by(SubscriptionPlan.sort_order))).all()
    return ok([plan_read(p) for p in plans], message="Plans")


@router.put("/platform/admin/plans/{code}", response_model=ApiResponse[PlanRead], summary="Edit a plan")
async def update_plan(code: str, data: PlanUpdate, admin: PlatformAdmin, session: AsyncSession = Depends(get_db)):
    plan = await plan_by_code(session, code)
    if data.monthly_price != plan.monthly_price:
        # Razorpay plans have a fixed amount: the next checkout creates a new one.
        # Brands already subscribed keep their current price until they change plan.
        plan.razorpay_plan_id = None
    plan.name, plan.monthly_price, plan.monthly_ai_credits = data.name, data.monthly_price, data.monthly_ai_credits
    plan.product_limit, plan.staff_limit, plan.is_active = data.product_limit, data.staff_limit, data.is_active
    plan.features = {f: bool(data.features.get(f)) for f in FEATURES}
    await session.commit()
    return ok(plan_read(plan), message="Plan saved")


@router.put("/platform/admin/brands/{brand_id}/plan", response_model=ApiResponse[PlanRead], summary="Put a brand on a plan by hand")
async def assign_plan(
    brand_id: UUID, data: AssignPlan, request: Request, admin: PlatformAdmin, session: AsyncSession = Depends(get_db)
):
    tenant = await session.get(Tenant, brand_id)
    if tenant is None:
        raise NotFoundError("Brand not found", error_code=BrandErrorCode.NOT_FOUND)
    plan = await plan_by_code(session, data.plan_code)
    await SubscriptionService(session, brand_id).change_plan(plan.code, SubscriptionStatus.ACTIVE)
    await record_platform_action(
        session, brand_id, admin.email, "plan.assigned", "subscription", brand_id,
        summary=f"Plan set to {plan.name} by the platform team", request=request,
    )  # fmt: skip
    await session.commit()
    return ok(plan_read(plan), message="Plan assigned")
