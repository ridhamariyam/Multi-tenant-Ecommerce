from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.dependencies import AUDITED
from app.audit.service import record_activity
from app.auth.dependencies import require_customer, require_permission
from app.auth.permissions import Permission
from app.cart.router import CART_TOKEN_HEADER, MAX_CART_TOKEN_LENGTH
from app.cart.service import CartService
from app.core import rate_limit
from app.core.config import get_settings
from app.core.database import get_db
from app.core.pagination import PageParams
from app.core.request_context import client_ip
from app.core.responses import ApiResponse, ok, paginated
from app.orders.constants import MAX_IDEMPOTENCY_KEY_LENGTH, PaymentMethod
from app.orders.pdf import (
    PDF_MEDIA_TYPE,
    invoice_filename,
    render_invoice_pdf,
    render_packing_slip,
    render_shipping_label,
    render_shipping_labels,
)
from app.orders.schemas import (
    BulkLabelRequest,
    CheckoutCreate,
    CheckoutPreview,
    CheckoutPreviewCreate,
    DeliveryAddressUpdate,
    GuestCheckoutCreate,
    GuestCheckoutPreviewCreate,
    InvoiceRead,
    OrderQuery,
    OrderRead,
    OrderStatusUpdate,
    OrderSummaryRead,
    OrderTrackingRead,
    PublicTrackingQuery,
    ShipmentUpdate,
    TrackingEventCreate,
)
from app.orders.serializers import (
    invoice_read,
    order_read,
    order_summary_read,
    tracking_read,
)
from app.orders.service import CheckoutService, OrderService
from app.payments.service import PaymentService
from app.pricing.service import GstService
from app.shipments.serializers import customer_shipment_read
from app.shipments.service import ShipmentService
from app.tenants.resolver import CurrentTenant
from app.users.models import User

checkout_router = APIRouter(prefix="/checkout", tags=["Checkout"])


async def _with_online_payment(session: AsyncSession, tenant, order):
    """For an online order, open (or reuse) its Razorpay order so the browser can pay.

    The order is already placed; if Razorpay can't be reached it stays placed with
    its payment pending, and replaying checkout with the same Idempotency-Key
    tries again.
    """
    if order.payment_method == PaymentMethod.CASH_ON_DELIVERY.value:
        return order
    await PaymentService(session, tenant.id).start_online_payment(
        order.id, order.customer_id, tenant.currency
    )
    return await OrderService(session, tenant.id).get(order.id)

router = APIRouter(prefix="/orders", tags=["Orders"])

admin_router = APIRouter(
    prefix="/admin/orders", tags=["Admin-Order_management"], dependencies=AUDITED
)

tracking_router = APIRouter(prefix="/storefront/orders", tags=["Order Tracking"])

PDF_RESPONSE = {
    200: {"content": {PDF_MEDIA_TYPE: {}}, "description": "The invoice as a PDF download"}
}


async def _tracking(session: AsyncSession, order) -> OrderTrackingRead:
    """The order's timeline, plus the courier's own status once a shipment is booked."""
    shipment = await ShipmentService(session, order.tenant_id).current_for_order(order.id)
    return tracking_read(order, customer_shipment_read(shipment))


async def _invoice_pdf(session: AsyncSession, tenant, order) -> Response:
    """The JSON invoice, laid out as a PDF -- no figures are recalculated here."""
    seller = await GstService(session, tenant.id).get_settings()
    invoice = invoice_read(order, seller, tenant.currency)
    content = await run_in_threadpool(
        render_invoice_pdf,
        invoice,
        store_name=tenant.name,
        customer_phone=order.delivery_phone,
        customer_email=order.contact_email,
    )
    return Response(
        content=content,
        media_type=PDF_MEDIA_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="{invoice_filename(invoice)}"',
            "Cache-Control": "private, no-store",
        },
    )


@checkout_router.post(
    "/preview",
    response_model=ApiResponse[CheckoutPreview],
    summary="Price the cart before ordering",
)

async def preview_checkout(
    coupon_code: str | None = Query(
        default=None,
        min_length=1,
        max_length=50,
        description="Optional coupon code to preview",
    ),
    data: CheckoutPreviewCreate | None = None,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_customer),
) -> ApiResponse[CheckoutPreview]:
    preview = await CheckoutService(
        session, user.tenant_id, user.id
    ).preview(
        address_id=data.address_id if data else None,
        coupon_code=coupon_code,
        payment_method=data.payment_method if data else PaymentMethod.CASH_ON_DELIVERY,
    )
    return ok(preview, message="Checkout preview")


@checkout_router.post(
    "",
    response_model=ApiResponse[OrderRead],
    status_code=status.HTTP_201_CREATED,
    summary="Place the order",
)
async def place_order(
    data: CheckoutCreate,
    tenant: CurrentTenant,
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        max_length=MAX_IDEMPOTENCY_KEY_LENGTH,
        description="Send the same key to retry safely; the original order comes back",
    ),
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_customer),
) -> ApiResponse[OrderRead]:
    settings = get_settings()
    await rate_limit.enforce(
        "checkout",
        str(user.tenant_id),
        str(user.id),
        limit=settings.checkout_rate_limit_attempts,
        window_seconds=settings.commerce_rate_limit_window_seconds,
    )

    order = await CheckoutService(session, user.tenant_id, user.id).place_order(
        data.address_id,
        data.coupon_code,
        idempotency_key=idempotency_key,
        payment_method=data.payment_method,
    )
    order = await _with_online_payment(session, tenant, order)
    return ok(order_read(order, tenant.currency), message="Order placed")


@checkout_router.post(
    "/guest/preview",
    response_model=ApiResponse[CheckoutPreview],
    summary="Price a guest cart before ordering (no account needed)",
)
async def preview_guest_checkout(
    data: GuestCheckoutPreviewCreate,
    tenant: CurrentTenant,
    cart_token: str = Header(alias=CART_TOKEN_HEADER, max_length=MAX_CART_TOKEN_LENGTH),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[CheckoutPreview]:
    cart = await CartService(session, tenant.id, guest_token=cart_token).active_cart()
    preview = await CheckoutService(session, tenant.id, None).preview_guest(
        cart,
        address=data.address,
        pincode=data.pincode,
        phone=data.phone,
        coupon_code=data.coupon_code,
        payment_method=data.payment_method,
    )
    return ok(preview, message="Checkout preview")


@checkout_router.post(
    "/guest",
    response_model=ApiResponse[OrderRead],
    status_code=status.HTTP_201_CREATED,
    summary="Place an order as a guest (no account needed)",
)
async def place_guest_order(
    request: Request,
    data: GuestCheckoutCreate,
    tenant: CurrentTenant,
    cart_token: str = Header(alias=CART_TOKEN_HEADER, max_length=MAX_CART_TOKEN_LENGTH),
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        max_length=MAX_IDEMPOTENCY_KEY_LENGTH,
        description="Send the same key to retry safely; the original order comes back",
    ),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[OrderRead]:
    settings = get_settings()
    await rate_limit.enforce(
        "guest-checkout",
        str(tenant.id),
        client_ip(request),
        limit=settings.guest_checkout_rate_limit_attempts,
        window_seconds=settings.commerce_rate_limit_window_seconds,
    )

    order = await CheckoutService(session, tenant.id, None).place_guest_order(
        cart_token,
        data.contact,
        data.address,
        coupon_code=data.coupon_code,
        payment_method=data.payment_method,
        idempotency_key=idempotency_key,
    )
    order = await _with_online_payment(session, tenant, order)
    return ok(order_read(order, tenant.currency), message="Order placed")


@tracking_router.get(
    "/track",
    response_model=ApiResponse[OrderTrackingRead],
    summary="Track an order with its number and the phone it was placed with",
)
async def track_order_publicly(
    request: Request,
    tenant: CurrentTenant,
    params: Annotated[PublicTrackingQuery, Query()],
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[OrderTrackingRead]:
    settings = get_settings()
    await rate_limit.enforce(
        "order-tracking",
        str(tenant.id),
        client_ip(request),
        limit=settings.order_tracking_rate_limit_attempts,
        window_seconds=settings.commerce_rate_limit_window_seconds,
    )
    order = await OrderService(session, tenant.id).get_for_tracking(
        params.order_number, params.phone
    )
    return ok(await _tracking(session, order), message="Order tracking retrieved")


@router.get(
    "",
    response_model=ApiResponse[list[OrderSummaryRead]],
    summary="List your orders",
)
async def list_my_orders(
    tenant: CurrentTenant,
    params: Annotated[PageParams, Query()],
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_customer),
) -> ApiResponse[list[OrderSummaryRead]]:
    orders, total = await OrderService(session, user.tenant_id).list(
        params, customer_id=user.id
    )
    return paginated(
        [order_summary_read(order, tenant.currency) for order in orders],
        total_items=total,
        params=params,
        message="Orders retrieved",
    )


@router.post(
    "/{order_id}/cancel",
    response_model=ApiResponse[OrderRead],
    summary="Cancel one of your orders",
)
async def cancel_my_order(
    order_id: UUID,
    tenant: CurrentTenant,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_customer),
) -> ApiResponse[OrderRead]:
    order = await OrderService(session, user.tenant_id).cancel_for_customer(
        user.id, order_id
    )
    return ok(order_read(order, tenant.currency), message="Order cancelled")


@router.get(
    "/{order_id}/tracking",
    response_model=ApiResponse[OrderTrackingRead],
    summary="Where one of your orders is",
)
async def track_my_order(
    order_id: UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_customer),
) -> ApiResponse[OrderTrackingRead]:
    order = await OrderService(session, user.tenant_id).get_for_customer(user.id, order_id)
    return ok(await _tracking(session, order), message="Order tracking retrieved")


@router.get(
    "/{order_id}/invoice",
    response_model=ApiResponse[InvoiceRead],
    summary="GST invoice for one of your orders",
)
async def my_invoice(
    order_id: UUID,
    tenant: CurrentTenant,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_customer),
) -> ApiResponse[InvoiceRead]:
    order = await OrderService(session, user.tenant_id).get_for_customer(user.id, order_id)
    seller = await GstService(session, user.tenant_id).get_settings()
    return ok(invoice_read(order, seller, tenant.currency), message="Invoice retrieved")


@router.get(
    "/{order_id}/invoice/pdf",
    response_class=Response,
    responses=PDF_RESPONSE,
    summary="Download the GST invoice for one of your orders as a PDF",
)
async def my_invoice_pdf(
    order_id: UUID,
    tenant: CurrentTenant,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_customer),
) -> Response:
    order = await OrderService(session, user.tenant_id).get_for_customer(user.id, order_id)
    return await _invoice_pdf(session, tenant, order)


@router.get(
    "/{order_id}",
    response_model=ApiResponse[OrderRead],
    summary="Retrieve one of your orders",
)
async def get_my_order(
    order_id: UUID,
    tenant: CurrentTenant,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_customer),
) -> ApiResponse[OrderRead]:
    order = await OrderService(session, user.tenant_id).get_for_customer(
        user.id, order_id
    )
    return ok(order_read(order, tenant.currency), message="Order retrieved")


@admin_router.get(
    "",
    response_model=ApiResponse[list[OrderSummaryRead]],
    summary="List orders",
)
async def list_orders(
    tenant: CurrentTenant,
    params: Annotated[OrderQuery, Query()],
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.ORDERS_VIEW, legacy_staff=True)),
) -> ApiResponse[list[OrderSummaryRead]]:
    orders, total = await OrderService(session, user.tenant_id).list(params)
    return paginated(
        [order_summary_read(order, tenant.currency) for order in orders],
        total_items=total,
        params=params,
        message="Orders retrieved",
    )


@admin_router.get(
    "/{order_id}",
    response_model=ApiResponse[OrderRead],
    summary="Retrieve an order",
)
async def get_order(
    order_id: UUID,
    tenant: CurrentTenant,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.ORDERS_VIEW, legacy_staff=True)),
) -> ApiResponse[OrderRead]:
    order = await OrderService(session, user.tenant_id).get(order_id)
    return ok(order_read(order, tenant.currency), message="Order retrieved")


@admin_router.patch(
    "/{order_id}/status",
    response_model=ApiResponse[OrderRead],
    summary="Move an order to its next status",
)
async def update_order_status(
    order_id: UUID,
    data: OrderStatusUpdate,
    tenant: CurrentTenant,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.ORDERS_MANAGE)),
) -> ApiResponse[OrderRead]:
    shipment = data.model_dump(
        include={"courier_name", "tracking_number", "tracking_url"}, exclude_none=True
    )
    order = await OrderService(session, user.tenant_id).update_status(
        order_id,
        data.status,
        note=data.note,
        shipment=shipment,
        return_reason_id=data.return_reason_id,
        return_note=data.return_note,
    )
    return ok(order_read(order, tenant.currency), message="Order status updated")


@admin_router.patch(
    "/{order_id}/shipment",
    response_model=ApiResponse[OrderRead],
    summary="Set the courier, tracking number and tracking link",
)
async def update_shipment(
    order_id: UUID,
    data: ShipmentUpdate,
    tenant: CurrentTenant,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.ORDERS_MANAGE)),
) -> ApiResponse[OrderRead]:
    order = await OrderService(session, user.tenant_id).update_shipment(
        order_id, data.model_dump(exclude_unset=True)
    )
    return ok(order_read(order, tenant.currency), message="Shipment updated")


@admin_router.post(
    "/{order_id}/tracking-events",
    response_model=ApiResponse[OrderTrackingRead],
    status_code=status.HTTP_201_CREATED,
    summary="Add a courier scan or note to an order's tracking",
)
async def add_tracking_event(
    order_id: UUID,
    data: TrackingEventCreate,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.ORDERS_MANAGE, legacy_staff=True)),
) -> ApiResponse[OrderTrackingRead]:
    order = await OrderService(session, user.tenant_id).add_tracking_event(
        order_id,
        description=data.description,
        location=data.location,
        occurred_at=data.occurred_at,
    )
    return ok(tracking_read(order), message="Tracking event added")


@admin_router.get(
    "/{order_id}/tracking",
    response_model=ApiResponse[OrderTrackingRead],
    summary="An order's tracking timeline",
)
async def admin_tracking(
    order_id: UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.ORDERS_VIEW, legacy_staff=True)),
) -> ApiResponse[OrderTrackingRead]:
    order = await OrderService(session, user.tenant_id).get(order_id)
    return ok(await _tracking(session, order), message="Order tracking retrieved")


@admin_router.get(
    "/{order_id}/invoice",
    response_model=ApiResponse[InvoiceRead],
    summary="GST invoice for an order",
)
async def admin_invoice(
    order_id: UUID,
    tenant: CurrentTenant,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.ORDERS_VIEW, legacy_staff=True)),
) -> ApiResponse[InvoiceRead]:
    order = await OrderService(session, user.tenant_id).get(order_id)
    seller = await GstService(session, user.tenant_id).get_settings()
    return ok(invoice_read(order, seller, tenant.currency), message="Invoice retrieved")


@admin_router.get(
    "/{order_id}/invoice/pdf",
    response_class=Response,
    responses=PDF_RESPONSE,
    summary="Download the GST invoice for an order as a PDF",
)
async def admin_invoice_pdf(
    order_id: UUID,
    tenant: CurrentTenant,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.ORDERS_VIEW, legacy_staff=True)),
) -> Response:
    order = await OrderService(session, user.tenant_id).get(order_id)
    return await _invoice_pdf(session, tenant, order)



def _pdf_response(content: bytes, filename: str) -> Response:
    return Response(
        content=content,
        media_type=PDF_MEDIA_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
        },
    )


@admin_router.patch(
    "/{order_id}/address",
    response_model=ApiResponse[OrderRead],
    summary="Correct the delivery address before the order ships",
)
async def update_order_address(
    order_id: UUID,
    data: DeliveryAddressUpdate,
    request: Request,
    tenant: CurrentTenant,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.ORDERS_MANAGE)),
) -> ApiResponse[OrderRead]:
    order, before = await OrderService(session, user.tenant_id).update_address(order_id, data)
    await record_activity(
        session,
        user,
        "order.address_updated",
        "order",
        order.id,
        summary=f"Delivery address changed on {order.order_number}",
        changes={"before": before, "after": data.model_dump()},
        request=request,
    )
    return ok(order_read(order, tenant.currency), message="Address updated")


@admin_router.get(
    "/{order_id}/packing-slip/pdf",
    response_class=Response,
    responses=PDF_RESPONSE,
    summary="Packing slip (items and quantities, no prices) as a PDF",
)
async def packing_slip_pdf(
    order_id: UUID,
    tenant: CurrentTenant,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.ORDERS_VIEW, legacy_staff=True)),
) -> Response:
    order = await OrderService(session, user.tenant_id).get(order_id)
    seller = await GstService(session, tenant.id).get_settings()
    content = await run_in_threadpool(
        render_packing_slip, order, store_name=tenant.name, seller=seller
    )
    return _pdf_response(content, f"packing-slip-{order.order_number}.pdf")


@admin_router.post(
    "/shipping-labels/pdf",
    response_class=Response,
    responses=PDF_RESPONSE,
    summary="Shipping labels for several orders in one PDF (one A6 label per page)",
)
async def bulk_shipping_labels_pdf(
    data: BulkLabelRequest,
    tenant: CurrentTenant,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.ORDERS_VIEW, legacy_staff=True)),
) -> Response:
    orders = await OrderService(session, user.tenant_id).for_labels(data.order_ids)
    seller = await GstService(session, tenant.id).get_settings()
    content = await run_in_threadpool(
        render_shipping_labels, orders, store_name=tenant.name, seller=seller
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    return _pdf_response(content, f"labels-{len(orders)}-orders-{stamp}.pdf")


@admin_router.get(
    "/{order_id}/shipping-label/pdf",
    response_class=Response,
    responses=PDF_RESPONSE,
    summary="A6 address label for the parcel as a PDF",
)
async def shipping_label_pdf(
    order_id: UUID,
    tenant: CurrentTenant,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.ORDERS_VIEW, legacy_staff=True)),
) -> Response:
    order = await OrderService(session, user.tenant_id).get(order_id)
    seller = await GstService(session, tenant.id).get_settings()
    content = await run_in_threadpool(
        render_shipping_label, order, store_name=tenant.name, seller=seller
    )
    return _pdf_response(content, f"label-{order.order_number}.pdf")


@admin_router.post(
    "/{order_id}/refund",
    response_model=ApiResponse[OrderRead],
    summary="Refund a cancelled order's online payment in full",
)
async def refund_order(
    order_id: UUID,
    tenant: CurrentTenant,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.PAYMENTS_MANAGE)),
) -> ApiResponse[OrderRead]:
    order = await PaymentService(session, user.tenant_id).refund(order_id)
    return ok(order_read(order, tenant.currency), message="Refund requested")
