from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalogue.repository import ProductImageRepository
from app.catalogue.schemas import ProductImageSummary
from app.catalogue.service import get_sellable_variant
from app.core.database import conflict_on_integrity_error
from app.core.exceptions import ConflictError, NotFoundError
from app.wishlist.models import Wishlist
from app.wishlist.repository import WishlistItemRepository, WishlistRepository
from app.wishlist.schemas import (
    WishListItemCreate,
    WishListItemRead,
    WishListRead,
)

ITEM_NOT_FOUND = "Wishlist item not found"
WISHLIST_ITEM_EXISTS = "Item already in wishlist"


class WishListService:
    def __init__(self, session: AsyncSession, tenant_id: UUID, customer_id: UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.customer_id = customer_id
        self.wishlists = WishlistRepository(session, tenant_id)
        self.items = WishlistItemRepository(session, tenant_id)
        self.images = ProductImageRepository(session, tenant_id)

    async def get_or_create_wishlist(self) -> Wishlist:
        wishlist = await self.wishlists.get_by_customer(customer_id=self.customer_id)
        if wishlist is not None:
            return wishlist
        try:
            wishlist = await self.wishlists.create(
                Wishlist(tenant_id=self.tenant_id, customer_id=self.customer_id)
            )
            await self.session.commit()
            return wishlist
        except IntegrityError:
            await self.session.rollback()
            existing = await self.wishlists.get_by_customer(self.customer_id)
            if existing is None:
                raise
            return existing

    async def render(self, wishlist: Wishlist) -> WishListRead:
        rows = await self.items.list_with_catalogue(wishlist.id)
        images = await self.images.primary_for([product.id for _item, _variant, product in rows])
        items: list[WishListItemRead] = []
        for item, variant, product in rows:
            items.append(
                WishListItemRead(
                    id=item.id,
                    variant_id=variant.id,
                    product_id=product.id,
                    product_name=product.name,
                    variant_name=variant.name,
                    sku=variant.sku,
                    unit_price=variant.price,
                    image=_summary(images.get(product.id)),
                )
            )
        return WishListRead(id=wishlist.id, items=items, item_count=len(items))

    async def view(self) -> WishListRead:
        wishlist = await self.get_or_create_wishlist()
        return await self.render(wishlist)

    async def add_item(self, data: WishListItemCreate) -> WishListRead:
        wishlist = await self.get_or_create_wishlist()
        await get_sellable_variant(self.session, self.tenant_id, data.variant_id)
        existing = await self.items.get_by_variant(wishlist.id, data.variant_id)
        if existing is not None:
            raise ConflictError(WISHLIST_ITEM_EXISTS)
        async with conflict_on_integrity_error(self.session, WISHLIST_ITEM_EXISTS):
            await self.items.add_item(wishlist.id, data.variant_id)
            await self.session.commit()
        return await self.render(wishlist)

    async def remove_item(self, item_id: UUID) -> WishListRead:
        wishlist = await self.get_or_create_wishlist()
        item = await self.items.get_item(wishlist.id, item_id)
        if item is None:
            raise NotFoundError(ITEM_NOT_FOUND)
        await self.items.delete(item)
        await self.session.commit()
        return await self.render(wishlist)

    async def clear(self) -> WishListRead:
        wishlist = await self.get_or_create_wishlist()
        await self.items.clear(wishlist.id)
        await self.session.commit()
        return await self.render(wishlist)


def _summary(image) -> ProductImageSummary | None:
    return ProductImageSummary.model_validate(image) if image is not None else None
