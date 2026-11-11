"""Plans, a brand's subscription, plan limits and the monthly AI allowance.

No billing provider is connected: plans change only by a platform admin and
no money moves (billing_provider = "manual"). Responses say so.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.constants import LedgerEntry
from app.ai.models import AiUsageLedger
from app.core.error_codes import BillingErrorCode
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.subscriptions.constants import (
    DEFAULT_PLANS,
    NEW_BRAND_PLAN,
    TRIAL_DAYS,
    SubscriptionStatus,
)
from app.subscriptions.models import BrandSubscription, SubscriptionPlan

BILLING_NOTICE = (
    "Billing is not connected yet: plans are assigned by the platform team and no "
    "payment is taken."
)


def _add_month(moment: datetime) -> datetime:
    year, month = (moment.year + 1, 1) if moment.month == 12 else (moment.year, moment.month + 1)
    day = min(moment.day, 28)
    return moment.replace(year=year, month=month, day=day)


async def ensure_default_plans(session: AsyncSession) -> None:
    """Create any missing default plan (the migration does this for real databases)."""
    for plan in DEFAULT_PLANS:
        await session.execute(
            insert(SubscriptionPlan).values(id=uuid.uuid4(), **plan).on_conflict_do_nothing(
                index_elements=["code"]
            )
        )


async def plan_by_code(session: AsyncSession, code: str) -> SubscriptionPlan:
    plan = await session.scalar(select(SubscriptionPlan).where(SubscriptionPlan.code == code))
    if plan is None:
        await ensure_default_plans(session)
        plan = await session.scalar(select(SubscriptionPlan).where(SubscriptionPlan.code == code))
    if plan is None:
        raise NotFoundError("Unknown plan", error_code=BillingErrorCode.PLAN_NOT_FOUND)
    return plan


async def start_trial(session: AsyncSession, tenant_id: uuid.UUID) -> BrandSubscription:
    """A new brand's subscription. Added to the caller's transaction, not committed."""
    plan = await plan_by_code(session, NEW_BRAND_PLAN)
    now = datetime.now(timezone.utc)
    subscription = BrandSubscription(
        tenant_id=tenant_id,
        plan_id=plan.id,
        status=SubscriptionStatus.TRIALING.value,
        current_period_start=now,
        current_period_end=now + timedelta(days=TRIAL_DAYS),
    )
    session.add(subscription)
    await session.flush()
    await grant_allowance(session, tenant_id, plan, subscription.current_period_start)
    return subscription


async def grant_allowance(
    session: AsyncSession, tenant_id: uuid.UUID, plan: SubscriptionPlan, period_start: datetime
) -> None:
    """The plan's AI credits for one period, at most once (unique reference)."""
    if plan.monthly_ai_credits <= 0:
        return
    await session.execute(
        insert(AiUsageLedger)
        .values(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            entry_type=LedgerEntry.GRANT.value,
            credits=plan.monthly_ai_credits,
            reference=f"plan:{plan.code}:{period_start.date().isoformat()}",
            note=f"{plan.name} allowance",
        )
        .on_conflict_do_nothing(constraint="uq_ai_usage_ledger_reference")
    )


class SubscriptionService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id

    async def current(self) -> tuple[BrandSubscription, SubscriptionPlan] | None:
        """The subscription, rolled forward to the current period (granting its allowance).

        None for a brand that predates plans and was never given one: such a
        brand is not limited (the migration gives every existing brand one).
        """
        row = (
            await self.session.execute(
                select(BrandSubscription, SubscriptionPlan)
                .join(SubscriptionPlan, SubscriptionPlan.id == BrandSubscription.plan_id)
                .where(BrandSubscription.tenant_id == self.tenant_id)
            )
        ).one_or_none()
        if row is None:
            return None
        subscription, plan = row
        now = datetime.now(timezone.utc)
        if subscription.status == SubscriptionStatus.ACTIVE.value:
            rolled = False
            while subscription.current_period_end <= now:
                subscription.current_period_start = subscription.current_period_end
                subscription.current_period_end = _add_month(subscription.current_period_start)
                rolled = True
            await grant_allowance(self.session, self.tenant_id, plan, subscription.current_period_start)
            if rolled:
                await self.session.flush()
        return subscription, plan

    async def require_feature(self, feature: str) -> None:
        current = await self.current()
        if current is None:
            return
        subscription, plan = current
        if subscription.status in {SubscriptionStatus.CANCELLED.value, SubscriptionStatus.PAST_DUE.value}:
            raise PermissionDeniedError(
                "This brand's subscription is not active", error_code=BillingErrorCode.FEATURE_NOT_IN_PLAN
            )
        if subscription.status == SubscriptionStatus.TRIALING.value and subscription.current_period_end <= datetime.now(timezone.utc):
            raise PermissionDeniedError(
                "The free trial has ended. Ask the platform team to choose a plan.",
                error_code=BillingErrorCode.FEATURE_NOT_IN_PLAN,
            )
        if not plan.features.get(feature, False):
            raise PermissionDeniedError(
                f"The {plan.name} plan does not include this feature",
                error_code=BillingErrorCode.FEATURE_NOT_IN_PLAN,
            )

    async def check_limit(self, limit_name: str, current_count: int) -> None:
        """Refuse adding one more of something when the plan's limit is reached."""
        current = await self.current()
        if current is None:
            return
        _, plan = current
        limit = getattr(plan, limit_name)
        if limit is not None and current_count >= limit:
            label = limit_name.removesuffix("_limit")
            raise PermissionDeniedError(
                f"The {plan.name} plan allows {limit} {label}s. Upgrade to add more.",
                error_code=BillingErrorCode.PLAN_LIMIT_REACHED,
            )

    async def change_plan(self, plan_code: str, status: SubscriptionStatus) -> BrandSubscription:
        plan = await plan_by_code(self.session, plan_code)
        now = datetime.now(timezone.utc)
        subscription = await self.session.scalar(
            select(BrandSubscription).where(BrandSubscription.tenant_id == self.tenant_id)
        )
        if subscription is None:
            subscription = BrandSubscription(
                tenant_id=self.tenant_id, plan_id=plan.id, status=status.value,
                current_period_start=now, current_period_end=_add_month(now),
            )  # fmt: skip
            self.session.add(subscription)
        else:
            if subscription.plan_id != plan.id:
                subscription.current_period_start = now
                subscription.current_period_end = _add_month(now)
            subscription.plan_id = plan.id
            subscription.status = status.value
        await self.session.flush()
        if status in {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING}:
            await grant_allowance(self.session, self.tenant_id, plan, subscription.current_period_start)
        await self.session.commit()
        await self.session.refresh(subscription)
        return subscription


async def count_rows(session: AsyncSession, model, tenant_id: uuid.UUID, *where) -> int:
    return int(
        await session.scalar(select(func.count()).select_from(model).where(model.tenant_id == tenant_id, *where))
        or 0
    )
