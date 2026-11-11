from __future__ import annotations

import hmac
import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.dependencies import AUDITED
from app.auth.dependencies import require_permission
from app.auth.permissions import Permission
from app.core.config import get_settings
from app.core.database import get_db
from app.core.error_codes import ShipmentErrorCode
from app.core.exceptions import AuthenticationError, ValidationError
from app.core.responses import ApiResponse, ok
from app.orders.service import OrderService
from app.shipments import shiprocket
from app.shipments.constants import ShipmentPaymentMode, ShipmentState
from app.shipments.schemas import (
    AwbAssign,
    CourierRateRead,
    CourierRatesRead,
    OrderShipmentsRead,
    PackageInput,
    PickupCreate,
    PickupLocationRead,
    ProviderSettingsRead,
    ProviderSettingsUpdate,
    RateQueryParams,
    ShipmentCreate,
    ShipmentRead,
)
from app.shipments.serializers import settings_read, shipment_read
from app.shipments.service import ShipmentService, handle_webhook
from app.users.models import User

router = APIRouter(
    prefix="/admin/orders/{order_id}/shipments",
    tags=["Admin-Shipments"],
    dependencies=AUDITED,
)

settings_router = APIRouter(
    prefix="/admin/shipping/provider", tags=["Admin-Shipments"], dependencies=AUDITED
)

# Shiprocket refuses webhook URLs containing "shiprocket", "kartrocket", "sr"
# or "kr", so this path avoids them.
webhook_router = APIRouter(prefix="/courier-webhooks", tags=["Courier webhooks"])

MAX_WEBHOOK_BYTES = 256_000

can_view = require_permission(Permission.ORDERS_VIEW, legacy_staff=True)
can_manage = require_permission(Permission.ORDERS_MANAGE)


@router.get(
    "",
    response_model=ApiResponse[OrderShipmentsRead],
    summary="An order's shipment, earlier attempts and whether it can be booked",
)
async def order_shipments(
    order_id: UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(can_view),
) -> ApiResponse[OrderShipmentsRead]:
    service = ShipmentService(session, user.tenant_id)
    shipments = await service.for_order(order_id)
    order = await OrderService(session, user.tenant_id).get(order_id)
    settings = await service.get_settings()
    current = next((s for s in shipments if s.state != ShipmentState.CANCELLED.value), None)
    enabled = bool(settings and settings.is_enabled)
    configured = shiprocket.is_configured(user.tenant_id)
    blocked = (
        "Shipping with Shiprocket is not enabled for this store"
        if not enabled
        else "Shiprocket API credentials are not configured for this store"
        if not configured
        else "This order already has a shipment"
        if current is not None
        else service.create_blocked_reason(order)
    )
    return ok(
        OrderShipmentsRead(
            provider="SHIPROCKET",
            provider_enabled=enabled,
            credentials_configured=configured,
            can_create=blocked is None,
            create_blocked_reason=blocked,
            package_defaults=ShipmentService.package_defaults(settings),
            current=shipment_read(current) if current else None,
            history=[shipment_read(s, with_events=False) for s in shipments if s is not current],
        ),
        message="Shipments retrieved",
    )


@router.get(
    "/rates",
    response_model=ApiResponse[CourierRatesRead],
    summary="Live courier rates and serviceability for this order's parcel",
)
async def courier_rates(
    order_id: UUID,
    params: Annotated[RateQueryParams, Query()],
    session: AsyncSession = Depends(get_db),
    user: User = Depends(can_manage),
) -> ApiResponse[CourierRatesRead]:
    try:
        package = params.package()
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    query, rates = await ShipmentService(session, user.tenant_id).rates(order_id, package)
    return ok(
        CourierRatesRead(
            pickup_postcode=query.pickup_postcode,
            delivery_postcode=query.delivery_postcode,
            payment_mode=ShipmentPaymentMode.COD if query.cod else ShipmentPaymentMode.PREPAID,
            package=PackageInput(
                weight_kg=query.package.weight_kg,
                length_cm=query.package.length_cm,
                breadth_cm=query.package.breadth_cm,
                height_cm=query.package.height_cm,
            ),
            declared_value=query.declared_value,
            couriers=[CourierRateRead(**rate.__dict__) for rate in rates],
        ),
        message="Courier rates retrieved",
    )


@router.post(
    "",
    response_model=ApiResponse[ShipmentRead],
    status_code=201,
    summary="Book the order with Shiprocket (optionally assigning a courier)",
)
async def create_shipment(
    order_id: UUID,
    data: ShipmentCreate,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(can_manage),
) -> ApiResponse[ShipmentRead]:
    shipment = await ShipmentService(session, user.tenant_id).create(
        order_id, package=data.package, courier_id=data.courier_id, actor_id=user.id
    )
    return ok(shipment_read(shipment), message="Shipment created")


@router.post(
    "/{shipment_id}/awb",
    response_model=ApiResponse[ShipmentRead],
    summary="Assign a courier and get the AWB",
)
async def assign_awb(
    order_id: UUID,
    shipment_id: UUID,
    data: AwbAssign,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(can_manage),
) -> ApiResponse[ShipmentRead]:
    shipment = await ShipmentService(session, user.tenant_id).assign_awb(
        order_id, shipment_id, data.courier_id
    )
    return ok(shipment_read(shipment), message="Courier assigned")


@router.post(
    "/{shipment_id}/pickup",
    response_model=ApiResponse[ShipmentRead],
    summary="Ask the courier to collect the parcel",
)
async def schedule_pickup(
    order_id: UUID,
    shipment_id: UUID,
    data: PickupCreate,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(can_manage),
) -> ApiResponse[ShipmentRead]:
    shipment = await ShipmentService(session, user.tenant_id).schedule_pickup(
        order_id, shipment_id, data.pickup_date
    )
    return ok(shipment_read(shipment), message="Pickup scheduled")


@router.post(
    "/{shipment_id}/label",
    response_model=ApiResponse[ShipmentRead],
    summary="Generate the courier's shipping label (returns its download link)",
)
async def generate_label(
    order_id: UUID,
    shipment_id: UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(can_manage),
) -> ApiResponse[ShipmentRead]:
    shipment = await ShipmentService(session, user.tenant_id).label(order_id, shipment_id)
    return ok(shipment_read(shipment), message="Label ready")


@router.post(
    "/{shipment_id}/manifest",
    response_model=ApiResponse[ShipmentRead],
    summary="Generate (or re-print) the pickup manifest",
)
async def generate_manifest(
    order_id: UUID,
    shipment_id: UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(can_manage),
) -> ApiResponse[ShipmentRead]:
    shipment = await ShipmentService(session, user.tenant_id).manifest(order_id, shipment_id)
    return ok(shipment_read(shipment), message="Manifest ready")


@router.post(
    "/{shipment_id}/sync",
    response_model=ApiResponse[ShipmentRead],
    summary="Refresh tracking from Shiprocket now",
)
async def sync_tracking(
    order_id: UUID,
    shipment_id: UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(can_manage),
) -> ApiResponse[ShipmentRead]:
    shipment = await ShipmentService(session, user.tenant_id).sync(order_id, shipment_id)
    return ok(shipment_read(shipment), message="Tracking refreshed")


@router.post(
    "/{shipment_id}/cancel",
    response_model=ApiResponse[ShipmentRead],
    summary="Cancel the shipment with the courier (the order is not cancelled or refunded)",
)
async def cancel_shipment(
    order_id: UUID,
    shipment_id: UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(can_manage),
) -> ApiResponse[ShipmentRead]:
    shipment = await ShipmentService(session, user.tenant_id).cancel(order_id, shipment_id)
    return ok(shipment_read(shipment), message="Shipment cancelled")


@router.post(
    "/{shipment_id}/retry",
    response_model=ApiResponse[ShipmentRead],
    summary="Retry the last failed or unconfirmed step, without booking twice",
)
async def retry_shipment(
    order_id: UUID,
    shipment_id: UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(can_manage),
) -> ApiResponse[ShipmentRead]:
    shipment = await ShipmentService(session, user.tenant_id).retry(order_id, shipment_id)
    return ok(shipment_read(shipment), message="Shipment updated")


@settings_router.get(
    "",
    response_model=ApiResponse[ProviderSettingsRead],
    summary="Courier provider setup for this store",
)
async def get_provider_settings(
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.SETTINGS_VIEW, legacy_staff=True)),
) -> ApiResponse[ProviderSettingsRead]:
    settings = await ShipmentService(session, user.tenant_id).get_settings()
    return ok(settings_read(settings, user.tenant_id), message="Shipping provider settings")


@settings_router.put(
    "",
    response_model=ApiResponse[ProviderSettingsRead],
    summary="Enable Shiprocket and set the pickup location and package defaults",
)
async def update_provider_settings(
    data: ProviderSettingsUpdate,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.SETTINGS_MANAGE)),
) -> ApiResponse[ProviderSettingsRead]:
    settings = await ShipmentService(session, user.tenant_id).update_settings(data, user.id)
    return ok(settings_read(settings, user.tenant_id), message="Shipping provider settings saved")


@settings_router.get(
    "/pickup-locations",
    response_model=ApiResponse[list[PickupLocationRead]],
    summary="Pickup locations registered in the Shiprocket panel (checks the credentials)",
)
async def pickup_locations(
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.SETTINGS_VIEW, legacy_staff=True)),
) -> ApiResponse[list[PickupLocationRead]]:
    locations = await ShipmentService(session, user.tenant_id).pickup_locations()
    return ok(
        [PickupLocationRead(**location.__dict__) for location in locations],
        message="Pickup locations",
    )


@webhook_router.post(
    "/tracking",
    response_model=ApiResponse[dict[str, str]],
    summary="Receive a Shiprocket tracking webhook (authenticated by x-api-key)",
)
async def tracking_webhook(
    request: Request,
    api_key: str | None = Header(default=None, alias="x-api-key"),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[dict[str, str]]:
    expected = get_settings().shiprocket_webhook_token
    if not expected or not api_key or not hmac.compare_digest(api_key.encode(), expected.encode()):
        raise AuthenticationError(
            "Invalid webhook token", error_code=ShipmentErrorCode.WEBHOOK_UNAUTHORIZED
        )
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > MAX_WEBHOOK_BYTES:
            raise ValidationError("Webhook body too large")
    try:
        payload = json.loads(raw or b"{}")
    except ValueError as exc:
        raise ValidationError("Webhook body is not JSON") from exc
    if not isinstance(payload, dict):
        raise ValidationError("Webhook body must be a JSON object")
    result = await handle_webhook(session, payload)
    return ok({"result": result}, message="Webhook received")
