"""Plans, a brand's subscription, plan limits and the monthly AI allowance.

Brands pay through Razorpay Subscriptions (app.subscriptions.billing); the
platform team can also set a plan by hand (billing_provider = "manual").
A lapsed subscription (cancelled, unpaid past the grace period, or an
unpaid trial) falls back to the Free plan's limits; nothing is deleted.
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
    FALLBACK_PLAN,
    FEATURE_LABELS,
    NEW_BRAND_PLAN,
    PAST_DUE_GRACE_DAYS,
    SubscriptionStatus,
)
from app.subscriptions.models import BrandSubscription, SubscriptionPlan



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


async def start_free(session: AsyncSession, tenant_id: uuid.UUID) -> BrandSubscription:
    """A new brand's subscription (the Free plan). Added to the caller's transaction."""
    plan = await plan_by_code(session, NEW_BRAND_PLAN)
    now = datetime.now(timezone.utc)
    subscription = BrandSubscription(
        tenant_id=tenant_id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE.value,
        current_period_start=now,
        current_period_end=_add_month(now),
    )
    session.add(subscription)
    await session.flush()
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
        # Manual plans roll forward by themselves; Razorpay-billed periods
        # move only when Razorpay reports a charge (webhook).
        if subscription.status == SubscriptionStatus.ACTIVE.value and subscription.billing_provider == "manual":
            rolled = False
            while subscription.current_period_end <= now:
                subscription.current_period_start = subscription.current_period_end
                subscription.current_period_end = _add_month(subscription.current_period_start)
                rolled = True
            await grant_allowance(self.session, self.tenant_id, plan, subscription.current_period_start)
            if rolled:
                await self.session.flush()
        return subscription, plan

    async def effective_plan(self) -> SubscriptionPlan | None:
        """The plan whose limits apply right now (None = unlimited, pre-plan brand)."""
        current = await self.current()
        if current is None:
            return None
        subscription, plan = current
        if lapsed(subscription):
            return await plan_by_code(self.session, FALLBACK_PLAN)
        return plan

    async def require_feature(self, feature: str) -> None:
        plan = await self.effective_plan()
        if plan is None or plan.features.get(feature, False):
            return
        label = FEATURE_LABELS.get(feature, feature)
        raise PermissionDeniedError(
            f"{label} is not included in the {plan.name} plan. Upgrade in Plan & billing.",
            error_code=BillingErrorCode.FEATURE_NOT_IN_PLAN,
        )

    async def check_limit(self, limit_name: str, current_count: int) -> None:
        """Refuse adding one more of something when the plan's limit is reached."""
        plan = await self.effective_plan()
        if plan is None:
            return
        limit = getattr(plan, limit_name)
        if limit is not None and current_count >= limit:
            label = {"product_limit": "products", "staff_limit": "team members", "store_limit": "stores"}.get(
                limit_name, limit_name
            )
            raise PermissionDeniedError(
                f"The {plan.name} plan allows {limit} {label}. Upgrade in Plan & billing to add more.",
                error_code=BillingErrorCode.PLAN_LIMIT_REACHED,
            )

    async def usage(self) -> dict[str, int]:
        from app.brands.constants import MemberStatus
        from app.brands.models import BrandMember
        from app.catalogue.constants import CatalogueStatus
        from app.catalogue.models import Product

        return {
            "products": await count_rows(
                self.session, Product, self.tenant_id, Product.status != CatalogueStatus.ARCHIVED.value
            ),
            "staff": await count_rows(
                self.session, BrandMember, self.tenant_id, BrandMember.status == MemberStatus.ACTIVE.value
            ),
        }

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


def lapsed(subscription: BrandSubscription, now: datetime | None = None) -> bool:
    """Whether the subscription no longer earns its plan's limits."""
    now = now or datetime.now(timezone.utc)
    if subscription.status == SubscriptionStatus.CANCELLED.value:
        return True
    if subscription.status == SubscriptionStatus.PAST_DUE.value:
        since = subscription.past_due_since or subscription.current_period_end
        return now - since > timedelta(days=PAST_DUE_GRACE_DAYS)
    if subscription.status == SubscriptionStatus.TRIALING.value:
        return subscription.current_period_end <= now
    return False


async def count_rows(session: AsyncSession, model, tenant_id: uuid.UUID, *where) -> int:
    return int(
        await session.scalar(select(func.count()).select_from(model).where(model.tenant_id == tenant_id, *where))
        or 0
    )
