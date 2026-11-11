from __future__ import annotations

from sqlalchemy import Select

from app.core.repository import TenantScopedRepository
from app.pricing.models import GstSettings, PincodeRule, ShippingSettings, TaxSettings


class ShippingSettingsRepository(TenantScopedRepository[ShippingSettings]):
    model = ShippingSettings

    async def get_for_tenant(self) -> ShippingSettings | None:
        """The tenant's one row, if they have configured delivery at all."""
        return await self.session.scalar(self.base_select())


class TaxSettingsRepository(TenantScopedRepository[TaxSettings]):
    model = TaxSettings

    async def get_for_tenant(self) -> TaxSettings | None:
        return await self.session.scalar(self.base_select())


class PincodeRuleRepository(TenantScopedRepository[PincodeRule]):
    model = PincodeRule

    async def get_by_pincode(self, pincode: str) -> PincodeRule | None:
        return await self.find_one(PincodeRule.pincode == pincode)

    def list_select(
        self, *, search: str | None = None, is_serviceable: bool | None = None
    ) -> Select[tuple[PincodeRule]]:
        stmt = self.base_select()
        if search:
            stmt = stmt.where(PincodeRule.pincode.startswith(search.strip()))
        if is_serviceable is not None:
            stmt = stmt.where(PincodeRule.is_serviceable.is_(is_serviceable))
        return stmt.order_by(PincodeRule.pincode)


class GstSettingsRepository(TenantScopedRepository[GstSettings]):
    model = GstSettings

    async def get_for_tenant(self) -> GstSettings | None:
        return await self.session.scalar(self.base_select())
