"""Courier shipments for orders, their tracking history, and per-tenant provider settings."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    and_,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.catalogue.constants import PRICE_PRECISION, PRICE_SCALE
from app.models.base import Base, IdMixin, TenantMixin, TimestampMixin
from app.shipments.constants import (
    MAX_ACTIVITY_LENGTH,
    MAX_AWB_LENGTH,
    MAX_COURIER_NAME_LENGTH,
    MAX_DEDUPE_KEY_LENGTH,
    MAX_ERROR_LENGTH,
    MAX_LOCATION_LENGTH,
    MAX_PICKUP_LOCATION_LENGTH,
    MAX_PROVIDER_ID_LENGTH,
    MAX_STATUS_LABEL_LENGTH,
    MAX_URL_LENGTH,
    OperationStatus,
    ShipmentEventSource,
    ShipmentOperation,
    ShipmentPaymentMode,
    ShipmentState,
    ShippingProvider,
)


def _values(enum) -> str:
    return ", ".join(f"'{member.value}'" for member in enum)


WEIGHT = Numeric(7, 3)
DIMENSION = Numeric(6, 1)
MONEY = Numeric(PRICE_PRECISION, PRICE_SCALE)


class Shipment(IdMixin, TenantMixin, TimestampMixin, Base):
    """One booking of an order with a courier provider.

    An order has at most one shipment that is not CANCELLED; a cancelled one
    stays as history and a new attempt gets the next `attempt` number, so the
    id sent to the provider (`channel_order_id`) is never reused -- Shiprocket
    refuses ids of cancelled orders.
    """

    __tablename__ = "shipments"

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_shipments_tenant_id_id"),
        UniqueConstraint("order_id", "attempt", name="uq_shipments_order_attempt"),
        UniqueConstraint(
            "provider", "channel_order_id", name="uq_shipments_provider_channel_order"
        ),
        UniqueConstraint("provider", "awb_code", name="uq_shipments_provider_awb"),
        ForeignKeyConstraint(
            ["tenant_id", "order_id"],
            ["orders.tenant_id", "orders.id"],
            name="fk_shipments_tenant_order_orders",
            ondelete="CASCADE",
        ),
        CheckConstraint(f"state IN ({_values(ShipmentState)})", name="state_valid"),
        CheckConstraint(f"provider IN ({_values(ShippingProvider)})", name="provider_valid"),
        CheckConstraint(
            f"payment_mode IN ({_values(ShipmentPaymentMode)})", name="payment_mode_valid"
        ),
        CheckConstraint(
            f"pending_operation IS NULL OR pending_operation IN ({_values(ShipmentOperation)})",
            name="pending_operation_valid",
        ),
        CheckConstraint(
            f"operation_status IS NULL OR operation_status IN ({_values(OperationStatus)})",
            name="operation_status_valid",
        ),
        CheckConstraint(
            "(pending_operation IS NULL) = (operation_status IS NULL)",
            name="operation_has_status",
        ),
        CheckConstraint("attempt >= 1", name="attempt_positive"),
        CheckConstraint(
            "weight_kg > 0 AND length_cm > 0 AND breadth_cm > 0 AND height_cm > 0",
            name="package_positive",
        ),
        CheckConstraint("declared_value >= 0", name="declared_value_not_negative"),
        CheckConstraint(
            "cod_amount >= 0 AND (payment_mode = 'COD' OR cod_amount = 0)",
            name="cod_amount_only_for_cod",
        ),
        CheckConstraint("retry_count >= 0", name="retry_count_not_negative"),
        # One live booking per order; cancelled attempts are history.
        Index(
            "uq_shipments_one_open_per_order",
            "tenant_id",
            "order_id",
            unique=True,
            postgresql_where=text("state <> 'CANCELLED'"),
        ),
        Index("ix_shipments_tenant_id_order_id", "tenant_id", "order_id"),
        Index("ix_shipments_tenant_id_next_sync_at", "tenant_id", "next_sync_at"),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    provider: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ShippingProvider.SHIPROCKET.value
    )

    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # The order id sent to the provider. Fixed before the first call, so a
    # timed-out create can be looked up by it instead of booked twice.
    channel_order_id: Mapped[str] = mapped_column(String(MAX_PROVIDER_ID_LENGTH), nullable=False)

    state: Mapped[str] = mapped_column(
        String(30), nullable=False, default=ShipmentState.PENDING_FULFILMENT.value
    )

    provider_order_id: Mapped[str | None] = mapped_column(
        String(MAX_PROVIDER_ID_LENGTH), nullable=True
    )
    provider_shipment_id: Mapped[str | None] = mapped_column(
        String(MAX_PROVIDER_ID_LENGTH), nullable=True
    )
    awb_code: Mapped[str | None] = mapped_column(String(MAX_AWB_LENGTH), nullable=True)
    courier_company_id: Mapped[str | None] = mapped_column(
        String(MAX_PROVIDER_ID_LENGTH), nullable=True
    )
    courier_name: Mapped[str | None] = mapped_column(String(MAX_COURIER_NAME_LENGTH), nullable=True)
    tracking_url: Mapped[str | None] = mapped_column(String(MAX_URL_LENGTH), nullable=True)
    label_url: Mapped[str | None] = mapped_column(String(MAX_URL_LENGTH), nullable=True)
    manifest_url: Mapped[str | None] = mapped_column(String(MAX_URL_LENGTH), nullable=True)

    pickup_location: Mapped[str] = mapped_column(String(MAX_PICKUP_LOCATION_LENGTH), nullable=False)
    # As the provider reported them; not computed here.
    pickup_scheduled_date: Mapped[str | None] = mapped_column(String(40), nullable=True)
    pickup_token_number: Mapped[str | None] = mapped_column(String(200), nullable=True)
    provider_etd: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # The package actually handed over, as entered or defaulted from settings.
    weight_kg: Mapped[Decimal] = mapped_column(WEIGHT, nullable=False)
    length_cm: Mapped[Decimal] = mapped_column(DIMENSION, nullable=False)
    breadth_cm: Mapped[Decimal] = mapped_column(DIMENSION, nullable=False)
    height_cm: Mapped[Decimal] = mapped_column(DIMENSION, nullable=False)
    # The weight the courier charged on, when it reports one.
    applied_weight_kg: Mapped[Decimal | None] = mapped_column(WEIGHT, nullable=True)

    payment_mode: Mapped[str] = mapped_column(String(10), nullable=False)
    # Value of the goods sent (the order total), for the provider and insurance.
    declared_value: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    # Cash the courier must collect at the door: the order's COD balance.
    # Distinct from the order total (an advance may be paid) and from what the
    # courier charges the store.
    cod_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=0)
    # What the provider quoted the store for the chosen courier (freight and
    # COD handling), as reported. Not what the shopper paid for shipping.
    freight_charge: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    cod_charge: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)

    provider_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider_status_label: Mapped[str | None] = mapped_column(
        String(MAX_STATUS_LABEL_LENGTH), nullable=True
    )
    # Time of the newest provider event applied, so an older one cannot move the state back.
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # The provider call in flight or last failed, for a safe retry.
    pending_operation: Mapped[str | None] = mapped_column(String(20), nullable=True)
    operation_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(MAX_ERROR_LENGTH), nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    picked_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", name="fk_shipments_created_by_users", ondelete="SET NULL"),
        nullable=True,
    )

    events: Mapped[list["ShipmentEvent"]] = relationship(
        "ShipmentEvent",
        primaryjoin=lambda: and_(
            Shipment.id == ShipmentEvent.shipment_id,
            Shipment.tenant_id == ShipmentEvent.tenant_id,
        ),
        foreign_keys=lambda: [ShipmentEvent.shipment_id, ShipmentEvent.tenant_id],
        order_by=lambda: (ShipmentEvent.occurred_at, ShipmentEvent.created_at),
        lazy="selectin",
        viewonly=True,
    )


class ShipmentEvent(IdMixin, TenantMixin, TimestampMixin, Base):
    """One tracking event exactly as the provider reported it, with the state it maps to."""

    __tablename__ = "shipment_events"

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "shipment_id"],
            ["shipments.tenant_id", "shipments.id"],
            name="fk_shipment_events_tenant_shipment_shipments",
            ondelete="CASCADE",
        ),
        # The same scan arriving by webhook and by polling is stored once.
        UniqueConstraint("shipment_id", "dedupe_key", name="uq_shipment_events_shipment_dedupe"),
        CheckConstraint(f"source IN ({_values(ShipmentEventSource)})", name="source_valid"),
        CheckConstraint(
            f"state IS NULL OR state IN ({_values(ShipmentState)})", name="state_valid"
        ),
        Index("ix_shipment_events_tenant_id_shipment_id", "tenant_id", "shipment_id"),
    )

    shipment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source: Mapped[str] = mapped_column(String(10), nullable=False)

    provider_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # The courier's own scan code (e.g. "DLVD") and the provider's label for it.
    courier_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status_label: Mapped[str | None] = mapped_column(String(MAX_STATUS_LABEL_LENGTH), nullable=True)
    # Our state for this event; NULL when the code does not move a shipment.
    state: Mapped[str | None] = mapped_column(String(30), nullable=True)
    activity: Mapped[str | None] = mapped_column(String(MAX_ACTIVITY_LENGTH), nullable=True)
    location: Mapped[str | None] = mapped_column(String(MAX_LOCATION_LENGTH), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    dedupe_key: Mapped[str] = mapped_column(String(MAX_DEDUPE_KEY_LENGTH), nullable=False)
    # The original event, kept so nothing the provider said is lost in mapping.
    raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class ShippingProviderSettings(IdMixin, TenantMixin, TimestampMixin, Base):
    """A tenant's courier-provider setup. Credentials are not stored here.

    Booking stays off until an admin enables it with a pickup location. Package
    defaults are optional: when unset, every shipment needs its package entered.
    """

    __tablename__ = "shipping_provider_settings"

    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_shipping_provider_settings_tenant_id"),
        CheckConstraint(f"provider IN ({_values(ShippingProvider)})", name="provider_valid"),
        CheckConstraint(
            "pickup_postcode IS NULL OR pickup_postcode ~ '^[1-9][0-9]{5}$'",
            name="pickup_postcode_is_indian",
        ),
        CheckConstraint(
            "NOT is_enabled OR (pickup_location IS NOT NULL AND pickup_postcode IS NOT NULL)",
            name="enabled_needs_pickup",
        ),
        CheckConstraint(
            "(default_weight_kg IS NULL AND default_length_cm IS NULL"
            " AND default_breadth_cm IS NULL AND default_height_cm IS NULL)"
            " OR (default_weight_kg IS NOT NULL AND default_length_cm IS NOT NULL"
            " AND default_breadth_cm IS NOT NULL AND default_height_cm IS NOT NULL"
            " AND default_weight_kg > 0 AND default_length_cm > 0"
            " AND default_breadth_cm > 0 AND default_height_cm > 0)",
            name="package_defaults_complete",
        ),
    )

    provider: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ShippingProvider.SHIPROCKET.value
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # The pickup location's name exactly as added in the provider's panel.
    pickup_location: Mapped[str | None] = mapped_column(
        String(MAX_PICKUP_LOCATION_LENGTH), nullable=True
    )
    pickup_postcode: Mapped[str | None] = mapped_column(String(6), nullable=True)

    # Shiprocket requires a buyer email; this one (e.g. the store's own) is
    # sent when the order has none, as many phone-only customers do.
    fallback_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    default_weight_kg: Mapped[Decimal | None] = mapped_column(WEIGHT, nullable=True)
    default_length_cm: Mapped[Decimal | None] = mapped_column(DIMENSION, nullable=True)
    default_breadth_cm: Mapped[Decimal | None] = mapped_column(DIMENSION, nullable=True)
    default_height_cm: Mapped[Decimal | None] = mapped_column(DIMENSION, nullable=True)

    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id", name="fk_shipping_provider_settings_updated_by_users", ondelete="SET NULL"
        ),
        nullable=True,
    )
