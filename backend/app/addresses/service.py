from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.addresses.models import Address
from app.addresses.repository import AddressRepository
from app.addresses.schemas import AddressCreate, AddressUpdate
from app.core.database import conflict_on_integrity_error
from app.core.exceptions import NotFoundError

ADDRESS_NOT_FOUND = "Address not found"


class AddressService:
    """A customer's delivery addresses, scoped to one customer and tenant."""

    def __init__(self, session: AsyncSession, tenant_id: UUID, customer_id: UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.customer_id = customer_id
        self.addresses = AddressRepository(session, tenant_id)

    async def get(self, address_id: UUID) -> Address:
        address = await self.addresses.get_for_customer(self.customer_id, address_id)
        if address is None:
            raise NotFoundError(ADDRESS_NOT_FOUND)
        return address

    async def list(self) -> list[Address]:
        rows = await self.session.scalars(self.addresses.list_select(self.customer_id))
        return list(rows.all())

    async def create(self, data: AddressCreate) -> Address:
        is_default = data.is_default or not await self.addresses.has_any(self.customer_id)

        async with conflict_on_integrity_error(self.session, "Unable to save the address"):
            if is_default:
                await self.addresses.clear_default(self.customer_id)

            address = Address(
                customer_id=self.customer_id,
                full_name=data.full_name,
                phone=data.phone,
                address_line_1=data.address_line_1,
                address_line_2=data.address_line_2,
                city=data.city,
                state=data.state,
                postal_code=data.postal_code,
                country=data.country,
                is_default=is_default,
            )
            await self.addresses.add(address)
            await self.session.commit()

        return address

    async def update(self, address_id: UUID, data: AddressUpdate) -> Address:
        address = await self.get(address_id)
        changes = data.model_dump(exclude_unset=True)

        make_default = changes.pop("is_default", None)

        for field, value in changes.items():
            setattr(address, field, value)

        async with conflict_on_integrity_error(self.session, "Unable to save the address"):
            if make_default is True:
                await self.addresses.clear_default(
                    self.customer_id, exclude_id=address.id
                )
                address.is_default = True
            elif make_default is False:
                address.is_default = False

            await self.session.commit()

        return address

    async def delete(self, address_id: UUID) -> None:
        """Delete the address; orders keep their own copy of it."""
        address = await self.get(address_id)

        await self.addresses.delete(address)
        await self.session.commit()

