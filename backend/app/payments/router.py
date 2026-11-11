from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.dependencies import AUDITED
from app.auth.dependencies import require_customer, require_permission
from app.auth.permissions import Permission
from app.core import rate_limit
from app.core.config import get_settings
from app.core.database import get_db
from app.core.request_context import client_ip
from app.core.responses import ApiResponse, ok, paginated
from app.payments.schemas import PaymentQuery, PaymentRead, RazorpayVerification
from app.payments.serializers import payment_read
from app.payments.service import PaymentService, handle_razorpay_webhook
from app.tenants.resolver import CurrentTenant
from app.users.models import User

router = APIRouter(prefix="/payments", tags=["Payments"])

admin_router = APIRouter(prefix="/admin/payments", tags=["Admin-Payments"])


@router.post(
    "/razorpay/verify",
    response_model=ApiResponse[PaymentRead],
    summary="Verify a Razorpay payment",
)
async def verify_razorpay_payment(
    data: RazorpayVerification,
    tenant: CurrentTenant,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_customer),
) -> ApiResponse[PaymentRead]:
    settings = get_settings()
    await rate_limit.enforce(
        "checkout",
        str(user.tenant_id),
        str(user.id),
        limit=settings.checkout_rate_limit_attempts,
        window_seconds=settings.commerce_rate_limit_window_seconds,
    )
    payment = await PaymentService(session, user.tenant_id).verify_razorpay_payment(
        user.id,
        razorpay_order_id=data.razorpay_order_id,
        razorpay_payment_id=data.razorpay_payment_id,
        razorpay_signature=data.razorpay_signature,
        currency=tenant.currency,
    )
    return ok(payment_read(payment, tenant.currency), message="Payment verified")


@router.post(
    "/razorpay/webhook",
    response_model=ApiResponse[dict[str, str]],
    summary="Receive a signed Razorpay account webhook, for any tenant",
)
async def razorpay_webhook(
    request: Request,
    signature: str | None = Header(default=None, alias="X-Razorpay-Signature"),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[dict[str, str]]:
    result = await handle_razorpay_webhook(session, await request.body(), signature)
    return ok({"result": result}, message="Webhook received")


@router.post(
    "/razorpay/webhook/{tenant_id}",
    response_model=ApiResponse[dict[str, str]],
    summary="Receive a signed webhook from one brand's own Razorpay account",
)
async def brand_razorpay_webhook(
    tenant_id: UUID,
    request: Request,
    signature: str | None = Header(default=None, alias="X-Razorpay-Signature"),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[dict[str, str]]:
    result = await handle_razorpay_webhook(session, await request.body(), signature, tenant_id)
    return ok({"result": result}, message="Webhook received")


@router.post(
    "/razorpay/verify-guest",
    response_model=ApiResponse[PaymentRead],
    summary="Verify a guest's Razorpay payment",
)
async def verify_guest_razorpay_payment(
    request: Request,
    data: RazorpayVerification,
    tenant: CurrentTenant,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[PaymentRead]:
    """No sign-in: the Razorpay signature (made with the brand's key secret)
    is what proves the payment, and only a guest order can be confirmed here."""
    settings = get_settings()
    await rate_limit.enforce(
        "guest-checkout",
        str(tenant.id),
        client_ip(request),
        limit=settings.guest_checkout_rate_limit_attempts,
        window_seconds=settings.commerce_rate_limit_window_seconds,
    )
    payment = await PaymentService(session, tenant.id).verify_guest_razorpay_payment(
        razorpay_order_id=data.razorpay_order_id,
        razorpay_payment_id=data.razorpay_payment_id,
        razorpay_signature=data.razorpay_signature,
        currency=tenant.currency,
    )
    return ok(payment_read(payment, tenant.currency), message="Payment verified")


@router.get(
    "/{payment_id}",
    response_model=ApiResponse[PaymentRead],
    summary="Retrieve one of your payments",
)
async def get_my_payment(
    payment_id: UUID,
    tenant: CurrentTenant,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_customer),
) -> ApiResponse[PaymentRead]:
    payment = await PaymentService(session, user.tenant_id).get_for_customer(
        user.id, payment_id
    )
    return ok(payment_read(payment, tenant.currency), message="Payment retrieved")


@admin_router.get(
    "",
    response_model=ApiResponse[list[PaymentRead]],
    summary="List payments",
)
async def list_payments(
    tenant: CurrentTenant,
    params: Annotated[PaymentQuery, Query()],
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.PAYMENTS_VIEW, legacy_staff=True)),
) -> ApiResponse[list[PaymentRead]]:
    payments, total = await PaymentService(session, user.tenant_id).list(
        params, order_id=params.order_id, status=params.status
    )
    return paginated(
        [payment_read(payment, tenant.currency) for payment in payments],
        total_items=total,
        params=params,
        message="Payments retrieved",
    )


@admin_router.get(
    "/{payment_id}",
    response_model=ApiResponse[PaymentRead],
    summary="Retrieve a payment",
)
async def get_payment(
    payment_id: UUID,
    tenant: CurrentTenant,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.PAYMENTS_VIEW, legacy_staff=True)),
) -> ApiResponse[PaymentRead]:
    payment = await PaymentService(session, user.tenant_id).get(payment_id)
    return ok(payment_read(payment, tenant.currency), message="Payment retrieved")


@admin_router.post(
    "/{payment_id}/mark-paid",
    response_model=ApiResponse[PaymentRead],
    summary="Record a COD advance as received",
    dependencies=AUDITED,
)
async def mark_advance_paid(
    payment_id: UUID,
    tenant: CurrentTenant,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.PAYMENTS_MANAGE)),
) -> ApiResponse[PaymentRead]:
    payment = await PaymentService(session, user.tenant_id).mark_advance_paid(payment_id)
    return ok(payment_read(payment, tenant.currency), message="Advance marked as paid")
