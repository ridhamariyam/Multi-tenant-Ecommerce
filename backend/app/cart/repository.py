from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, delete, select, update

from app.cart.models import Cart, CartItem, CartStatus
from app.catalogue.models import Product, ProductVariant
from app.core.repository import TenantScopedRepository


class CartRepository(TenantScopedRepository[Cart]):
    model = Cart

    async def get_active(self, customer_id: UUID) -> Cart | None:
        return await self.find_one(
            Cart.customer_id == customer_id,
            Cart.status == CartStatus.ACTIVE.value,
        )

    async def get_active_guest(self, token_hash: str) -> Cart | None:
        return await self.find_one(
            Cart.guest_token_hash == token_hash,
            Cart.status == CartStatus.ACTIVE.value,
        )

    async def create(
        self, customer_id: UUID | None = None, *, guest_token_hash: str | None = None
    ) -> Cart:
        return await self.add(
            Cart(
                customer_id=customer_id,
                guest_token_hash=guest_token_hash,
                status=CartStatus.ACTIVE.value,
            )
        )


async def expire_stale_carts(session, cutoff: datetime) -> int:
    """Expire every ACTIVE cart idle since before `cutoff`, across all tenants.

    Items go first so an expired cart holds nothing; the cart row stays as
    a record. Returns how many carts were expired. The caller commits.
    """
    stale = select(Cart.id).where(
        Cart.status == CartStatus.ACTIVE.value, Cart.last_activity_at < cutoff
    )
    await session.execute(delete(CartItem).where(CartItem.cart_id.in_(stale)))
    result = await session.execute(
        update(Cart)
        .where(Cart.status == CartStatus.ACTIVE.value, Cart.last_activity_at < cutoff)
        .values(status=CartStatus.EXPIRED.value)
    )
    return result.rowcount or 0


class CartItemRepository(TenantScopedRepository[CartItem]):
    model = CartItem

    async def get_item(self, cart_id: UUID, item_id: UUID) -> CartItem | None:
        return await self.find_one(CartItem.cart_id == cart_id, CartItem.id == item_id)

    async def get_by_variant(self, cart_id: UUID, variant_id: UUID) -> CartItem | None:
        return await self.find_one(
            CartItem.cart_id == cart_id, CartItem.variant_id == variant_id
        )

    async def add_item(self, cart_id: UUID, variant_id: UUID, quantity: int) -> CartItem:
        return await self.add(
            CartItem(cart_id=cart_id, variant_id=variant_id, quantity=quantity)
        )

    async def clear(self, cart_id: UUID) -> int:
        result = await self.session.execute(
            delete(CartItem).where(
                CartItem.tenant_id == self.tenant_id, CartItem.cart_id == cart_id
            )
        )
        await self.session.flush()
        return result.rowcount or 0

    async def list_with_catalogue(
        self, cart_id: UUID
    ) -> list[tuple[CartItem, ProductVariant, Product]]:
        """Every cart line joined to the variant and product it points at, in one query."""
        stmt = (
            select(CartItem, ProductVariant, Product)
            .join(
                ProductVariant,
                and_(
                    ProductVariant.id == CartItem.variant_id,
                    ProductVariant.tenant_id == CartItem.tenant_id,
                ),
            )
            .join(
                Product,
                and_(
                    Product.id == ProductVariant.product_id,
                    Product.tenant_id == ProductVariant.tenant_id,
                ),
            )
            .where(CartItem.tenant_id == self.tenant_id, CartItem.cart_id == cart_id)
            .order_by(CartItem.created_at)
        )
        return list((await self.session.execute(stmt)).all())
