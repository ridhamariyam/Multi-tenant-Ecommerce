from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.cart.models import Cart, CartStatus
from app.cart.repository import CartItemRepository, CartRepository
from app.cart.schemas import CartItemCreate, CartItemRead, CartItemUpdate, CartRead
from app.catalogue.constants import CatalogueStatus
from app.catalogue.prices import effective_price
from app.catalogue.repository import ProductImageRepository
from app.catalogue.schemas import ProductImageSummary
from app.catalogue.serializers import sellable_quantity
from app.catalogue.service import InventoryService, get_sellable_variant
from app.core.config import get_settings
from app.core.error_codes import CartErrorCode, InventoryErrorCode
from app.core.exceptions import ConflictError, NotFoundError

ITEM_NOT_FOUND = "Cart item not found"
GUEST_CART_NOT_FOUND = "Cart not found or expired"


def hash_guest_token(token: str) -> str:
    """Only the hash is stored, so a database leak does not hand out carts."""
    return hashlib.sha256(token.encode()).hexdigest()


def new_guest_token() -> str:
    return secrets.token_urlsafe(32)


def retention_period() -> timedelta:
    return timedelta(days=get_settings().cart_retention_days)


def is_expired(cart: Cart, now: datetime | None = None) -> bool:
    moment = now or datetime.now(timezone.utc)
    return cart.last_activity_at is not None and cart.last_activity_at < moment - retention_period()


class CartService:
    """Cart operations for a customer or a guest; adding never reserves stock.

    Exactly one of `customer_id` and `guest_token` identifies the cart.
    """

    def __init__(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        customer_id: UUID | None = None,
        *,
        guest_token: str | None = None,
    ) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.customer_id = customer_id
        self.guest_token = guest_token

        self.carts = CartRepository(session, tenant_id)
        self.items = CartItemRepository(session, tenant_id)
        self.images = ProductImageRepository(session, tenant_id)
        self.inventory = InventoryService(session, tenant_id)

    # ------------------------------------------------------------------ carts

    async def create_guest_cart(self) -> CartRead:
        """Start a cart for a shopper who has not signed in."""
        token = new_guest_token()
        cart = await self.carts.create(guest_token_hash=hash_guest_token(token))
        await self.session.commit()

        rendered = await self._render(cart)
        return rendered.model_copy(update={"guest_token": token})

    async def get_or_create_cart(self) -> Cart:
        """The caller's active cart. A customer gets one on first use; a guest must have one."""
        if self.customer_id is None:
            return await self._guest_cart()

        cart = await self.carts.get_active(self.customer_id)
        if cart is not None and not await self._expire_if_stale(cart):
            return cart

        try:
            cart = await self.carts.create(self.customer_id)
            await self.session.commit()
            return cart
        except IntegrityError:
            await self.session.rollback()
            existing = await self.carts.get_active(self.customer_id)
            if existing is None:
                raise
            return existing

    async def active_cart(self) -> Cart | None:
        """The caller's live cart without creating one (for checkout)."""
        if self.customer_id is None:
            return await self._guest_cart()

        cart = await self.carts.get_active(self.customer_id)
        if cart is None or await self._expire_if_stale(cart):
            return None
        return cart

    async def _guest_cart(self) -> Cart:
        if not self.guest_token:
            raise NotFoundError(GUEST_CART_NOT_FOUND, error_code=CartErrorCode.CART_NOT_FOUND)

        cart = await self.carts.get_active_guest(hash_guest_token(self.guest_token))
        if cart is None or await self._expire_if_stale(cart):
            raise NotFoundError(GUEST_CART_NOT_FOUND, error_code=CartErrorCode.CART_NOT_FOUND)
        return cart

    async def _expire_if_stale(self, cart: Cart) -> bool:
        """Retire a cart idle past the retention period. True if it was."""
        if not is_expired(cart):
            return False

        await self.items.clear(cart.id)
        cart.status = CartStatus.EXPIRED.value
        await self.session.commit()

        return True

    def _touch(self, cart: Cart) -> None:
        cart.last_activity_at = datetime.now(timezone.utc)

    # ------------------------------------------------------------- operations

    async def view(self) -> CartRead:
        cart = await self.get_or_create_cart()
        return await self._render(cart)

    async def clear(self) -> CartRead:
        """Empty the cart but keep it, so the customer keeps the same cart id."""
        cart = await self.get_or_create_cart()

        await self.items.clear(cart.id)
        self._touch(cart)
        await self.session.commit()

        return await self._render(cart)

    async def add_item(self, data: CartItemCreate) -> CartRead:
        cart = await self.get_or_create_cart()

        existing = await self.items.get_by_variant(cart.id, data.variant_id)
        wanted = data.quantity + (existing.quantity if existing else 0)

        await self._check_available(data.variant_id, wanted)

        try:
            if existing is not None:
                existing.quantity = wanted
            else:
                await self.items.add_item(cart.id, data.variant_id, data.quantity)
            self._touch(cart)
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            return await self._top_up(cart, data)

        return await self._render(cart)

    async def _top_up(self, cart: Cart, data: CartItemCreate) -> CartRead:
        existing = await self.items.get_by_variant(cart.id, data.variant_id)
        if existing is None:
            raise ConflictError(
                "Could not update the cart, please try again",
                error_code=CartErrorCode.CONCURRENT_UPDATE,
            )

        wanted = existing.quantity + data.quantity
        await self._check_available(data.variant_id, wanted)

        existing.quantity = wanted
        self._touch(cart)
        await self.session.commit()
        return await self._render(cart)

    async def update_item(self, item_id: UUID, data: CartItemUpdate) -> CartRead:
        cart = await self.get_or_create_cart()

        item = await self.items.get_item(cart.id, item_id)
        if item is None:
            raise NotFoundError(ITEM_NOT_FOUND, error_code=CartErrorCode.CART_ITEM_NOT_FOUND)

        await self._check_available(item.variant_id, data.quantity)

        item.quantity = data.quantity
        self._touch(cart)
        await self.session.commit()

        return await self._render(cart)

    async def remove_item(self, item_id: UUID) -> CartRead:
        cart = await self.get_or_create_cart()

        item = await self.items.get_item(cart.id, item_id)
        if item is None:
            raise NotFoundError(ITEM_NOT_FOUND, error_code=CartErrorCode.CART_ITEM_NOT_FOUND)

        await self.items.delete(item)
        self._touch(cart)
        await self.session.commit()

        return await self._render(cart)

    async def merge_guest_cart(self, guest_token: str) -> CartRead:
        """Merge the contents of a guest cart into the signed-in customer's cart.
        """
        if self.customer_id is None:
            raise ConflictError("Only a signed-in customer can merge a cart")

        guest = await CartService(
            self.session, self.tenant_id, guest_token=guest_token
        )._guest_cart()
        cart = await self.get_or_create_cart()

        for line, variant, product in await self.items.list_with_catalogue(guest.id):
            if (
                variant.status != CatalogueStatus.ACTIVE.value
                or product.status != CatalogueStatus.ACTIVE.value
            ):
                continue

            available = sellable_quantity(await self.inventory.get(variant.id))
            existing = await self.items.get_by_variant(cart.id, variant.id)
            wanted = min(line.quantity + (existing.quantity if existing else 0), available)
            if wanted <= 0:
                continue

            if existing is not None:
                existing.quantity = wanted
            else:
                await self.items.add_item(cart.id, variant.id, wanted)

        await self.items.clear(guest.id)
        guest.status = CartStatus.CONVERTED.value
        self._touch(cart)
        await self.session.commit()

        return await self._render(cart)

    async def _check_available(self, variant_id: UUID, quantity: int) -> None:
        """Check stock for this quantity; nothing is reserved here."""
        await get_sellable_variant(self.session, self.tenant_id, variant_id)

        available = sellable_quantity(await self.inventory.get(variant_id))
        if quantity > available:
            if available == 0:
                raise ConflictError(
                    "This item is out of stock", error_code=InventoryErrorCode.INSUFFICIENT_STOCK
                )
            raise ConflictError(
                f"Only {available} items are available",
                error_code=InventoryErrorCode.INSUFFICIENT_STOCK,
            )

    async def _render(self, cart: Cart) -> CartRead:
        rows = await self.items.list_with_catalogue(cart.id)
        images = await self.images.primary_for(
            [product.id for _item, _variant, product in rows]
        )

        items: list[CartItemRead] = []
        subtotal = Decimal("0.00")
        count = 0

        for item, variant, product in rows:
            unit_price = effective_price(variant)
            line_total = unit_price * item.quantity
            subtotal += line_total
            count += item.quantity

            items.append(
                CartItemRead(
                    id=item.id,
                    variant_id=variant.id,
                    product_id=product.id,
                    product_name=product.name,
                    variant_name=variant.name,
                    sku=variant.sku,
                    quantity=item.quantity,
                    unit_price=unit_price,
                    subtotal=line_total,
                    image=_summary(images.get(product.id)),
                )
            )

        return CartRead(
            id=cart.id,
            items=items,
            subtotal=subtotal,
            item_count=count,
            expires_at=(cart.last_activity_at + retention_period())
            if cart.last_activity_at
            else None,
        )


def _summary(image) -> ProductImageSummary | None:
    return ProductImageSummary.model_validate(image) if image is not None else None
