"""Add sample automatic offers to the development tenant without changing its catalogue."""

from __future__ import annotations

import asyncio
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal, dispose_engine
from app.coupons.constants import DiscountType
from app.coupons.schemas import CouponCreate
from app.coupons.service import CouponService
from app.tenants.models import Tenant
from app.tenants.repository import TenantRepository

DEMO_OFFERS = (
    CouponCreate(
        code="CLIQ_WELCOME",
        discount_type=DiscountType.PERCENTAGE,
        discount_value=Decimal("15"),
        first_order_only=True,
        is_automatic=True,
    ),
    CouponCreate(
        code="CLIQ_MORE",
        discount_type=DiscountType.PERCENTAGE,
        discount_value=Decimal("20"),
        min_quantity=3,
        is_automatic=True,
    ),
    CouponCreate(
        code="CLIQ_DELIVERY",
        discount_type=DiscountType.FREE_SHIPPING,
        min_order_amount=Decimal("1499"),
        is_automatic=True,
    ),
)


async def seed_demo_offers(session: AsyncSession, tenant: Tenant) -> None:
    """Create missing offers only, preserving any edits made in the admin panel."""
    if get_settings().is_production:
        raise RuntimeError("Demo offers are never seeded in production")

    service = CouponService(session, tenant.id)
    created = 0
    for offer in DEMO_OFFERS:
        if await service.coupons.get_by_code(offer.code) is None:
            await service.create(offer)
            created += 1
    print(f"Demo offers: +{created} (existing offers preserved)")


async def seed() -> None:
    settings = get_settings()
    if settings.is_production:
        raise RuntimeError("Demo offers are never seeded in production")

    try:
        async with AsyncSessionLocal() as session:
            tenant = await TenantRepository(session).get_active_by_slug(
                settings.seed_tenant_slug.strip().lower()
            )
            if tenant is None:
                raise RuntimeError("Seed tenant not found; run app.commands.bootstrap first")
            await seed_demo_offers(session, tenant)
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(seed())
