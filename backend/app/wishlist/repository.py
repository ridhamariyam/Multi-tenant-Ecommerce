from uuid import UUID

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession  # type: ignore

from app.catalogue.models import Product, ProductVariant
from app.wishlist.models import Wishlist, WishlistItem


class WishlistRepository:
    model = Wishlist

    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id

    async def find_one(self, *criterion) -> Wishlist | None:
        stmt = select(self.model).where(self.model.tenant_id == self.tenant_id, *criterion)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_customer(self, customer_id: UUID) -> Wishlist | None:
        return await self.find_one(Wishlist.customer_id == customer_id)

    async def create(self, wishlist: Wishlist) -> Wishlist:
        self.session.add(wishlist)
        await self.session.flush()
        return wishlist


class WishlistItemRepository:
    model = WishlistItem

    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id

    async def find_one(self, *criterion) -> WishlistItem | None:
        stmt = select(self.model).where(self.model.tenant_id == self.tenant_id, *criterion)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def find(self, *criterion) -> list[WishlistItem]:
        stmt = select(self.model).where(self.model.tenant_id == self.tenant_id, *criterion)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def add(self, item: WishlistItem) -> WishlistItem:
        item.tenant_id = self.tenant_id
        self.session.add(item)
        await self.session.flush()
        return item

    async def get(self, wishlist_id: UUID, variant_id: UUID) -> WishlistItem | None:
        return await self.find_one(
            WishlistItem.wishlist_id == wishlist_id, WishlistItem.variant_id == variant_id
        )

    async def get_by_variant(self, wishlist_id: UUID, variant_id: UUID) -> WishlistItem | None:
        return await self.find_one(
            WishlistItem.wishlist_id == wishlist_id, WishlistItem.variant_id == variant_id
        )

    async def add_item(self, wishlist_id: UUID, variant_id: UUID) -> WishlistItem:
        return await self.add(WishlistItem(wishlist_id=wishlist_id, variant_id=variant_id))

    async def get_item(
        self,
        wishlist_id: UUID,
        item_id: UUID,
    ) -> WishlistItem | None:
        return await self.find_one(
            WishlistItem.wishlist_id == wishlist_id, WishlistItem.id == item_id
        )

    async def clear(self, wishlist_id: UUID) -> int:
        query = delete(WishlistItem).where(
            WishlistItem.tenant_id == self.tenant_id, WishlistItem.wishlist_id == wishlist_id
        )
        result = await self.session.execute(query)
        await self.session.flush()
        return result.rowcount or 0

    async def delete(self, item: WishlistItem) -> None:
        await self.session.delete(item)
        await self.session.flush()

    async def list_with_catalogue(
        self, wishlist_id: UUID
    ) -> list[tuple[WishlistItem, ProductVariant, Product]]:
        stmt = (
            select(WishlistItem, ProductVariant, Product)
            .join(
                ProductVariant,
                and_(
                    ProductVariant.id == WishlistItem.variant_id,
                    ProductVariant.tenant_id == WishlistItem.tenant_id,
                ),
            )
            .join(
                Product,
                and_(
                    Product.id == ProductVariant.product_id,
                    Product.tenant_id == ProductVariant.tenant_id,
                ),
            )
            .where(
                WishlistItem.tenant_id == self.tenant_id, WishlistItem.wishlist_id == wishlist_id
            )
            .order_by(WishlistItem.created_at)
        )
        return list((await self.session.execute(stmt)).all())
