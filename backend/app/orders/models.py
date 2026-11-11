import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    Sequence,
    String,
    UniqueConstraint,
    and_,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.addresses.models import (
    MAX_CITY_LENGTH,
    MAX_LINE_LENGTH,
    MAX_NAME_LENGTH,
    MAX_POSTAL_CODE_LENGTH,
)
from app.catalogue.constants import (
    MAX_NAME_LENGTH as MAX_PRODUCT_NAME_LENGTH,
)
from app.catalogue.constants import (
    MAX_SKU_LENGTH,
    PRICE_PRECISION,
    PRICE_SCALE,
)
from app.models.base import Base, IdMixin, TenantMixin, TimestampMixin
from app.orders.constants import (
    CUSTOMER_CANCELLABLE_STATUSES,
    MAX_COURIER_NAME_LENGTH,
    MAX_IDEMPOTENCY_KEY_LENGTH,
    MAX_ORDER_NUMBER_LENGTH,
    MAX_TRACKING_DESCRIPTION_LENGTH,
    MAX_TRACKING_LOCATION_LENGTH,
    MAX_TRACKING_NUMBER_LENGTH,
    MAX_TRACKING_URL_LENGTH,
    ORDER_NUMBER_START,
    GstType,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    TrackingSource,
)
from app.payments.constants import PaymentPurpose
from app.payments.models import Payment

_ORDER_STATUS_VALUES = ", ".join(f"'{status.value}'" for status in OrderStatus)
_PAYMENT_STATUS_VALUES = ", ".join(f"'{status.value}'" for status in PaymentStatus)
_PAYMENT_METHOD_VALUES = ", ".join(f"'{method.value}'" for method in PaymentMethod)
_GST_TYPE_VALUES = ", ".join(f"'{kind.value}'" for kind in GstType)
_SOURCE_VALUES = ", ".join(f"'{source.value}'" for source in TrackingSource)

ORDER_NUMBER_SEQUENCE = Sequence(
    "order_number_seq", start=ORDER_NUMBER_START, metadata=Base.metadata
)


class Order(IdMixin, TenantMixin, TimestampMixin, Base):
    """One placed order, with prices and the delivery address copied in at checkout."""

    __tablename__ = "orders"

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_orders_tenant_id_id"),
        UniqueConstraint("order_number", name="uq_orders_order_number"),
        # NULLs stay distinct in Postgres, so orders placed without a key
        # never collide with each other.
        UniqueConstraint(
            "tenant_id",
            "customer_id",
            "idempotency_key",
            name="uq_orders_tenant_customer_idempotency",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["users.tenant_id", "users.id"],
            name="fk_orders_tenant_customer_users",
            ondelete="CASCADE",
        ),
        CheckConstraint(f"status IN ({_ORDER_STATUS_VALUES})", name="status_valid"),
        CheckConstraint(
            f"payment_status IN ({_PAYMENT_STATUS_VALUES})", name="payment_status_valid"
        ),
        CheckConstraint("subtotal >= 0", name="subtotal_not_negative"),
        CheckConstraint("shipping_amount >= 0", name="shipping_not_negative"),
        CheckConstraint("tax_amount >= 0", name="tax_not_negative"),
        CheckConstraint(
            "tax_included_amount >= 0 AND tax_included_amount <= tax_amount",
            name="tax_included_valid",
        ),
        CheckConstraint("discount_amount >= 0", name="discount_not_negative"),
        CheckConstraint("discount_amount <= subtotal", name="discount_not_more_than_subtotal"),
        CheckConstraint("cod_fee >= 0", name="cod_fee_not_negative"),
        CheckConstraint(
            "advance_amount >= 0 AND advance_amount <= total_amount",
            name="advance_within_total",
        ),
        CheckConstraint(
            "total_amount = subtotal - discount_amount + shipping_amount + cod_fee + tax_amount - "
            "tax_included_amount",
            name="total_matches_components",
        ),
        CheckConstraint(
            "cgst_amount >= 0 AND sgst_amount >= 0 AND igst_amount >= 0",
            name="gst_not_negative",
        ),
        CheckConstraint(
            "(gst_type IS NULL AND cgst_amount = 0 AND sgst_amount = 0 AND igst_amount = 0) "
            "OR (gst_type IS NOT NULL AND cgst_amount + sgst_amount + igst_amount = tax_amount)",
            name="gst_split_matches_tax",
        ),
        CheckConstraint(
            f"payment_method IN ({_PAYMENT_METHOD_VALUES})", name="payment_method_valid"
        ),
        CheckConstraint(
            f"gst_type IS NULL OR gst_type IN ({_GST_TYPE_VALUES})", name="gst_type_valid"
        ),
        Index("ix_orders_tenant_id_tracking_number", "tenant_id", "tracking_number"),
        Index("ix_orders_tenant_id_customer_id", "tenant_id", "customer_id"),
        Index("ix_orders_tenant_id_status", "tenant_id", "status"),
        Index("ix_orders_tenant_id_payment_status", "tenant_id", "payment_status"),
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    order_number: Mapped[str] = mapped_column(
        String(MAX_ORDER_NUMBER_LENGTH), nullable=False
    )

    # What the client sent as Idempotency-Key, so a retry returns this order
    # instead of placing a second one.
    idempotency_key: Mapped[str | None] = mapped_column(
        String(MAX_IDEMPOTENCY_KEY_LENGTH), nullable=True
    )

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=OrderStatus.PENDING.value
    )

    payment_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=PaymentStatus.PENDING.value
    )

    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(PRICE_PRECISION, PRICE_SCALE), nullable=False
    )

    # Snapshot of the coupon actually redeemed for this order, if any -- not
    # a live reference to reconstruct from. coupon_id is single-column (not
    # the usual composite tenant FK) since it only needs to survive the
    # coupon itself being soft-deleted later, the same reasoning used
    # elsewhere in this codebase for historical references; coupon_code is
    # copied in case the coupon's own code is ever changed.
    coupon_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("coupons.id", ondelete="SET NULL"),
        nullable=True,
    )

    coupon_code: Mapped[str | None] = mapped_column(String(50), nullable=True)

    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(PRICE_PRECISION, PRICE_SCALE), nullable=False, default=0, server_default="0"
    )

    shipping_amount: Mapped[Decimal] = mapped_column(
        Numeric(PRICE_PRECISION, PRICE_SCALE), nullable=False
    )

    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(PRICE_PRECISION, PRICE_SCALE), nullable=False
    )
    tax_included_amount: Mapped[Decimal] = mapped_column(
        Numeric(PRICE_PRECISION, PRICE_SCALE), nullable=False, default=0, server_default="0"
    )

    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(PRICE_PRECISION, PRICE_SCALE), nullable=False
    )

    delivery_name: Mapped[str] = mapped_column(String(MAX_NAME_LENGTH), nullable=False)

    delivery_phone: Mapped[str] = mapped_column(String(16), nullable=False)

    delivery_address_line_1: Mapped[str] = mapped_column(
        String(MAX_LINE_LENGTH), nullable=False
    )

    delivery_address_line_2: Mapped[str | None] = mapped_column(
        String(MAX_LINE_LENGTH), nullable=True
    )

    delivery_city: Mapped[str] = mapped_column(String(MAX_CITY_LENGTH), nullable=False)

    delivery_state: Mapped[str] = mapped_column(String(MAX_CITY_LENGTH), nullable=False)

    delivery_postal_code: Mapped[str] = mapped_column(
        String(MAX_POSTAL_CODE_LENGTH), nullable=False
    )

    delivery_country: Mapped[str] = mapped_column(
        String(MAX_CITY_LENGTH), nullable=False
    )

    # Where order updates go; the account email, or the one a guest typed in.
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Placed through guest checkout (the customer row was found or made by phone).
    is_guest: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    payment_method: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=PaymentMethod.CASH_ON_DELIVERY.value,
        server_default=PaymentMethod.CASH_ON_DELIVERY.value,
    )

    # COD handling fee charged on this order, part of the total.
    cod_fee: Mapped[Decimal] = mapped_column(
        Numeric(PRICE_PRECISION, PRICE_SCALE), nullable=False, default=0, server_default="0"
    )

    # Part of a COD order paid before dispatch; the rest is cash at the door.
    advance_amount: Mapped[Decimal] = mapped_column(
        Numeric(PRICE_PRECISION, PRICE_SCALE), nullable=False, default=0, server_default="0"
    )

    # GST split of tax_amount. NULL gst_type marks legacy tax with unknown classification.
    cgst_amount: Mapped[Decimal] = mapped_column(
        Numeric(PRICE_PRECISION, PRICE_SCALE), nullable=False, default=0, server_default="0"
    )
    sgst_amount: Mapped[Decimal] = mapped_column(
        Numeric(PRICE_PRECISION, PRICE_SCALE), nullable=False, default=0, server_default="0"
    )
    igst_amount: Mapped[Decimal] = mapped_column(
        Numeric(PRICE_PRECISION, PRICE_SCALE), nullable=False, default=0, server_default="0"
    )
    gst_type: Mapped[str | None] = mapped_column(String(12), nullable=True)
    place_of_supply: Mapped[str | None] = mapped_column(String(100), nullable=True)
    seller_gstin: Mapped[str | None] = mapped_column(String(15), nullable=True)
    seller_legal_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    seller_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    seller_state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    seller_state_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    invoice_prefix: Mapped[str | None] = mapped_column(String(20), nullable=True)
    shipping_sac_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    charges_gst_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    prices_include_gst: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    gst_registration_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # True when any line was taxed at a rate the store has not verified yet.
    tax_review_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    estimated_delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Why the parcel came back: the reason's label as chosen when the order was
    # marked RETURNED (a snapshot, so renaming a reason never rewrites history).
    return_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    return_note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    courier_name: Mapped[str | None] = mapped_column(
        String(MAX_COURIER_NAME_LENGTH), nullable=True
    )
    tracking_number: Mapped[str | None] = mapped_column(
        String(MAX_TRACKING_NUMBER_LENGTH), nullable=True
    )
    tracking_url: Mapped[str | None] = mapped_column(
        String(MAX_TRACKING_URL_LENGTH), nullable=True
    )

    payments: Mapped[list["Payment"]] = relationship(
        "Payment",
        primaryjoin=lambda: and_(
            Order.id == Payment.order_id,
            Order.tenant_id == Payment.tenant_id,
        ),
        foreign_keys=lambda: [Payment.order_id, Payment.tenant_id],
        order_by=lambda: Payment.created_at,
        lazy="selectin",
        viewonly=True,
    )

    tracking_events: Mapped[list["OrderTrackingEvent"]] = relationship(
        "OrderTrackingEvent",
        primaryjoin=lambda: and_(
            Order.id == OrderTrackingEvent.order_id,
            Order.tenant_id == OrderTrackingEvent.tenant_id,
        ),
        foreign_keys=lambda: [OrderTrackingEvent.order_id, OrderTrackingEvent.tenant_id],
        order_by=lambda: (OrderTrackingEvent.occurred_at, OrderTrackingEvent.created_at),
        lazy="selectin",
        viewonly=True,
    )

    @property
    def payment(self) -> Payment | None:
        """The cash-on-delivery payment: the whole amount, or the balance after an advance."""
        for payment in self.payments:
            if payment.purpose != PaymentPurpose.ADVANCE.value:
                return payment
        return None

    @property
    def advance_payment(self) -> Payment | None:
        for payment in self.payments:
            if payment.purpose == PaymentPurpose.ADVANCE.value:
                return payment
        return None

    items: Mapped[list["OrderItem"]] = relationship(
        "OrderItem",
        primaryjoin=lambda: and_(
            Order.id == OrderItem.order_id,
            Order.tenant_id == OrderItem.tenant_id,
        ),
        foreign_keys=lambda: [OrderItem.order_id, OrderItem.tenant_id],
        order_by=lambda: OrderItem.created_at,
        lazy="selectin",
        viewonly=True,
    )

    @property
    def customer_can_cancel(self) -> bool:
        """Whether the customer may cancel online: an unpaid cash order before PROCESSING."""
        return (
            OrderStatus(self.status) in CUSTOMER_CANCELLABLE_STATUSES
            and self.payment_method == PaymentMethod.CASH_ON_DELIVERY.value
            and self.payment_status != PaymentStatus.PAID.value
            and not any(payment.status == PaymentStatus.PAID.value for payment in self.payments)
        )


class OrderItem(IdMixin, TenantMixin, TimestampMixin, Base):
    """One order line, with the product details frozen at purchase time."""

    __tablename__ = "order_items"

    __table_args__ = (
        UniqueConstraint("order_id", "variant_id", name="uq_order_items_order_variant"),
        ForeignKeyConstraint(
            ["tenant_id", "order_id"],
            ["orders.tenant_id", "orders.id"],
            name="fk_order_items_tenant_order_orders",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "variant_id"],
            ["product_variants.tenant_id", "product_variants.id"],
            name="fk_order_items_tenant_variant_product_variants",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["products.tenant_id", "products.id"],
            name="fk_order_items_tenant_product_products",
            ondelete="CASCADE",
        ),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price >= 0", name="unit_price_not_negative"),
        CheckConstraint(
            "subtotal = unit_price * quantity", name="subtotal_is_price_times_quantity"
        ),
        Index("ix_order_items_tenant_id_order_id", "tenant_id", "order_id"),
        Index("ix_order_items_tax_configuration_id", "tax_configuration_id"),
        Index("ix_order_items_tax_rule_id", "tax_rule_id"),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    variant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    product_name: Mapped[str] = mapped_column(
        String(MAX_PRODUCT_NAME_LENGTH), nullable=False
    )

    variant_name: Mapped[str] = mapped_column(
        String(MAX_PRODUCT_NAME_LENGTH), nullable=False
    )

    sku: Mapped[str] = mapped_column(String(MAX_SKU_LENGTH), nullable=False)

    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(PRICE_PRECISION, PRICE_SCALE), nullable=False
    )

    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(PRICE_PRECISION, PRICE_SCALE), nullable=False
    )

    # GST frozen at purchase. NULL on orders placed before GST lines existed.
    hsn_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    tax_configuration_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "tax_rate_configurations.id",
            name="fk_order_items_tax_configuration",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    gst_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    discount_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(PRICE_PRECISION, PRICE_SCALE), nullable=True
    )
    taxable_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(PRICE_PRECISION, PRICE_SCALE), nullable=True
    )
    tax_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(PRICE_PRECISION, PRICE_SCALE), nullable=True
    )
    # The rest of the tax snapshot: the split, and which rule (version) set the
    # rate and how sure the store was of it. NULL on orders placed before these.
    cgst_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(PRICE_PRECISION, PRICE_SCALE), nullable=True
    )
    sgst_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(PRICE_PRECISION, PRICE_SCALE), nullable=True
    )
    igst_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(PRICE_PRECISION, PRICE_SCALE), nullable=True
    )
    tax_rule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "gst_default_rules.id", name="fk_order_items_tax_rule", ondelete="RESTRICT"
        ),
        nullable=True,
    )
    tax_rule_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    tax_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tax_verification: Mapped[str | None] = mapped_column(String(30), nullable=True)


class OrderTrackingEvent(IdMixin, TenantMixin, TimestampMixin, Base):
    """One step in an order's journey: a status change or a courier scan."""

    __tablename__ = "order_tracking_events"

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "order_id"],
            ["orders.tenant_id", "orders.id"],
            name="fk_order_tracking_events_tenant_order_orders",
            ondelete="CASCADE",
        ),
        CheckConstraint(f"source IN ({_SOURCE_VALUES})", name="source_valid"),
        CheckConstraint(
            f"status IS NULL OR status IN ({_ORDER_STATUS_VALUES})", name="status_valid"
        ),
        Index(
            "ix_order_tracking_events_tenant_id_order_id_occurred_at",
            "tenant_id",
            "order_id",
            "occurred_at",
        ),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    # The order status this event moved to; NULL for a courier scan or note.
    status: Mapped[str | None] = mapped_column(String(20), nullable=True)

    description: Mapped[str] = mapped_column(
        String(MAX_TRACKING_DESCRIPTION_LENGTH), nullable=False
    )

    location: Mapped[str | None] = mapped_column(
        String(MAX_TRACKING_LOCATION_LENGTH), nullable=True
    )

    source: Mapped[str] = mapped_column(
        String(10), nullable=False, default=TrackingSource.SYSTEM.value
    )

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
