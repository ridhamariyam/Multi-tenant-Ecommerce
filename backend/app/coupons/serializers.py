"""Turn coupon rows into API payloads."""

from __future__ import annotations

from uuid import UUID

from app.coupons.models import Coupon
from app.coupons.schemas import CouponRead, OfferRead


def coupon_read(
    coupon: Coupon, currency: str, category_ids: list[UUID] | None = None
) -> CouponRead:
    return CouponRead(
        id=coupon.id,
        code=coupon.code,
        discount_type=coupon.discount_type,
        discount_value=coupon.discount_value,
        currency=currency,
        min_order_amount=coupon.min_order_amount,
        max_discount_amount=coupon.max_discount_amount,
        starts_at=coupon.starts_at,
        expires_at=coupon.expires_at,
        usage_limit=coupon.usage_limit,
        per_customer_usage_limit=coupon.per_customer_usage_limit,
        times_used=coupon.times_used,
        is_active=coupon.is_active,
        is_automatic=coupon.is_automatic,
        first_order_only=coupon.first_order_only,
        min_quantity=coupon.min_quantity,
        buy_quantity=coupon.buy_quantity,
        get_quantity=coupon.get_quantity,
        category_ids=category_ids or [],
        valid_weekdays=coupon.valid_weekdays or [],
        created_at=coupon.created_at,
    )


def offer_read(coupon: Coupon, currency: str, category_ids: list[UUID]) -> OfferRead:
    return OfferRead(
        code=coupon.code,
        discount_type=coupon.discount_type,
        discount_value=coupon.discount_value,
        min_order_amount=coupon.min_order_amount,
        min_quantity=coupon.min_quantity,
        buy_quantity=coupon.buy_quantity,
        get_quantity=coupon.get_quantity,
        first_order_only=coupon.first_order_only,
        category_ids=category_ids,
        expires_at=coupon.expires_at,
        currency=currency,
    )