from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, delete, func, select

from app.core.repository import TenantScopedRepository
from app.coupons.models import Coupon, CouponCategory, CouponUsage


class CouponRepository(TenantScopedRepository[Coupon]):
    model = Coupon

    async def live_automatic(self) -> list[Coupon]:
        """Active automatic discounts; date and usage rules are checked by the service."""
        rows = await self.session.scalars(
            self.base_select()
            .where(Coupon.is_active.is_(True), Coupon.is_automatic.is_(True))
            .order_by(Coupon.created_at)
        )
        return list(rows.all())

    def list_select(self, *, active_only: bool = False) -> Select[tuple[Coupon]]:
        stmt = self.base_select()
        if active_only:
            stmt = stmt.where(Coupon.is_active.is_(True))
        return stmt.order_by(Coupon.created_at.desc())

    async def get_by_code(self, code: str) -> Coupon | None:
        return await self.find_one(Coupon.code == code.upper())

    async def get_by_code_for_update(self, code: str) -> Coupon | None:
        stmt = (
            self.base_select()
            .where(func.upper(Coupon.code) == code.upper())
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return await self.session.scalar(stmt)


class CouponUsageRepository(TenantScopedRepository[CouponUsage]):
    model = CouponUsage

    async def count_for_customer(self, coupon_id: UUID, customer_id: UUID) -> int:
        stmt = select(func.count()).select_from(CouponUsage).where(
            CouponUsage.tenant_id == self.tenant_id,
            CouponUsage.coupon_id == coupon_id,
            CouponUsage.customer_id == customer_id,
        )
        return await self.session.scalar(stmt)


class CouponCategoryRepository(TenantScopedRepository[CouponCategory]):
    model = CouponCategory

    async def ids_for(self, coupon_id: UUID) -> list[UUID]:
        rows = await self.session.scalars(
            select(CouponCategory.category_id).where(
                CouponCategory.tenant_id == self.tenant_id,
                CouponCategory.coupon_id == coupon_id,
            )
        )
        return list(rows.all())

    async def replace(self, coupon_id: UUID, category_ids: list[UUID]) -> None:
        await self.session.execute(
            delete(CouponCategory).where(
                CouponCategory.tenant_id == self.tenant_id,
                CouponCategory.coupon_id == coupon_id,
            )
        )
        for category_id in category_ids:
            self.session.add(
                CouponCategory(
                    tenant_id=self.tenant_id, coupon_id=coupon_id, category_id=category_id
                )
            )
        await self.session.flush()
