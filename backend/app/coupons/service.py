from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cart.repository import CartItemRepository
from app.cart.service import CartService
from app.catalogue.prices import effective_price
from app.catalogue.repository import CategoryRepository, category_subtree
from app.core.config import get_settings
from app.core.database import conflict_on_integrity_error
from app.core.error_codes import CartErrorCode, CouponErrorCode
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.money import ZERO, money
from app.core.pagination import PageParams
from app.coupons.constants import PERCENT_TYPES, DiscountType
from app.coupons.models import Coupon, CouponUsage
from app.coupons.models import Coupon as CouponModel
from app.coupons.repository import (
    CouponCategoryRepository,
    CouponRepository,
    CouponUsageRepository,
)
from app.coupons.schemas import CouponCreate, CouponUpdate
from app.orders.constants import OrderStatus
from app.orders.models import Order
from app.pricing.constants import PERCENT

COUPON_NOT_FOUND = "Coupon not found"
SAVE_FAILED = "Unable to save coupon, please try again"
PERCENTAGE_TOO_LARGE = "Percentage discount value cannot exceed 100."
DATES_INVERTED = "Start date cannot be after expiration date."
USAGE_LIMIT_REACHED = "This coupon has reached its usage limit"


CART_EMPTY = "Your cart is empty"
NEEDS_CART = "This offer depends on what is in your bag -- add items first"
FIRST_ORDER_ONLY = "This coupon is only valid on your first order"


@dataclass
class CouponLine:
    """One cart line as the coupon rules see it."""

    product_id: UUID
    category_id: UUID
    unit_price: Decimal
    quantity: int


@dataclass
class CouponResult:
    coupon: Coupon
    discount: Decimal  # off the goods
    shipping_discount: Decimal  # off the delivery charge
    automatic: bool = False

    @property
    def saving(self) -> Decimal:
        return self.discount + self.shipping_discount


def _check_rules(
    discount_type: DiscountType | str,
    discount_value: Decimal | None,
    starts_at: datetime | None,
    expires_at: datetime | None,
    buy_quantity: int | None = None,
    get_quantity: int | None = None,
) -> None:
    """Rules a coupon must satisfy however it arrived -- a 400, not a 422."""
    kind = DiscountType(discount_type)
    if kind is not DiscountType.FREE_SHIPPING and not discount_value:
        raise ValidationError("discount_value is required for this discount type")

    if kind in PERCENT_TYPES and discount_value is not None and discount_value > PERCENT:
        raise ValidationError(PERCENTAGE_TOO_LARGE)

    if kind is DiscountType.BOGO and (not buy_quantity or not get_quantity):
        raise ValidationError("A buy-one-get-one coupon needs buy_quantity and get_quantity")

    if starts_at is not None and expires_at is not None and starts_at >= expires_at:
        raise ValidationError(DATES_INVERTED)



WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def valid_today(coupon: Coupon, moment: datetime) -> bool:
    """Weekday rule, judged by the shop's local date (not UTC)."""
    if not coupon.valid_weekdays:
        return True
    offset = timedelta(minutes=get_settings().store_utc_offset_minutes)
    return (moment.astimezone(timezone.utc) + offset).weekday() in coupon.valid_weekdays


class CouponService:
    """Manage coupon creation, lookup, validation, and redemption."""

    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.coupons = CouponRepository(session, tenant_id)
        self.usages = CouponUsageRepository(session, tenant_id)
        self.categories = CouponCategoryRepository(session, tenant_id)
        self.catalogue_categories = CategoryRepository(session, tenant_id)

    async def get(self, coupon_id: UUID) -> Coupon:
        coupon = await self.coupons.get(coupon_id)
        if coupon is None:
            raise NotFoundError(COUPON_NOT_FOUND)
        return coupon

    async def list(
        self,
        params: PageParams,
        *,
        active_only: bool = False,
    ) -> tuple[list[Coupon], int]:
        stmt = self.coupons.list_select(active_only=active_only)
        rows, total = await self.coupons.paginate(stmt, params)
        return list(rows), total

    async def create(self, data: CouponCreate) -> Coupon:
        _check_rules(
            data.discount_type,
            data.discount_value,
            data.starts_at,
            data.expires_at,
            data.buy_quantity,
            data.get_quantity,
        )
        await self._require_categories(data.category_ids or [])

        code_upper = data.code.upper()
        existing = await self.coupons.get_by_code(code_upper)
        if existing is not None:
            raise ConflictError(
                "A coupon with this code already exists",
                error_code=CouponErrorCode.CODE_TAKEN,
            )

        
        async with conflict_on_integrity_error(self.session, SAVE_FAILED):
            coupon = Coupon(
                code=code_upper,
                discount_type=data.discount_type.value,
                discount_value=data.discount_value or ZERO,
                min_order_amount=data.min_order_amount,
                max_discount_amount=data.max_discount_amount,
                starts_at=data.starts_at,
                expires_at=data.expires_at,
                usage_limit=data.usage_limit,
                per_customer_usage_limit=data.per_customer_usage_limit,
                is_active=data.is_active,
                is_automatic=data.is_automatic,
                first_order_only=data.first_order_only,
                min_quantity=data.min_quantity,
                buy_quantity=data.buy_quantity,
                get_quantity=data.get_quantity,
                valid_weekdays=data.valid_weekdays,
            )
            await self.coupons.add(coupon)
            if data.category_ids:
                await self.categories.replace(coupon.id, data.category_ids)
            await self.session.commit()

        return coupon

    async def update(self, coupon_id: UUID, data: CouponUpdate) -> Coupon:
        coupon = await self.get(coupon_id)
        changes = data.model_dump(exclude_unset=True)

        category_ids = changes.pop("category_ids", None)
        _check_rules(
            changes.get("discount_type", coupon.discount_type),
            changes.get("discount_value", coupon.discount_value),
            changes.get("starts_at", coupon.starts_at),
            changes.get("expires_at", coupon.expires_at),
            changes.get("buy_quantity", coupon.buy_quantity),
            changes.get("get_quantity", coupon.get_quantity),
        )
        if category_ids is not None:
            await self._require_categories(category_ids)
            await self.categories.replace(coupon.id, category_ids)
        if "discount_value" in changes and changes["discount_value"] is None:
            changes["discount_value"] = ZERO

        for field, value in changes.items():
            setattr(
                coupon, field, value.value if isinstance(value, DiscountType) else value
            )

        
        async with conflict_on_integrity_error(self.session, SAVE_FAILED):
            await self.session.commit()

        return coupon

    async def delete(self, coupon_id: UUID) -> None:
        """Deactivate the coupon without removing its usage history."""
        coupon = await self.get(coupon_id)
        coupon.is_active = False
        await self.session.commit()

    async def _require_categories(self, category_ids: list[UUID]) -> None:
        for category_id in category_ids:
            if await self.catalogue_categories.get(category_id) is None:
                raise NotFoundError(f"Category {category_id} not found")

    async def category_ids(self, coupon_id: UUID) -> list[UUID]:
        return await self.categories.ids_for(coupon_id)

    async def _eligible_category_ids(self, coupon: Coupon) -> set[UUID] | None:
        """Every category the coupon covers, sub-categories included; None = all."""
        roots = await self.categories.ids_for(coupon.id)
        if not roots:
            return None
        covered: set[UUID] = set()
        for root in roots:
            covered.update(
                (await self.session.scalars(category_subtree(self.tenant_id, root))).all()
            )
        return covered

    async def _has_earlier_order(self, customer_id: UUID) -> bool:
        count = await self.session.scalar(
            select(func.count(Order.id)).where(
                Order.tenant_id == self.tenant_id,
                Order.customer_id == customer_id,
                Order.status != OrderStatus.CANCELLED.value,
            )
        )
        return bool(count)

    @staticmethod
    def _needs_lines(coupon: Coupon, has_categories: bool) -> bool:
        return (
            has_categories
            or coupon.min_quantity is not None
            or coupon.discount_type == DiscountType.BOGO.value
        )

    async def evaluate(
        self,
        coupon: Coupon | None,
        subtotal: Decimal,
        customer_id: UUID | None,
        *,
        lines: list[CouponLine] | None = None,
        shipping: Decimal = ZERO,
    ) -> CouponResult:
        """Validate a coupon against this basket and work out what it saves."""
        if coupon is None or not coupon.is_active:
            raise NotFoundError(
                "Invalid or inactive coupon code",
                error_code=CouponErrorCode.INVALID,
            )

        now = datetime.now(timezone.utc)
        if coupon.starts_at and now < coupon.starts_at:
            raise ValidationError(
                "This coupon is not active yet",
                error_code=CouponErrorCode.NOT_STARTED,
            )
        if coupon.expires_at and now > coupon.expires_at:
            raise ValidationError("This coupon has expired", error_code=CouponErrorCode.EXPIRED)
        if not valid_today(coupon, now):
            days = ", ".join(WEEKDAY_NAMES[d] for d in coupon.valid_weekdays)
            raise ValidationError(
                f"This coupon is only valid on {days}",
                error_code=CouponErrorCode.NOT_APPLICABLE,
            )

        # NULL means unlimited; 0 is a real "block everything" setting.
        if coupon.usage_limit is not None and coupon.times_used >= coupon.usage_limit:
            raise ValidationError(
                USAGE_LIMIT_REACHED,
                error_code=CouponErrorCode.USAGE_LIMIT_REACHED,
            )

        if coupon.per_customer_usage_limit is not None and customer_id is not None:
            customer_uses = await self.usages.count_for_customer(
                coupon.id,
                customer_id,
            )
            if customer_uses >= coupon.per_customer_usage_limit:
                raise ValidationError(
                    "You have already reached the usage limit for this coupon",
                    error_code=CouponErrorCode.USAGE_LIMIT_REACHED,
                )

        if coupon.first_order_only and (
            customer_id is None or await self._has_earlier_order(customer_id)
        ):
            raise ValidationError(FIRST_ORDER_ONLY, error_code=CouponErrorCode.NOT_APPLICABLE)

        if coupon.min_order_amount is not None and subtotal < coupon.min_order_amount:
            raise ValidationError(
                f"Minimum order amount of {coupon.min_order_amount} required for this coupon",
                error_code=CouponErrorCode.MIN_ORDER_NOT_MET,
            )

        covered = await self._eligible_category_ids(coupon)
        if self._needs_lines(coupon, covered is not None) and lines is None:
            raise ValidationError(NEEDS_CART, error_code=CouponErrorCode.NOT_APPLICABLE)

        if lines is None:
            eligible_total = subtotal
            eligible = []
        else:
            eligible = [
                line for line in lines if covered is None or line.category_id in covered
            ]
            eligible_total = sum((line.unit_price * line.quantity for line in eligible), ZERO)
            if covered is not None and not eligible:
                raise ValidationError(
                    "This coupon does not apply to anything in your bag",
                    error_code=CouponErrorCode.NOT_APPLICABLE,
                )

        if coupon.min_quantity is not None:
            units = sum(line.quantity for line in eligible)
            if units < coupon.min_quantity:
                raise ValidationError(
                    f"Add at least {coupon.min_quantity} eligible items to use this offer",
                    error_code=CouponErrorCode.NOT_APPLICABLE,
                )

        kind = DiscountType(coupon.discount_type)
        shipping_discount = ZERO
        if kind is DiscountType.FREE_SHIPPING:
            raw_discount = ZERO
            shipping_discount = money(shipping)
        elif kind is DiscountType.PERCENTAGE:
            raw_discount = eligible_total * coupon.discount_value / PERCENT
        elif kind is DiscountType.BOGO:
            raw_discount = self._bogo_discount(coupon, eligible)
            if raw_discount == ZERO:
                raise ValidationError(
                    f"Buy {coupon.buy_quantity} and get {coupon.get_quantity} -- "
                    "add more eligible items to use this offer",
                    error_code=CouponErrorCode.NOT_APPLICABLE,
                )
        else:
            raw_discount = coupon.discount_value

        if (
            kind in PERCENT_TYPES
            and coupon.max_discount_amount is not None
            and raw_discount > coupon.max_discount_amount
        ):
            raw_discount = coupon.max_discount_amount

        # Never negative, never more than what's actually being bought.
        discount = max(ZERO, min(money(raw_discount), eligible_total, subtotal))
        return CouponResult(
            coupon=coupon,
            discount=discount,
            shipping_discount=shipping_discount,
            automatic=coupon.is_automatic,
        )

    @staticmethod
    def _bogo_discount(coupon: Coupon, lines: list[CouponLine]) -> Decimal:
        """In each run of buy+get units (dearest first), the cheapest `get` are discounted."""
        units = sorted(
            (line.unit_price for line in lines for _ in range(line.quantity)), reverse=True
        )
        group = coupon.buy_quantity + coupon.get_quantity
        discounted = ZERO
        for start in range(0, len(units) - group + 1, group):
            for price in units[start + coupon.buy_quantity : start + group]:
                discounted += price
        return discounted * coupon.discount_value / PERCENT

    async def validated_discount(
        self,
        coupon: Coupon | None,
        subtotal: Decimal,
        customer_id: UUID,
    ) -> Decimal:
        """Validate a coupon and calculate the discount (subtotal-only rules)."""
        return (await self.evaluate(coupon, subtotal, customer_id)).discount

    async def apply_for_customer(self, code: str, customer_id: UUID) -> CouponResult:
        """The /coupons/apply check, priced against the live cart, never a client subtotal."""
        cart = await CartService(self.session, self.tenant_id, customer_id).active_cart()
        lines = await cart_lines(self.session, self.tenant_id, cart.id) if cart else []
        if not lines:
            raise ConflictError(CART_EMPTY, error_code=CartErrorCode.CART_EMPTY)
        coupon = await self.coupons.get_by_code(code)
        cart_subtotal = sum((line.unit_price * line.quantity for line in lines), ZERO)
        return await self.evaluate(coupon, cart_subtotal, customer_id, lines=lines)

    async def evaluate_code(
        self,
        code: str,
        subtotal: Decimal,
        customer_id: UUID | None,
        *,
        lines: list[CouponLine] | None = None,
        shipping: Decimal = ZERO,
        for_update: bool = False,
    ) -> CouponResult:
        coupon = (
            await self.coupons.get_by_code_for_update(code)
            if for_update
            else await self.coupons.get_by_code(code)
        )
        return await self.evaluate(
            coupon, subtotal, customer_id, lines=lines, shipping=shipping
        )

    async def best_automatic(
        self,
        subtotal: Decimal,
        customer_id: UUID | None,
        *,
        lines: list[CouponLine],
        shipping: Decimal = ZERO,
    ) -> CouponResult | None:
        """The automatic discount that saves the most on this basket, if any applies."""
        best: CouponResult | None = None
        for coupon in await self.coupons.live_automatic():
            try:
                result = await self.evaluate(
                    coupon, subtotal, customer_id, lines=lines, shipping=shipping
                )
            except (NotFoundError, ValidationError):
                continue
            if result.saving > ZERO and (best is None or result.saving > best.saving):
                best = result
        return best

    async def live_offers(self) -> list[Coupon]:
        """Automatic discounts currently running, for promo strips."""
        now = datetime.now(timezone.utc)
        return [
            coupon
            for coupon in await self.coupons.live_automatic()
            if (coupon.starts_at is None or coupon.starts_at <= now)
            and (coupon.expires_at is None or coupon.expires_at > now)
            and (coupon.usage_limit is None or coupon.times_used < coupon.usage_limit)
            and valid_today(coupon, now)
        ]

    async def lock(self, coupon_id: UUID) -> Coupon | None:
        """Re-read a coupon with a row lock before spending it."""
        return await self.session.scalar(
            select(CouponModel)
            .where(CouponModel.tenant_id == self.tenant_id, CouponModel.id == coupon_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def lock_and_validate(
        self,
        code: str,
        subtotal: Decimal,
        customer_id: UUID,
    ) -> tuple[Coupon, Decimal]:
        """Lock, validate, and calculate a coupon discount."""
        coupon = await self.coupons.get_by_code_for_update(code)
        discount = await self.validated_discount(coupon, subtotal, customer_id)
        return coupon, discount

    async def record_redemption(
        self,
        coupon: Coupon,
        customer_id: UUID,
        order_id: UUID,
        discount_amount: Decimal,
    ) -> CouponUsage:
        """Record a coupon redemption without committing the transaction."""
        coupon.times_used += 1
        usage = CouponUsage(
            coupon_id=coupon.id,
            customer_id=customer_id,
            order_id=order_id,
            discount_amount=discount_amount,
            used_at=datetime.now(timezone.utc),
        )
        return await self.usages.add(usage)

    async def record_usage(
        self,
        coupon_id: UUID,
        customer_id: UUID,
        order_id: UUID,
        discount_amount: Decimal,
    ) -> CouponUsage:
        """Record a coupon redemption and commit the transaction."""
        coupon = await self.get(coupon_id)
        usage = await self.record_redemption(
            coupon,
            customer_id,
            order_id,
            discount_amount,
        )
        await self.session.commit()
        return usage

async def cart_lines(session, tenant_id: UUID, cart_id: UUID) -> list[CouponLine]:
    """A cart's lines, priced at what the shopper pays now, for coupon rules."""
    rows = await CartItemRepository(session, tenant_id).list_with_catalogue(cart_id)
    return [
        CouponLine(
            product_id=product.id,
            category_id=product.category_id,
            unit_price=effective_price(variant),
            quantity=item.quantity,
        )
        for item, variant, product in rows
    ]
