"""Booking orders with the courier provider and following them to the door.

Rules this module keeps:

- A provider call that books or changes something is recorded on the
  shipment (`pending_operation`) and committed *before* it is made, so a
  timeout leaves evidence. Retrying first looks the result up at the provider
  (by the channel order id we chose) instead of booking again.
- The shipment state moves only on a provider's success response or a
  tracking event, never on a request merely being sent. Events older than the
  last applied one, or that would move a parcel backwards, are stored but do
  not change the state.
- The order follows the parcel through `OrderService.update_status`, so stock,
  COD collection and the existing refund rules apply unchanged. Nothing here
  refunds money: a cancelled or returned shipment leaves refunds to the
  existing payment workflow.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import NoReturn
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.error_codes import ShipmentErrorCode
from app.core.exceptions import (
    AppError,
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationError,
)
from app.core.money import ZERO, money
from app.orders.constants import (
    ALLOWED_TRANSITIONS,
    MAX_TRACKING_URL_LENGTH,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    TrackingSource,
)
from app.orders.models import Order, OrderTrackingEvent
from app.orders.repository import OrderRepository
from app.orders.service import OrderService
from app.payments.constants import PaymentStatus as CashStatus
from app.shipments import shiprocket
from app.shipments.constants import (
    CANCELLABLE_STATES,
    SHIPROCKET_STATUS_STATES,
    STATE_RANK,
    TERMINAL_STATES,
    TRACKABLE_STATES,
    OperationStatus,
    ShipmentEventSource,
    ShipmentOperation,
    ShipmentPaymentMode,
    ShipmentState,
    ShippingProvider,
)
from app.shipments.models import Shipment, ShipmentEvent, ShippingProviderSettings
from app.shipments.provider import (
    BookedOrder,
    BookingItem,
    BookingRequest,
    CourierRate,
    Package,
    PickupLocation,
    ProviderNotConfiguredError,
    RateQuery,
    ShippingProviderClient,
    ShippingProviderError,
    TrackingUpdate,
)
from app.shipments.schemas import PackageInput, ProviderSettingsUpdate

logger = logging.getLogger(__name__)

SHIPMENT_NOT_FOUND = "Shipment not found"

# Orders that are confirmed and not yet on their way may be booked.
BOOKABLE_ORDER_STATUSES = frozenset(
    {OrderStatus.CONFIRMED, OrderStatus.PROCESSING, OrderStatus.PACKED}
)

# A call still marked IN_PROGRESS after this long was interrupted (process
# restart); it is treated like an unknown outcome and reconciled.
STALE_OPERATION = timedelta(minutes=2)

# Where the order should be once the parcel reaches a state.
ORDER_TARGETS: dict[ShipmentState, OrderStatus] = {
    ShipmentState.PICKED_UP: OrderStatus.SHIPPED,
    ShipmentState.IN_TRANSIT: OrderStatus.SHIPPED,
    ShipmentState.DELIVERY_EXCEPTION: OrderStatus.SHIPPED,
    ShipmentState.RETURN_TO_ORIGIN: OrderStatus.SHIPPED,
    ShipmentState.OUT_FOR_DELIVERY: OrderStatus.OUT_FOR_DELIVERY,
    ShipmentState.DELIVERED: OrderStatus.DELIVERED,
    ShipmentState.RETURNED_TO_ORIGIN: OrderStatus.RETURNED,
}

# Which way to step when several order paths lead to the target.
_STEP_PREFERENCE = (
    OrderStatus.PACKED,
    OrderStatus.PROCESSING,
    OrderStatus.SHIPPED,
    OrderStatus.OUT_FOR_DELIVERY,
    OrderStatus.DELIVERED,
    OrderStatus.RETURNED,
)

STATE_NOTES = {
    ShipmentState.PICKED_UP: "Picked up by the courier",
    ShipmentState.IN_TRANSIT: "In transit",
    ShipmentState.OUT_FOR_DELIVERY: "Out for delivery",
    ShipmentState.DELIVERED: "Delivered",
    ShipmentState.RETURNED_TO_ORIGIN: "Returned to the seller undelivered",
}


def now() -> datetime:
    return datetime.now(timezone.utc)


def order_path(current: OrderStatus, target: OrderStatus) -> list[OrderStatus]:
    """The shortest run of allowed order transitions from `current` to `target`.

    Empty when already there or when the target cannot be reached (a closed
    order, or one already past it). Never passes through CANCELLED.
    """
    if current is target:
        return []
    frontier: list[list[OrderStatus]] = [[current]]
    seen = {current}
    while frontier:
        following: list[list[OrderStatus]] = []
        for path in frontier:
            allowed = ALLOWED_TRANSITIONS.get(path[-1], frozenset())
            for step in _STEP_PREFERENCE:
                if step not in allowed or step in seen:
                    continue
                if step is target:
                    return path[1:] + [step]
                seen.add(step)
                following.append(path + [step])
        frontier = following
    return []


def can_move(current: ShipmentState, new: ShipmentState) -> bool:
    """Whether a tracking event may move a shipment from `current` to `new`."""
    if current is new or current in TERMINAL_STATES:
        return False
    if current is ShipmentState.RETURN_TO_ORIGIN:
        return new is ShipmentState.RETURNED_TO_ORIGIN
    if new in {ShipmentState.CANCELLED, ShipmentState.DELIVERY_EXCEPTION}:
        return True
    if current is ShipmentState.DELIVERY_EXCEPTION:
        return STATE_RANK[new] >= STATE_RANK[ShipmentState.PICKUP_SCHEDULED]
    return STATE_RANK[new] > STATE_RANK[current]


def state_for_code(code: int | None) -> ShipmentState | None:
    return SHIPROCKET_STATUS_STATES.get(code) if code is not None else None


def get_client(tenant_id: UUID) -> ShippingProviderClient:
    """The provider client for live calls. Tests replace this."""
    return shiprocket.ShiprocketClient(shiprocket.credentials(tenant_id))


def provider_failure(exc: ShippingProviderError, hint: str | None = None) -> AppError:
    """A provider failure as an API error the admin can act on."""
    if isinstance(exc, ProviderNotConfiguredError):
        return ServiceUnavailableError(
            exc.message, error_code=ShipmentErrorCode.PROVIDER_NOT_CONFIGURED
        )
    message = exc.message + (f" {hint}" if hint else "")
    if exc.retryable or exc.ambiguous:
        return ServiceUnavailableError(message, error_code=ShipmentErrorCode.PROVIDER_UNAVAILABLE)
    return ConflictError(message, error_code=ShipmentErrorCode.PROVIDER_ERROR)


def recovery_hint(shipment: Shipment) -> str | None:
    """What an admin should do about a failed or unfinished call."""
    operation = shipment.pending_operation
    if operation is None:
        return None
    status = shipment.operation_status
    if status == OperationStatus.UNKNOWN.value:
        return (
            "Shiprocket did not confirm the last step. Retry: the shipment is looked up "
            "first, so nothing is booked twice."
        )
    if status == OperationStatus.FAILED.value:
        if operation == ShipmentOperation.CREATE.value:
            return (
                "Shiprocket refused the booking. Retry a temporary failure, or cancel this "
                "attempt before correcting the address, pickup setup or parcel and rebooking."
            )
        if operation == ShipmentOperation.ASSIGN_AWB.value:
            return (
                "No AWB was assigned. Check the wallet balance or pick another courier from "
                "the rates list, then retry."
            )
        if operation == ShipmentOperation.SCHEDULE_PICKUP.value:
            return "Pickup was not scheduled. Retry, or choose another pickup date."
        return "Retry the last step."
    return "A Shiprocket request for this shipment is in progress."


class ShipmentService:
    """Shipments of one tenant's orders."""

    def __init__(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        client: ShippingProviderClient | None = None,
    ) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self._client = client
        self.orders = OrderRepository(session, tenant_id)

    @property
    def client(self) -> ShippingProviderClient:
        if self._client is None:
            self._client = get_client(self.tenant_id)
        return self._client

    # ------------------------------------------------------------ settings

    async def get_settings(self) -> ShippingProviderSettings | None:
        return await self.session.scalar(
            select(ShippingProviderSettings).where(
                ShippingProviderSettings.tenant_id == self.tenant_id
            )
        )

    async def update_settings(
        self, data: ProviderSettingsUpdate, actor_id: UUID | None
    ) -> ShippingProviderSettings:
        if data.is_enabled and not shiprocket.is_configured(self.tenant_id):
            raise ConflictError(
                "Add SHIPROCKET_EMAIL and SHIPROCKET_PASSWORD to the server environment "
                "before enabling shipments",
                error_code=ShipmentErrorCode.PROVIDER_NOT_CONFIGURED,
            )
        settings = await self.session.scalar(
            select(ShippingProviderSettings)
            .where(ShippingProviderSettings.tenant_id == self.tenant_id)
            .with_for_update()
        )
        if settings is None:
            settings = ShippingProviderSettings(
                tenant_id=self.tenant_id, provider=ShippingProvider.SHIPROCKET.value
            )
            self.session.add(settings)
        package = data.package_defaults
        settings.is_enabled = data.is_enabled
        settings.pickup_location = data.pickup_location
        settings.pickup_postcode = data.pickup_postcode
        settings.fallback_email = str(data.fallback_email) if data.fallback_email else None
        settings.default_weight_kg = package.weight_kg if package else None
        settings.default_length_cm = package.length_cm if package else None
        settings.default_breadth_cm = package.breadth_cm if package else None
        settings.default_height_cm = package.height_cm if package else None
        settings.updated_by_id = actor_id
        await self.session.commit()
        await self.session.refresh(settings)
        return settings

    async def pickup_locations(self) -> list[PickupLocation]:
        """The pickup locations registered in the provider panel, to check the name."""
        try:
            return await self.client.pickup_locations()
        except ShippingProviderError as exc:
            raise provider_failure(exc) from exc

    async def _require_enabled(self) -> ShippingProviderSettings:
        settings = await self.get_settings()
        if settings is None or not settings.is_enabled:
            raise ConflictError(
                "Shipping with Shiprocket is not enabled for this store. Enable it under "
                "Settings > Shipping provider.",
                error_code=ShipmentErrorCode.PROVIDER_DISABLED,
            )
        return settings

    @staticmethod
    def package_defaults(settings: ShippingProviderSettings | None) -> PackageInput | None:
        if settings is None or settings.default_weight_kg is None:
            return None
        return PackageInput(
            weight_kg=settings.default_weight_kg,
            length_cm=settings.default_length_cm,
            breadth_cm=settings.default_breadth_cm,
            height_cm=settings.default_height_cm,
        )

    def _package(
        self, given: PackageInput | None, settings: ShippingProviderSettings | None
    ) -> Package:
        package = given or self.package_defaults(settings)
        if package is None:
            raise ValidationError(
                "Enter the packed parcel's weight and dimensions, or configure package "
                "defaults under Settings > Shipping provider",
                error_code=ShipmentErrorCode.PACKAGE_REQUIRED,
            )
        return Package(
            weight_kg=package.weight_kg,
            length_cm=package.length_cm,
            breadth_cm=package.breadth_cm,
            height_cm=package.height_cm,
        )

    # ------------------------------------------------------------- reading

    async def _order(self, order_id: UUID) -> Order:
        return await OrderService(self.session, self.tenant_id).get(order_id)

    async def for_order(self, order_id: UUID) -> list[Shipment]:
        """Every attempt for the order, newest first."""
        await self._order(order_id)  # 404 for another tenant's order
        return list(
            (
                await self.session.scalars(
                    select(Shipment)
                    .where(Shipment.tenant_id == self.tenant_id, Shipment.order_id == order_id)
                    .order_by(Shipment.attempt.desc())
                )
            ).all()
        )

    async def current_for_order(self, order_id: UUID) -> Shipment | None:
        return await self.session.scalar(
            select(Shipment).where(
                Shipment.tenant_id == self.tenant_id,
                Shipment.order_id == order_id,
                Shipment.state != ShipmentState.CANCELLED.value,
            )
        )

    async def get(self, order_id: UUID, shipment_id: UUID) -> Shipment:
        shipment = await self.session.scalar(
            select(Shipment).where(
                Shipment.tenant_id == self.tenant_id,
                Shipment.order_id == order_id,
                Shipment.id == shipment_id,
            )
        )
        if shipment is None:
            raise NotFoundError(SHIPMENT_NOT_FOUND, error_code=ShipmentErrorCode.NOT_FOUND)
        return shipment

    async def _lock(self, order_id: UUID, shipment_id: UUID) -> Shipment:
        shipment = await self.session.scalar(
            select(Shipment)
            .where(
                Shipment.tenant_id == self.tenant_id,
                Shipment.order_id == order_id,
                Shipment.id == shipment_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if shipment is None:
            raise NotFoundError(SHIPMENT_NOT_FOUND, error_code=ShipmentErrorCode.NOT_FOUND)
        return shipment

    async def reload(self, shipment: Shipment) -> Shipment:
        """The shipment with its events, fresh after commits."""
        await self.session.refresh(shipment)
        return (
            await self.session.scalars(
                select(Shipment)
                .where(Shipment.id == shipment.id)
                .execution_options(populate_existing=True)
            )
        ).one()

    def create_blocked_reason(self, order: Order) -> str | None:
        """Why this order cannot be booked yet, in words for the admin; None if it can."""
        status = OrderStatus(order.status)
        if status not in BOOKABLE_ORDER_STATUSES:
            if status is OrderStatus.PENDING:
                return "Confirm the order before booking a shipment."
            return f"A {status.value} order cannot be booked with a courier."
        if order.payment_method != PaymentMethod.CASH_ON_DELIVERY.value and (
            order.payment_status != PaymentStatus.PAID.value
        ):
            return "The online payment has not been captured yet."
        if order.advance_amount > ZERO:
            advance = order.advance_payment
            if advance is None or advance.status != CashStatus.PAID.value:
                return "The COD advance has not been paid yet."
        if order.delivery_country.strip().lower() not in {"india", "in", "ind"}:
            return "Only deliveries within India can be booked."
        code = order.delivery_postal_code.strip()
        if not (len(code) == 6 and code.isdigit() and code[0] != "0"):
            return "The delivery address needs a valid 6-digit pincode."
        return None

    @staticmethod
    def cod_amount(order: Order) -> Decimal:
        """Cash the courier must collect: the total less anything already paid."""
        if order.payment_method != PaymentMethod.CASH_ON_DELIVERY.value:
            return ZERO
        paid = sum((p.amount for p in order.payments if p.status == CashStatus.PAID.value), ZERO)
        return money(max(order.total_amount - paid, ZERO))

    # --------------------------------------------------------------- rates

    async def rates(
        self, order_id: UUID, package: PackageInput | None
    ) -> tuple[RateQuery, list[CourierRate]]:
        """Verified courier rates for this order's parcel, from the provider."""
        settings = await self._require_enabled()
        order = await self._order(order_id)
        query = RateQuery(
            pickup_postcode=settings.pickup_postcode or "",
            delivery_postcode=order.delivery_postal_code.strip(),
            package=self._package(package, settings),
            cod=self.cod_amount(order) > ZERO,
            declared_value=order.total_amount,
        )
        try:
            return query, await self.client.check_rates(query)
        except ShippingProviderError as exc:
            raise provider_failure(exc) from exc

    # -------------------------------------------------------------- create

    async def create(
        self,
        order_id: UUID,
        *,
        package: PackageInput | None,
        courier_id: str | None,
        actor_id: UUID | None,
    ) -> Shipment:
        settings = await self._require_enabled()
        order = await self.orders.lock(order_id)
        if order is None:
            await self._order(order_id)  # raises the usual 404
        existing = await self.current_for_order(order_id)
        if existing is not None:
            await self.session.rollback()
            raise ConflictError(
                "This order already has a shipment. Retry or cancel it instead of booking another.",
                error_code=ShipmentErrorCode.ALREADY_EXISTS,
            )
        reason = self.create_blocked_reason(order)
        if reason is not None:
            await self.session.rollback()
            raise ConflictError(reason, error_code=ShipmentErrorCode.ORDER_NOT_SHIPPABLE)
        parcel = self._package(package, settings)
        attempt = (
            await self.session.scalar(
                select(func.max(Shipment.attempt)).where(
                    Shipment.tenant_id == self.tenant_id, Shipment.order_id == order_id
                )
            )
            or 0
        ) + 1
        cod = self.cod_amount(order)
        shipment = Shipment(
            tenant_id=self.tenant_id,
            order_id=order.id,
            provider=ShippingProvider.SHIPROCKET.value,
            attempt=attempt,
            channel_order_id=self.channel_order_id(order, attempt),
            state=ShipmentState.PENDING_FULFILMENT.value,
            pickup_location=settings.pickup_location or "",
            weight_kg=parcel.weight_kg,
            length_cm=parcel.length_cm,
            breadth_cm=parcel.breadth_cm,
            height_cm=parcel.height_cm,
            payment_mode=(
                ShipmentPaymentMode.COD if cod > ZERO else ShipmentPaymentMode.PREPAID
            ).value,
            declared_value=order.total_amount,
            cod_amount=cod,
            courier_company_id=courier_id,
            pending_operation=ShipmentOperation.CREATE.value,
            operation_status=OperationStatus.IN_PROGRESS.value,
            retry_count=0,
            created_by_id=actor_id,
        )
        self.session.add(shipment)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError(
                "This order already has a shipment", error_code=ShipmentErrorCode.ALREADY_EXISTS
            ) from exc

        await self._book(shipment, order, settings)
        if courier_id and shipment.state == ShipmentState.SHIPMENT_CREATED.value:
            return await self.assign_awb(order.id, shipment.id, courier_id)
        return await self.reload(shipment)

    @staticmethod
    def channel_order_id(order: Order, attempt: int) -> str:
        """The id the provider files the order under: digits and a dash, as its docs advise."""
        return f"{order.id.int}-{attempt}"

    def _booking(self, shipment: Shipment, order: Order, settings) -> BookingRequest:
        paid_before = order.total_amount - shipment.cod_amount if shipment.cod_amount else ZERO
        return BookingRequest(
            channel_order_id=shipment.channel_order_id,
            order_date=order.created_at,
            pickup_location=shipment.pickup_location,
            customer_name=order.delivery_name,
            address_line_1=order.delivery_address_line_1,
            address_line_2=order.delivery_address_line_2,
            city=order.delivery_city,
            state=order.delivery_state,
            postcode=order.delivery_postal_code.strip(),
            country=order.delivery_country,
            email=order.contact_email or (settings.fallback_email if settings else None),
            phone=order.delivery_phone,
            items=[
                BookingItem(
                    name=f"{item.product_name} - {item.variant_name}"[:200],
                    sku=item.sku,
                    units=item.quantity,
                    selling_price=item.unit_price,
                    discount=ZERO,
                    tax_rate=item.gst_rate,
                    hsn=item.hsn_code,
                )
                for item in order.items
            ],
            cod=shipment.payment_mode == ShipmentPaymentMode.COD.value,
            shipping_charges=order.shipping_amount,
            transaction_charges=order.cod_fee,
            # A COD advance already paid is not collected again at the door.
            total_discount=order.discount_amount + paid_before,
            # Shiprocket does not compute totals; for COD this is what the
            # courier collects, for prepaid the value of the order.
            sub_total=shipment.cod_amount
            if shipment.payment_mode == ShipmentPaymentMode.COD.value
            else order.total_amount,
            package=Package(
                weight_kg=shipment.weight_kg,
                length_cm=shipment.length_cm,
                breadth_cm=shipment.breadth_cm,
                height_cm=shipment.height_cm,
            ),
        )

    async def _book(self, shipment: Shipment, order: Order, settings) -> None:
        if not (order.contact_email or (settings and settings.fallback_email)):
            await self._fail(
                shipment,
                ShippingProviderError(
                    "Shiprocket needs a buyer email. Add a fallback email under Settings > "
                    "Shipping provider."
                ),
            )
        try:
            booked = await self.client.create_order(self._booking(shipment, order, settings))
        except ShippingProviderError as exc:
            await self._fail(shipment, exc)
        except AppError as exc:
            await self._fail(shipment, ShippingProviderError(exc.message))
        await self._adopt(shipment, booked)

    async def _adopt(self, shipment: Shipment, booked: BookedOrder) -> None:
        """Record a provider order we created (or found again) on the shipment."""
        shipment = await self._lock(shipment.order_id, shipment.id)
        shipment.provider_order_id = booked.provider_order_id
        shipment.provider_shipment_id = booked.provider_shipment_id
        if booked.is_cancelled:
            await self._mark_cancelled(shipment, "Cancellation confirmed by the courier")
            return
        if booked.provider_shipment_id is None:
            await self._fail(
                shipment,
                ShippingProviderError(
                    "Booking exists but shipment is not ready yet", ambiguous=True
                ),
            )
        if shipment.state == ShipmentState.PENDING_FULFILMENT.value:
            shipment.state = ShipmentState.SHIPMENT_CREATED.value
        if booked.awb_code:
            await self._record_awb(
                shipment, booked.awb_code, booked.courier_id, booked.courier_name
            )
        self._clear_operation(shipment)
        await self.session.commit()

    # ---------------------------------------------------------- operations

    async def _start(
        self, order_id: UUID, shipment_id: UUID, operation: ShipmentOperation, allowed
    ) -> Shipment:
        shipment = await self._lock(order_id, shipment_id)
        state = ShipmentState(shipment.state)
        if self._in_flight(shipment):
            await self.session.rollback()
            raise ConflictError(
                "Another Shiprocket request for this shipment is still running",
                error_code=ShipmentErrorCode.OPERATION_IN_PROGRESS,
            )
        # Cancelling may override an unfinished step (it looks the booking up
        # first); anything else must not run over one, and an unknown outcome
        # is only resolved by Retry, which checks before re-sending.
        if (
            operation is not ShipmentOperation.CANCEL
            and shipment.pending_operation is not None
            and (
                shipment.pending_operation != operation.value
                or shipment.operation_status != OperationStatus.FAILED.value
            )
        ):
            await self.session.rollback()
            raise ConflictError(
                f"Finish the pending {shipment.pending_operation.replace('_', ' ').lower()} "
                "step first (Retry)",
                error_code=ShipmentErrorCode.INVALID_STATE,
            )
        if state not in allowed:
            await self.session.rollback()
            raise ConflictError(
                f"A shipment that is {state.value} cannot do this",
                error_code=ShipmentErrorCode.INVALID_STATE,
            )
        shipment.pending_operation = operation.value
        shipment.operation_status = OperationStatus.IN_PROGRESS.value
        return shipment

    @staticmethod
    def _in_flight(shipment: Shipment) -> bool:
        return (
            shipment.operation_status == OperationStatus.IN_PROGRESS.value
            and shipment.updated_at is not None
            and now() - shipment.updated_at < STALE_OPERATION
        )

    async def assign_awb(
        self, order_id: UUID, shipment_id: UUID, courier_id: str | None
    ) -> Shipment:
        shipment = await self._start(
            order_id,
            shipment_id,
            ShipmentOperation.ASSIGN_AWB,
            {ShipmentState.SHIPMENT_CREATED},
        )
        if courier_id:
            shipment.courier_company_id = courier_id
        await self.session.commit()
        await self._call_assign(shipment)
        return await self.reload(shipment)

    async def _call_assign(self, shipment: Shipment) -> None:
        try:
            result = await self.client.assign_awb(
                shipment.provider_shipment_id or "", shipment.courier_company_id
            )
        except ShippingProviderError as exc:
            await self._fail(shipment, exc)
        shipment = await self._lock(shipment.order_id, shipment.id)
        await self._record_awb(shipment, result.awb_code, result.courier_id, result.courier_name)
        shipment.applied_weight_kg = result.applied_weight_kg
        shipment.pickup_scheduled_date = (
            result.pickup_scheduled_date or shipment.pickup_scheduled_date
        )
        self._clear_operation(shipment)
        await self.session.commit()
        await self._record_charges(shipment)

    async def _record_awb(
        self, shipment: Shipment, awb: str, courier_id: str | None, courier_name: str | None
    ) -> None:
        shipment.awb_code = awb
        shipment.courier_company_id = courier_id or shipment.courier_company_id
        shipment.courier_name = courier_name or shipment.courier_name
        if STATE_RANK[ShipmentState(shipment.state)] < STATE_RANK[ShipmentState.READY_TO_SHIP]:
            shipment.state = ShipmentState.READY_TO_SHIP.value
        shipment.next_sync_at = now() + self._interval()
        # The order's own shipment fields are what the customer pages show.
        order = await self.orders.get(shipment.order_id)
        if order is not None:
            order.courier_name = shipment.courier_name
            order.tracking_number = awb

    async def _record_charges(self, shipment: Shipment) -> None:
        """Best effort: the chosen courier's quoted freight and COD charges."""
        settings = await self.get_settings()
        if settings is None or not settings.pickup_postcode or not shipment.courier_company_id:
            return
        order = await self.orders.get(shipment.order_id)
        if order is None:
            return
        try:
            rates = await self.client.check_rates(
                RateQuery(
                    pickup_postcode=settings.pickup_postcode,
                    delivery_postcode=order.delivery_postal_code.strip(),
                    package=Package(
                        shipment.applied_weight_kg or shipment.weight_kg,
                        shipment.length_cm,
                        shipment.breadth_cm,
                        shipment.height_cm,
                    ),
                    cod=shipment.payment_mode == ShipmentPaymentMode.COD.value,
                    declared_value=shipment.declared_value,
                )
            )
        except ShippingProviderError:
            logger.info("Courier rates unavailable for shipment %s", shipment.id)
            return
        for rate in rates:
            if rate.courier_id == shipment.courier_company_id:
                shipment.freight_charge = rate.freight_charge
                shipment.cod_charge = rate.cod_charge
                await self.session.commit()
                return

    async def schedule_pickup(
        self, order_id: UUID, shipment_id: UUID, pickup_date: date | None
    ) -> Shipment:
        shipment = await self._start(
            order_id,
            shipment_id,
            ShipmentOperation.SCHEDULE_PICKUP,
            {ShipmentState.READY_TO_SHIP, ShipmentState.DELIVERY_EXCEPTION},
        )
        if not shipment.awb_code:
            await self.session.rollback()
            raise ConflictError(
                "Assign a courier (AWB) before scheduling a pickup",
                error_code=ShipmentErrorCode.INVALID_STATE,
            )
        if shipment.picked_up_at is not None:
            await self.session.rollback()
            raise ConflictError("The parcel has already been collected")
        await self.session.commit()
        await self._call_pickup(shipment, pickup_date)
        return await self.reload(shipment)

    async def _call_pickup(self, shipment: Shipment, pickup_date: date | None) -> None:
        try:
            result = await self.client.schedule_pickup(
                shipment.provider_shipment_id or "", pickup_date
            )
        except ShippingProviderError as exc:
            await self._fail(shipment, exc)
        shipment = await self._lock(shipment.order_id, shipment.id)
        shipment.pickup_scheduled_date = result.scheduled_date
        shipment.pickup_token_number = result.token_number
        if can_move(ShipmentState(shipment.state), ShipmentState.PICKUP_SCHEDULED):
            shipment.state = ShipmentState.PICKUP_SCHEDULED.value
        self._clear_operation(shipment)
        await self.session.commit()

    async def label(self, order_id: UUID, shipment_id: UUID) -> Shipment:
        shipment = await self.get(order_id, shipment_id)
        if not shipment.awb_code or shipment.state == ShipmentState.CANCELLED.value:
            raise ConflictError(
                "A label needs an assigned AWB", error_code=ShipmentErrorCode.INVALID_STATE
            )
        try:
            shipment.label_url = await self.client.generate_label(
                shipment.provider_shipment_id or ""
            )
        except ShippingProviderError as exc:
            raise provider_failure(exc) from exc
        await self.session.commit()
        return await self.reload(shipment)

    async def manifest(self, order_id: UUID, shipment_id: UUID) -> Shipment:
        shipment = await self.get(order_id, shipment_id)
        if (
            STATE_RANK[ShipmentState(shipment.state)] < STATE_RANK[ShipmentState.PICKUP_SCHEDULED]
            or shipment.state == ShipmentState.CANCELLED.value
        ):
            raise ConflictError(
                "Schedule the pickup before generating the manifest",
                error_code=ShipmentErrorCode.INVALID_STATE,
            )
        try:
            shipment.manifest_url = await self.client.generate_manifest(
                shipment.provider_shipment_id or "", shipment.provider_order_id or ""
            )
        except ShippingProviderError as exc:
            raise provider_failure(exc) from exc
        await self.session.commit()
        return await self.reload(shipment)

    async def cancel(self, order_id: UUID, shipment_id: UUID) -> Shipment:
        """Cancel the booking with the courier. The order itself is left as it is."""
        shipment = await self._lock(order_id, shipment_id)
        if (
            shipment.provider_order_id is None
            and shipment.pending_operation == ShipmentOperation.CREATE.value
            and shipment.operation_status == OperationStatus.FAILED.value
        ):
            await self._mark_cancelled(shipment, "Booking was refused; local attempt cancelled")
            return await self.reload(shipment)
        shipment = await self._start(
            order_id, shipment_id, ShipmentOperation.CANCEL, CANCELLABLE_STATES
        )
        await self.session.commit()
        await self._call_cancel(shipment)
        return await self.reload(shipment)

    async def _call_cancel(self, shipment: Shipment) -> None:
        if shipment.provider_order_id is None:
            # Never confirmed at the provider: make sure it really does not
            # exist there before letting it go.
            try:
                found = await self.client.find_order(shipment.channel_order_id)
            except ShippingProviderError as exc:
                await self._fail(shipment, exc)
            if found is not None:
                shipment.provider_order_id = found.provider_order_id
                shipment.provider_shipment_id = found.provider_shipment_id
            else:
                await self._fail(
                    shipment,
                    ShippingProviderError(
                        "The original booking is still unconfirmed. Check Shiprocket "
                        "before cancelling; no replacement booking can be created yet.",
                        ambiguous=True,
                    ),
                )
        if shipment.provider_order_id is not None:
            try:
                await self.client.cancel_order(shipment.provider_order_id)
            except ShippingProviderError as exc:
                await self._fail(shipment, exc)
        await self._mark_cancelled(shipment, "Shipment cancelled with the courier")

    async def _mark_cancelled(self, shipment: Shipment, note: str) -> None:
        # Production sessions disable autoflush. Preserve provider identifiers
        # just reconciled above before refreshing the row under its lock.
        await self.session.flush()
        shipment = await self._lock(shipment.order_id, shipment.id)
        if ShipmentState(shipment.state) in TERMINAL_STATES and (
            shipment.state != ShipmentState.CANCELLED.value
        ):
            await self._fail(
                shipment,
                ShippingProviderError(
                    "The courier reported a terminal delivery state during cancellation. "
                    "Check the provider panel before taking further action.",
                    ambiguous=True,
                ),
            )
        shipment.state = ShipmentState.CANCELLED.value
        shipment.cancelled_at = now()
        shipment.next_sync_at = None
        self._clear_operation(shipment)
        order = await self.orders.get(shipment.order_id)
        if order is not None and shipment.awb_code and order.tracking_number == shipment.awb_code:
            order.courier_name = None
            order.tracking_number = None
            order.tracking_url = None
        if order is not None and shipment.provider_order_id is not None:
            self.session.add(
                OrderTrackingEvent(
                    tenant_id=self.tenant_id,
                    order_id=shipment.order_id,
                    status=None,
                    description=note,
                    source=TrackingSource.SYSTEM.value,
                    occurred_at=now(),
                )
            )
        await self.session.commit()

    async def retry(self, order_id: UUID, shipment_id: UUID) -> Shipment:
        """Finish the last unfinished step, looking its result up first when unknown."""
        shipment = await self._lock(order_id, shipment_id)
        operation = shipment.pending_operation
        if operation is None:
            await self.session.rollback()
            raise ConflictError(
                "Nothing to retry on this shipment", error_code=ShipmentErrorCode.INVALID_STATE
            )
        if self._in_flight(shipment):
            await self.session.rollback()
            raise ConflictError(
                "Another Shiprocket request for this shipment is still running",
                error_code=ShipmentErrorCode.OPERATION_IN_PROGRESS,
            )
        uncertain = shipment.operation_status != OperationStatus.FAILED.value
        shipment.operation_status = OperationStatus.IN_PROGRESS.value
        shipment.retry_count += 1
        await self.session.commit()

        if operation == ShipmentOperation.CREATE.value:
            await self._retry_create(shipment, uncertain)
        elif operation == ShipmentOperation.ASSIGN_AWB.value:
            if uncertain:
                if await self._found_awb(shipment):
                    return await self.reload(shipment)
                await self._fail(
                    shipment,
                    ShippingProviderError(
                        "AWB assignment remains unconfirmed. Check the Shiprocket panel, "
                        "then retry reconciliation; the assignment will not be resent.",
                        ambiguous=True,
                    ),
                )
            await self._call_assign(shipment)
        elif operation == ShipmentOperation.SCHEDULE_PICKUP.value:
            if uncertain:
                # A pickup request is not idempotent. Tracking can confirm it;
                # an empty or delayed tracking result cannot prove it failed.
                try:
                    update = await self.client.track(shipment.awb_code or "")
                except ShippingProviderError as exc:
                    await self._fail(shipment, exc, keep_unknown=True)
                await self.apply_update(shipment, update, ShipmentEventSource.POLL)
                if shipment.pending_operation is None:
                    return await self.reload(shipment)
                await self._fail(
                    shipment,
                    ShippingProviderError(
                        "Pickup is still unconfirmed. Check the Shiprocket panel; "
                        "refresh tracking after confirming the pickup there.",
                        ambiguous=True,
                    ),
                )
            await self._call_pickup(shipment, None)
        elif operation == ShipmentOperation.CANCEL.value:
            if uncertain and await self._found_cancelled(shipment):
                return await self.reload(shipment)
            await self._call_cancel(shipment)
        return await self.reload(shipment)

    async def _retry_create(self, shipment: Shipment, uncertain: bool) -> None:
        if uncertain:
            try:
                found = await self.client.find_order(shipment.channel_order_id)
            except ShippingProviderError as exc:
                await self._fail(shipment, exc, keep_unknown=True)
            if found is not None:
                await self._adopt(shipment, found)
                return
            await self._fail(
                shipment,
                ShippingProviderError(
                    "No booking is visible yet. Check Shiprocket using reference "
                    f"{shipment.channel_order_id}, then retry reconciliation. "
                    "An unconfirmed booking will not be sent again automatically.",
                    ambiguous=True,
                ),
            )
        order = await self._order(shipment.order_id)
        reason = self.create_blocked_reason(order)
        if reason is not None:
            await self._fail(
                shipment,
                ShippingProviderError(f"{reason} Cancel this shipment instead."),
                keep_unknown=False,
            )
        try:
            settings = await self._require_enabled()
        except AppError as exc:
            await self._fail(shipment, ShippingProviderError(exc.message))
        await self._book(shipment, order, settings)

    async def _found_awb(self, shipment: Shipment) -> bool:
        try:
            booked = await self.client.get_order(shipment.provider_order_id or "")
        except ShippingProviderError as exc:
            await self._fail(shipment, exc, keep_unknown=True)
        if booked is None or not booked.awb_code:
            return False
        shipment = await self._lock(shipment.order_id, shipment.id)
        if booked.is_cancelled:
            await self._mark_cancelled(shipment, "Cancellation confirmed by the courier")
            return True
        await self._record_awb(shipment, booked.awb_code, booked.courier_id, booked.courier_name)
        self._clear_operation(shipment)
        await self.session.commit()
        return True

    async def _found_cancelled(self, shipment: Shipment) -> bool:
        if shipment.provider_order_id is None:
            return False
        try:
            booked = await self.client.get_order(shipment.provider_order_id)
        except ShippingProviderError as exc:
            await self._fail(shipment, exc, keep_unknown=True)
        if booked is None or not booked.is_cancelled:
            return False
        await self._mark_cancelled(shipment, "Shipment cancelled with the courier")
        return True

    async def _fail(
        self, shipment: Shipment, exc: ShippingProviderError, *, keep_unknown: bool = False
    ) -> NoReturn:
        """Record a failed call on the shipment, commit, and raise it for the admin."""
        unknown = exc.ambiguous or (
            keep_unknown and shipment.operation_status != OperationStatus.FAILED.value
        )
        shipment.operation_status = (
            OperationStatus.UNKNOWN if unknown else OperationStatus.FAILED
        ).value
        shipment.last_error = exc.message[:500]
        shipment.last_error_at = now()
        await self.session.commit()
        raise provider_failure(exc, recovery_hint(shipment))

    @staticmethod
    def _clear_operation(shipment: Shipment) -> None:
        shipment.pending_operation = None
        shipment.operation_status = None
        shipment.last_error = None

    def _interval(self) -> timedelta:
        return timedelta(minutes=max(5, get_settings().shipment_sync_interval_minutes))

    # ------------------------------------------------------------ tracking

    async def sync(self, order_id: UUID, shipment_id: UUID) -> Shipment:
        """Fetch tracking now (the admin's "Refresh tracking")."""
        shipment = await self._lock(order_id, shipment_id)
        if not shipment.awb_code:
            await self.session.rollback()
            raise ConflictError(
                "Nothing to track before an AWB is assigned",
                error_code=ShipmentErrorCode.INVALID_STATE,
            )
        try:
            update = await self.client.track(shipment.awb_code)
        except ShippingProviderError as exc:
            await self.session.rollback()
            raise provider_failure(exc) from exc
        await self.apply_update(shipment, update, ShipmentEventSource.POLL)
        return await self.reload(shipment)

    async def apply_update(
        self, shipment: Shipment, update: TrackingUpdate, source: ShipmentEventSource
    ) -> bool:
        """Store the provider's events and move the shipment, then the order.

        Idempotent: an event already stored is skipped, and the state only
        moves forward and only on an event newer than the last one applied.
        Returns whether the state changed.
        """
        known = set(
            (
                await self.session.scalars(
                    select(ShipmentEvent.dedupe_key).where(ShipmentEvent.shipment_id == shipment.id)
                )
            ).all()
        )
        for scan in sorted(update.scans, key=lambda s: s.occurred_at):
            key = "|".join(
                [
                    scan.occurred_at.astimezone(timezone.utc).isoformat(),
                    scan.courier_status or "",
                    str(scan.status_code or ""),
                    (scan.activity or "")[:80],
                ]
            )[:200]
            if key in known:
                continue
            known.add(key)
            mapped = state_for_code(scan.status_code)
            self.session.add(
                ShipmentEvent(
                    tenant_id=self.tenant_id,
                    shipment_id=shipment.id,
                    source=source.value,
                    provider_status_code=scan.status_code,
                    courier_status=scan.courier_status,
                    status_label=scan.status_label,
                    state=mapped.value if mapped else None,
                    activity=scan.activity,
                    location=scan.location,
                    occurred_at=scan.occurred_at,
                    dedupe_key=key,
                    raw=scan.raw,
                )
            )
            if scan.activity or scan.status_label:
                self.session.add(
                    OrderTrackingEvent(
                        tenant_id=self.tenant_id,
                        order_id=shipment.order_id,
                        status=None,
                        description=(scan.activity or scan.status_label or "")[:255],
                        location=scan.location,
                        source=TrackingSource.COURIER.value,
                        occurred_at=scan.occurred_at,
                    )
                )

        # The provider's headline status is the authority on where the
        # parcel is; the newest scan dates it when the update itself does not.
        headline = state_for_code(update.status_code)
        at = update.occurred_at or max((s.occurred_at for s in update.scans), default=None)
        if update.status_code is not None or update.status_label:
            stamp = at.astimezone(timezone.utc).isoformat() if at else ""
            key = f"status|{update.status_code}|{update.status_label}|{stamp}"[:200]
            if key not in known:
                self.session.add(
                    ShipmentEvent(
                        tenant_id=self.tenant_id,
                        shipment_id=shipment.id,
                        source=source.value,
                        provider_status_code=update.status_code,
                        status_label=update.status_label,
                        state=headline.value if headline else None,
                        occurred_at=at or now(),
                        dedupe_key=key,
                        raw=update.raw,
                    )
                )

        changed = False
        if headline is not None and (at is not None or source is ShipmentEventSource.POLL):
            changed = self._transition(shipment, headline, at or now(), update)

        if update.etd:
            shipment.provider_etd = update.etd
        if update.track_url:
            shipment.tracking_url = update.track_url
        if update.courier_name and not shipment.courier_name:
            shipment.courier_name = update.courier_name
        if shipment.last_error and shipment.last_error.startswith("Tracking:"):
            shipment.last_error = None
        shipment.last_synced_at = now()
        shipment.next_sync_at = (
            now() + self._interval() if ShipmentState(shipment.state) in TRACKABLE_STATES else None
        )
        order = await self.orders.get(shipment.order_id)
        if order is not None and shipment.awb_code and order.tracking_number == shipment.awb_code:
            if shipment.state == ShipmentState.CANCELLED.value:
                order.courier_name = None
                order.tracking_number = None
                order.tracking_url = None
            elif shipment.tracking_url and len(shipment.tracking_url) <= MAX_TRACKING_URL_LENGTH:
                order.tracking_url = shipment.tracking_url
        await self.session.commit()

        # Retrying this also repairs an interruption after the shipment commit
        # but before the corresponding order transitions were committed.
        await self._sync_order(shipment)
        return changed

    def _transition(
        self, shipment: Shipment, new: ShipmentState, at: datetime, update: TrackingUpdate
    ) -> bool:
        current = ShipmentState(shipment.state)
        if shipment.last_event_at is not None and at < shipment.last_event_at:
            return False  # stale: an older event arriving late
        if (
            shipment.picked_up_at is not None
            and STATE_RANK[new] < STATE_RANK[ShipmentState.PICKED_UP]
        ):
            return False
        if not can_move(current, new):
            if current is new:
                shipment.last_event_at = at
                shipment.provider_status_code = update.status_code
                shipment.provider_status_label = update.status_label
            return False
        shipment.state = new.value
        shipment.provider_status_code = update.status_code
        shipment.provider_status_label = update.status_label
        shipment.last_event_at = at
        if (
            not shipment.picked_up_at
            and STATE_RANK[new] >= STATE_RANK[ShipmentState.PICKED_UP]
            and new not in {ShipmentState.DELIVERY_EXCEPTION, ShipmentState.CANCELLED}
        ):
            shipment.picked_up_at = at
        if new is ShipmentState.DELIVERED:
            shipment.delivered_at = at
        if new is ShipmentState.CANCELLED:
            shipment.cancelled_at = at
            self._clear_operation(shipment)
        if (
            shipment.pending_operation == ShipmentOperation.SCHEDULE_PICKUP.value
            and STATE_RANK[new] >= STATE_RANK[ShipmentState.PICKUP_SCHEDULED]
        ):
            self._clear_operation(shipment)
        return True

    async def _sync_order(self, shipment: Shipment) -> None:
        """Move the order along with the parcel, by the order's own rules."""
        state = ShipmentState(shipment.state)
        target = ORDER_TARGETS.get(state)
        if target is None:
            return
        if state is ShipmentState.DELIVERY_EXCEPTION and shipment.picked_up_at is None:
            return  # a pickup failure: the parcel has not left
        orders = OrderService(self.session, self.tenant_id)
        order = await orders.get(shipment.order_id)
        order_id, order_number = order.id, order.order_number
        shipment_id = shipment.id
        current = OrderStatus(order.status)
        path = order_path(current, target)
        for step in path:
            try:
                await orders.update_status(
                    order_id,
                    step,
                    note=self._step_note(step, shipment),
                    source=TrackingSource.COURIER,
                )
            except AppError as exc:
                await self.session.rollback()
                logger.info(
                    "Order %s left at %s after courier status %s: %s",
                    order_number,
                    current.value,
                    state.value,
                    exc.message,
                )
                failed = await self._lock(order_id, shipment_id)
                message = (
                    f"Courier reports {state.value.replace('_', ' ').lower()}; "
                    f"order not moved to {step.value}: {exc.message}"
                )[:255]
                failed.last_error = message
                failed.last_error_at = now()
                await self.session.commit()
                return
        if shipment.last_error and shipment.last_error.startswith("Courier reports "):
            shipment.last_error = None
            await self.session.commit()

    @staticmethod
    def _step_note(step: OrderStatus, shipment: Shipment) -> str:
        courier = shipment.courier_name or "the courier"
        if step is OrderStatus.PACKED:
            return "Packed and handed to the courier"
        if step is OrderStatus.SHIPPED:
            return f"Shipped with {courier} (AWB {shipment.awb_code})"[:255]
        if step is OrderStatus.RETURNED:
            return "Returned to the seller undelivered (RTO)"
        return shipment.provider_status_label or step.value.replace("_", " ").capitalize()

    # ------------------------------------------------------ background work

    async def due_for_sync(self, limit: int = 100) -> list[Shipment]:
        return list(
            (
                await self.session.scalars(
                    select(Shipment)
                    .where(
                        Shipment.tenant_id == self.tenant_id,
                        Shipment.state.in_([s.value for s in TRACKABLE_STATES]),
                        Shipment.awb_code.is_not(None),
                        (Shipment.next_sync_at.is_(None)) | (Shipment.next_sync_at <= now()),
                    )
                    .order_by(Shipment.next_sync_at.asc().nulls_first())
                    .limit(limit)
                )
            ).all()
        )

    async def unconfirmed_bookings(self, limit: int = 50) -> list[Shipment]:
        """Creates whose outcome is unknown, to look up (never to re-send)."""
        cutoff = now() - STALE_OPERATION
        return list(
            (
                await self.session.scalars(
                    select(Shipment)
                    .where(
                        Shipment.tenant_id == self.tenant_id,
                        Shipment.pending_operation == ShipmentOperation.CREATE.value,
                        Shipment.operation_status.in_(
                            [OperationStatus.UNKNOWN.value, OperationStatus.IN_PROGRESS.value]
                        ),
                        Shipment.updated_at < cutoff,
                    )
                    .limit(limit)
                )
            ).all()
        )

    async def run_background_sync(self) -> dict[str, int]:
        """One pass for the tenant: reconcile unknown bookings, refresh tracking."""
        counts = {"reconciled": 0, "tracked": 0, "failed": 0}
        settings = await self.get_settings()
        if settings is None or not settings.is_enabled:
            return counts
        for shipment in await self.unconfirmed_bookings():
            try:
                found = await self.client.find_order(shipment.channel_order_id)
            except ShippingProviderError:
                counts["failed"] += 1
                continue
            if found is not None:
                try:
                    await self._adopt(shipment, found)
                except AppError:
                    counts["failed"] += 1
                else:
                    counts["reconciled"] += 1
            elif shipment.operation_status == OperationStatus.IN_PROGRESS.value:
                shipment.operation_status = OperationStatus.UNKNOWN.value
                await self.session.commit()
        for shipment in await self.due_for_sync():
            try:
                update = await self.client.track(shipment.awb_code or "")
            except ShippingProviderError as exc:
                shipment.next_sync_at = now() + self._interval()
                shipment.last_error = f"Tracking: {exc.message}"[:500]
                shipment.last_error_at = now()
                await self.session.commit()
                counts["failed"] += 1
                continue
            locked = await self._lock(shipment.order_id, shipment.id)
            await self.apply_update(locked, update, ShipmentEventSource.POLL)
            counts["tracked"] += 1
        return counts


async def handle_webhook(session: AsyncSession, payload: dict) -> str:
    """Apply a Shiprocket tracking webhook to whichever tenant's shipment it names.

    Authenticity is checked by the router. Unknown AWBs are acknowledged and
    ignored, so Shiprocket does not keep retrying them.
    """
    update = shiprocket.parse_webhook(payload)
    if not update.awb_code:
        return "ignored"
    shipment = await session.scalar(
        select(Shipment)
        .where(
            Shipment.provider == ShippingProvider.SHIPROCKET.value,
            Shipment.awb_code == update.awb_code,
        )
        .with_for_update()
    )
    if shipment is None:
        await session.rollback()
        return "unknown_awb"
    service = ShipmentService(session, shipment.tenant_id)
    changed = await service.apply_update(shipment, update, ShipmentEventSource.WEBHOOK)
    return "applied" if changed else "recorded"
