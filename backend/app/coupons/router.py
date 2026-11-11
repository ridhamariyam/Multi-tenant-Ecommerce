
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.dependencies import AUDITED
from app.auth.dependencies import require_customer, require_permission
from app.auth.permissions import Permission
from app.core import rate_limit
from app.core.config import get_settings
from app.core.database import get_db
from app.core.responses import ApiResponse, ok, paginated
from app.coupons.constants import DiscountType
from app.coupons.schemas import (
    CouponApplyRequest,
    CouponApplyResponse,
    CouponCreate,
    CouponQuery,
    CouponRead,
    CouponUpdate,
    OfferRead,
)
from app.coupons.serializers import coupon_read, offer_read
from app.coupons.service import CouponService
from app.tenants.resolver import CurrentTenant
from app.users.models import User

router = APIRouter(prefix="/coupons", tags=["Coupons"])

admin_router = APIRouter(prefix="/admin/coupons", tags=["Admin-Coupons"], dependencies=AUDITED)

@admin_router.get(
    "",
    response_model=ApiResponse[list[CouponRead]],
    summary="List all coupons",
)
async def list_coupons(
    tenant: CurrentTenant,
    params: Annotated[CouponQuery, Query()],
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.COUPONS_VIEW, legacy_staff=True)),
) -> ApiResponse[list[CouponRead]]:
    service = CouponService(session, user.tenant_id)
    coupons, total = await service.list(params, active_only=params.active_only)
    return paginated(
        [
            coupon_read(coupon, tenant.currency, await service.category_ids(coupon.id))
            for coupon in coupons
        ],
        total_items=total,
        params=params,
        message="Coupons retrieved",
    )


@admin_router.post(
    "",
    response_model=ApiResponse[CouponRead],
    summary="Create a coupon",
)
async def create_coupon(
    data: CouponCreate,
    tenant: CurrentTenant,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.COUPONS_MANAGE)),
) -> ApiResponse[CouponRead]:
    service = CouponService(session, user.tenant_id)
    coupon = await service.create(data)
    return ok(
        coupon_read(coupon, tenant.currency, await service.category_ids(coupon.id)),
        message="Coupon created",
    )


@admin_router.get(
    "/{coupon_id}",
    response_model=ApiResponse[CouponRead],
    summary="Retrieve a coupon",
)
async def get_coupon(
    coupon_id: UUID,
    tenant: CurrentTenant,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.COUPONS_VIEW, legacy_staff=True)),
) -> ApiResponse[CouponRead]:
    service = CouponService(session, user.tenant_id)
    coupon = await service.get(coupon_id)
    return ok(
        coupon_read(coupon, tenant.currency, await service.category_ids(coupon.id)),
        message="Coupon retrieved",
    )


@admin_router.put(
    "/{coupon_id}",
    response_model=ApiResponse[CouponRead],
    summary="Update a coupon",
)
async def update_coupon(
    coupon_id: UUID,
    data: CouponUpdate,
    tenant: CurrentTenant,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.COUPONS_MANAGE)),
) -> ApiResponse[CouponRead]:
    service = CouponService(session, user.tenant_id)
    coupon = await service.update(coupon_id, data)
    return ok(
        coupon_read(coupon, tenant.currency, await service.category_ids(coupon.id)),
        message="Coupon updated",
    )


@admin_router.delete(
    "/{coupon_id}",
    response_model=ApiResponse[None],
    summary="Delete a coupon",
)
async def delete_coupon(
    coupon_id: UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.COUPONS_MANAGE)),
) -> ApiResponse[None]:
    await CouponService(session, user.tenant_id).delete(coupon_id)
    return ok(None, message="Coupon deleted")


@router.post(
    "/apply",
    response_model=ApiResponse[CouponApplyResponse],
    summary="Validate a coupon code against your cart and calculate its discount",
)
async def apply_coupon(
    data: CouponApplyRequest,
    tenant: CurrentTenant,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_customer),
) -> ApiResponse[CouponApplyResponse]:
    settings = get_settings()
    await rate_limit.enforce(
        "coupon-apply",
        str(user.tenant_id),
        str(user.id),
        limit=settings.coupon_apply_rate_limit_attempts,
        window_seconds=settings.commerce_rate_limit_window_seconds,
    )

    result = await CouponService(session, user.tenant_id).apply_for_customer(data.code, user.id)

    return ok(
        CouponApplyResponse(
            code=result.coupon.code,
            discount_amount=result.discount,
            currency=tenant.currency,
            discount_type=result.coupon.discount_type,
            free_shipping=result.coupon.discount_type == DiscountType.FREE_SHIPPING.value,
        ),
        message="Coupon applied successfully",
    )


@router.get(
    "/offers",
    response_model=ApiResponse[list[OfferRead]],
    summary="Automatic discounts running now (no code needed)",
)
async def list_offers(
    tenant: CurrentTenant,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[list[OfferRead]]:
    service = CouponService(session, tenant.id)
    offers = [
        offer_read(coupon, tenant.currency, await service.category_ids(coupon.id))
        for coupon in await service.live_offers()
    ]
    return ok(offers, message="Offers retrieved")

