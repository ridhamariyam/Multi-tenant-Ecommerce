"""Turn shipment rows into API payloads."""

from __future__ import annotations

from app.core.config import get_settings
from app.shipments import shiprocket
from app.shipments.constants import (
    CANCELLABLE_STATES,
    STATE_RANK,
    OperationStatus,
    ShipmentState,
)
from app.shipments.models import Shipment, ShippingProviderSettings
from app.shipments.schemas import (
    CustomerShipmentRead,
    PackageInput,
    ProviderSettingsRead,
    ShipmentEventRead,
    ShipmentRead,
)
from app.shipments.service import ShipmentService, recovery_hint


def actions(shipment: Shipment) -> list[str]:
    """The next steps the admin screen may offer; the service enforces each again."""
    state = ShipmentState(shipment.state)
    available: list[str] = []
    in_progress = ShipmentService._in_flight(shipment)
    if shipment.pending_operation is not None and not in_progress:
        available.append("retry")
    if shipment.operation_status == OperationStatus.FAILED.value:
        if shipment.pending_operation == "ASSIGN_AWB" and state is ShipmentState.SHIPMENT_CREATED:
            available.append("assign_awb")
        if (
            shipment.pending_operation == "SCHEDULE_PICKUP"
            and state in {ShipmentState.READY_TO_SHIP, ShipmentState.DELIVERY_EXCEPTION}
            and shipment.picked_up_at is None
            and shipment.awb_code
        ):
            available.append("schedule_pickup")
    if shipment.pending_operation is None:
        if state is ShipmentState.SHIPMENT_CREATED:
            available.append("assign_awb")
        if state in {ShipmentState.READY_TO_SHIP, ShipmentState.DELIVERY_EXCEPTION} and (
            shipment.awb_code and shipment.picked_up_at is None
        ):
            available.append("schedule_pickup")
    if shipment.awb_code and state is not ShipmentState.CANCELLED:
        available.append("label")
    if (
        STATE_RANK[state] >= STATE_RANK[ShipmentState.PICKUP_SCHEDULED]
        and state is not ShipmentState.CANCELLED
    ):
        available.append("manifest")
    if shipment.awb_code and state is not ShipmentState.CANCELLED:
        available.append("sync")
    if state in CANCELLABLE_STATES and not in_progress:
        available.append("cancel")
    return available


def shipment_read(shipment: Shipment, *, with_events: bool = True) -> ShipmentRead:
    return ShipmentRead(
        id=shipment.id,
        order_id=shipment.order_id,
        provider=shipment.provider,
        attempt=shipment.attempt,
        channel_order_id=shipment.channel_order_id,
        state=shipment.state,
        provider_order_id=shipment.provider_order_id,
        provider_shipment_id=shipment.provider_shipment_id,
        awb_code=shipment.awb_code,
        courier_company_id=shipment.courier_company_id,
        courier_name=shipment.courier_name,
        tracking_url=shipment.tracking_url,
        label_url=shipment.label_url,
        manifest_url=shipment.manifest_url,
        pickup_location=shipment.pickup_location,
        pickup_scheduled_date=shipment.pickup_scheduled_date,
        pickup_token_number=shipment.pickup_token_number,
        provider_etd=shipment.provider_etd,
        package=PackageInput(
            weight_kg=shipment.weight_kg,
            length_cm=shipment.length_cm,
            breadth_cm=shipment.breadth_cm,
            height_cm=shipment.height_cm,
        ),
        applied_weight_kg=shipment.applied_weight_kg,
        payment_mode=shipment.payment_mode,
        declared_value=shipment.declared_value,
        cod_amount=shipment.cod_amount,
        freight_charge=shipment.freight_charge,
        cod_charge=shipment.cod_charge,
        provider_status_code=shipment.provider_status_code,
        provider_status_label=shipment.provider_status_label,
        last_event_at=shipment.last_event_at,
        pending_operation=shipment.pending_operation,
        operation_status=shipment.operation_status,
        last_error=shipment.last_error,
        last_error_at=shipment.last_error_at,
        retry_count=shipment.retry_count,
        last_synced_at=shipment.last_synced_at,
        picked_up_at=shipment.picked_up_at,
        delivered_at=shipment.delivered_at,
        cancelled_at=shipment.cancelled_at,
        created_at=shipment.created_at,
        updated_at=shipment.updated_at,
        actions=actions(shipment),
        recovery_hint=recovery_hint(shipment),
        events=[
            ShipmentEventRead(
                source=event.source,
                provider_status_code=event.provider_status_code,
                courier_status=event.courier_status,
                status_label=event.status_label,
                state=event.state,
                activity=event.activity,
                location=event.location,
                occurred_at=event.occurred_at,
            )
            for event in shipment.events
        ]
        if with_events
        else [],
    )


def customer_shipment_read(shipment: Shipment | None) -> CustomerShipmentRead | None:
    if shipment is None or shipment.state == ShipmentState.PENDING_FULFILMENT.value:
        return None
    return CustomerShipmentRead(
        state=shipment.state,
        status_label=shipment.provider_status_label,
        courier_name=shipment.courier_name,
        awb_code=shipment.awb_code,
        tracking_url=shipment.tracking_url,
        provider_etd=shipment.provider_etd,
        last_event_at=shipment.last_event_at,
    )


def settings_read(settings: ShippingProviderSettings | None, tenant_id) -> ProviderSettingsRead:
    return ProviderSettingsRead(
        provider="SHIPROCKET",
        is_enabled=bool(settings and settings.is_enabled),
        credentials_configured=shiprocket.is_configured(tenant_id),
        webhook_configured=bool(get_settings().shiprocket_webhook_token),
        pickup_location=settings.pickup_location if settings else None,
        pickup_postcode=settings.pickup_postcode if settings else None,
        fallback_email=settings.fallback_email if settings else None,
        package_defaults=ShipmentService.package_defaults(settings),
        updated_at=settings.updated_at if settings else None,
    )
