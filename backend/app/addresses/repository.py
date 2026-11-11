from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, update

from app.addresses.models import Address
from app.core.repository import TenantScopedRepository


class AddressRepository(TenantScopedRepository[Address]):
    model = Address

    def list_select(self, customer_id: UUID) -> Select[tuple[Address]]:
        return (
            self.base_select()
            .where(Address.customer_id == customer_id)
            .order_by(Address.is_default.desc(), Address.created_at)
        )

    async def get_for_customer(
        self, customer_id: UUID, address_id: UUID
    ) -> Address | None:
        """Fetch an address scoped to the customer as well as the tenant."""
        return await self.find_one(
            Address.id == address_id, Address.customer_id == customer_id
        )

    async def clear_default(
        self, customer_id: UUID, *, exclude_id: UUID | None = None
    ) -> None:
        """Demote whichever address is currently the default, if any."""
        conditions = [
            Address.tenant_id == self.tenant_id,
            Address.customer_id == customer_id,
            Address.is_default.is_(True),
        ]
        if exclude_id is not None:
            conditions.append(Address.id != exclude_id)

        await self.session.execute(
            update(Address).where(*conditions).values(is_default=False)
        )
        await self.session.flush()

    async def has_any(self, customer_id: UUID) -> bool:
        return await self.find_one(Address.customer_id == customer_id) is not None
