"""Per-tenant shipping, delivery-area, tax and GST-invoice settings."""

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
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.catalogue.constants import PRICE_PRECISION, PRICE_SCALE
from app.models.base import Base, IdMixin, TenantMixin, TimestampMixin
from app.pricing.constants import (
    DEFAULT_INVOICE_PREFIX,
    DEFAULT_MAX_DELIVERY_DAYS,
    DEFAULT_MIN_DELIVERY_DAYS,
    DEFAULT_TAX_CLASSIFICATION,
    MAX_TAX_PERCENTAGE,
    RULE_UNVERIFIED,
)

TAX_PRECISION = 5
TAX_SCALE = 2


class ShippingSettings(IdMixin, TenantMixin, TimestampMixin, Base):
    """One tenant's delivery charge, free above `free_shipping_minimum`."""

    __tablename__ = "shipping_settings"

    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_shipping_settings_tenant_id"),
        CheckConstraint("shipping_amount >= 0", name="shipping_amount_not_negative"),
        CheckConstraint(
            "free_shipping_minimum IS NULL OR free_shipping_minimum >= 0",
            name="free_shipping_minimum_not_negative",
        ),
        CheckConstraint(
            "min_delivery_days >= 0 AND max_delivery_days >= min_delivery_days",
            name="delivery_days_ordered",
        ),
    )

    shipping_amount: Mapped[Decimal] = mapped_column(
        Numeric(PRICE_PRECISION, PRICE_SCALE), nullable=False
    )

    free_shipping_minimum: Mapped[Decimal | None] = mapped_column(
        Numeric(PRICE_PRECISION, PRICE_SCALE), nullable=True
    )

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # The default delivery promise, in days from the order; a pincode may override it.
    min_delivery_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=DEFAULT_MIN_DELIVERY_DAYS,
        server_default=str(DEFAULT_MIN_DELIVERY_DAYS),
    )
    max_delivery_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=DEFAULT_MAX_DELIVERY_DAYS,
        server_default=str(DEFAULT_MAX_DELIVERY_DAYS),
    )

    # True: only pincodes listed as serviceable are delivered to.
    # False (default): everywhere is served unless a pincode is blocked.
    restrict_to_listed_pincodes: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )


class PincodeRule(IdMixin, TenantMixin, TimestampMixin, Base):
    """Delivery rules for one pincode: served or not, how fast, at what cost, COD or not."""

    __tablename__ = "pincode_rules"

    __table_args__ = (
        UniqueConstraint("tenant_id", "pincode", name="uq_pincode_rules_tenant_pincode"),
        CheckConstraint("pincode ~ '^[1-9][0-9]{5}$'", name="pincode_is_indian"),
        CheckConstraint(
            "shipping_amount IS NULL OR shipping_amount >= 0",
            name="shipping_amount_not_negative",
        ),
        CheckConstraint(
            "(min_delivery_days IS NULL) = (max_delivery_days IS NULL)"
            " AND (min_delivery_days IS NULL"
            " OR (min_delivery_days >= 0 AND max_delivery_days >= min_delivery_days))",
            name="delivery_days_ordered",
        ),
    )

    pincode: Mapped[str] = mapped_column(String(6), nullable=False)

    is_serviceable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    cod_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    min_delivery_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_delivery_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Replaces the flat delivery charge here (free-shipping threshold still applies).
    shipping_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(PRICE_PRECISION, PRICE_SCALE), nullable=True
    )

    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)


class GstSettings(IdMixin, TenantMixin, TimestampMixin, Base):
    """The seller's GST identity, printed on invoices and used to split CGST/SGST/IGST."""

    __tablename__ = "gst_settings"

    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_gst_settings_tenant_id"),
        CheckConstraint(
            "registration_status IN ('REGISTERED', 'NOT_REGISTERED', 'APPLICATION_PENDING', "
            "'UNKNOWN')",
            name="gst_registration_status_valid",
        ),
        CheckConstraint(
            "accounting_software IN ('TALLY', 'ZOHO_BOOKS', 'OTHER', 'NONE', 'NOT_DECIDED')",
            name="gst_accounting_software_valid",
        ),
        CheckConstraint(
            "configuration_status IN ('DRAFT', 'PENDING_CA_CONFIRMATION', 'ACTIVE')",
            name="gst_configuration_status_valid",
        ),
        CheckConstraint(
            "configuration_status != 'ACTIVE' OR (confirmed_by_id IS NOT NULL AND confirmed_at IS "
            "NOT NULL)",
            name="gst_active_requires_confirmation",
        ),
    )

    gstin: Mapped[str | None] = mapped_column(String(15), nullable=True)
    legal_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # The seller's state decides intra- (CGST+SGST) vs inter-state (IGST) supply.
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state_code: Mapped[str | None] = mapped_column(String(2), nullable=True)

    invoice_prefix: Mapped[str] = mapped_column(
        String(20), nullable=False, default=DEFAULT_INVOICE_PREFIX
    )

    shipping_sac_code: Mapped[str | None] = mapped_column(String(8), nullable=True)

    # Business choices are persisted independently from runtime secrets.
    registration_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="UNKNOWN", server_default="UNKNOWN"
    )
    accounting_software: Mapped[str] = mapped_column(
        String(30), nullable=False, default="NOT_DECIDED", server_default="NOT_DECIDED"
    )
    configuration_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="DRAFT", server_default="DRAFT"
    )
    prices_include_gst: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", name="fk_gst_settings_updated_by_users", ondelete="SET NULL"),
        nullable=True,
    )
    confirmed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", name="fk_gst_settings_confirmed_by_users", ondelete="SET NULL"),
        nullable=True,
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # False: the store charges no GST at all (e.g. not registered).
    gst_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    # Classification assumed for a product with no HSN code; NULL assumes nothing,
    # so such products fall back. Each line priced this way is flagged for review.
    default_classification: Mapped[str | None] = mapped_column(
        String(40), nullable=True, default=DEFAULT_TAX_CLASSIFICATION,
        server_default=DEFAULT_TAX_CLASSIFICATION,
    )
    # Replaces the system fallback rate for this tenant; NULL keeps the system one.
    fallback_gst_rate: Mapped[Decimal | None] = mapped_column(
        Numeric(TAX_PRECISION, TAX_SCALE), nullable=True
    )
    # The tenant's sign-off on the system default rules and its assumed classification.
    defaults_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    defaults_reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id", name="fk_gst_settings_defaults_reviewed_by_users", ondelete="SET NULL"
        ),
        nullable=True,
    )


class GstDefaultRule(IdMixin, TimestampMixin, Base):
    """A platform-wide GST rule, shared read-only by every tenant.

    A rule covers one classification (matched by HSN prefix, or assumed by the
    store), a per-piece value band (above `min_unit_value`, up to and including
    `max_unit_value`) and an effective date range. Rows are seeded by migration
    and never edited by a tenant: a tenant changes its tax through its own
    settings and overrides, so nothing here can leak between stores. A rule that
    changes gets a new row with a new `effective_from`, so old orders keep
    pointing at the version they were taxed under.
    """

    __tablename__ = "gst_default_rules"

    __table_args__ = (
        UniqueConstraint("code", "effective_from", name="uq_gst_default_rules_code_effective"),
        CheckConstraint("gst_rate >= 0 AND gst_rate <= 100", name="gst_rate_in_range"),
        CheckConstraint(
            "min_unit_value IS NULL OR max_unit_value IS NULL OR max_unit_value > min_unit_value",
            name="value_band_ordered",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from", name="dates_ordered"
        ),
        CheckConstraint(
            "verification_status IN ('UNVERIFIED', 'VERIFIED')", name="verification_status_valid"
        ),
        Index("ix_gst_default_rules_classification", "classification", "effective_from"),
    )

    code: Mapped[str] = mapped_column(String(60), nullable=False)
    classification: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    # HSN prefixes the rule covers (e.g. chapter "61"); empty for the fallback.
    hsn_prefixes: Mapped[list[str]] = mapped_column(
        ARRAY(String(8)), nullable=False, default=list, server_default="{}"
    )
    min_unit_value: Mapped[Decimal | None] = mapped_column(
        Numeric(PRICE_PRECISION, PRICE_SCALE), nullable=True
    )
    max_unit_value: Mapped[Decimal | None] = mapped_column(
        Numeric(PRICE_PRECISION, PRICE_SCALE), nullable=True
    )
    gst_rate: Mapped[Decimal] = mapped_column(Numeric(TAX_PRECISION, TAX_SCALE), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_fallback: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    verification_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=RULE_UNVERIFIED, server_default=RULE_UNVERIFIED
    )
    source: Mapped[str | None] = mapped_column(String(300), nullable=True)


class TaxSettings(IdMixin, TenantMixin, TimestampMixin, Base):
    """One tenant's tax rate, as a percentage: 18.00 means 18%."""

    __tablename__ = "tax_settings"

    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_tax_settings_tenant_id"),
        CheckConstraint(
            f"tax_percentage >= 0 AND tax_percentage <= {MAX_TAX_PERCENTAGE}",
            name="tax_percentage_in_range",
        ),
        CheckConstraint(
            "NOT is_active OR confirmed_by_ca", name="tax_active_requires_confirmation"
        ),
    )

    tax_percentage: Mapped[Decimal] = mapped_column(
        Numeric(TAX_PRECISION, TAX_SCALE), nullable=False
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    confirmed_by_ca: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )


class TaxRateConfiguration(IdMixin, TenantMixin, TimestampMixin, Base):
    """Versioned, CA-confirmed rate mapping for a product or its category."""

    __tablename__ = "tax_rate_configurations"

    __table_args__ = (
        CheckConstraint(
            "(product_id IS NOT NULL AND category_id IS NULL) OR "
            "(product_id IS NULL AND category_id IS NOT NULL)",
            name="tax_rate_one_target",
        ),
        CheckConstraint("gst_rate >= 0 AND gst_rate <= 100", name="tax_rate_in_range"),
        CheckConstraint("status IN ('PENDING', 'ACTIVE', 'RETIRED')", name="tax_rate_status_valid"),
        CheckConstraint(
            "status != 'ACTIVE' OR (ca_confirmed AND approved_by_id IS NOT NULL AND approved_at "
            "IS NOT NULL)",
            name="tax_rate_active_needs_confirmation",
        ),
        CheckConstraint("hsn_code ~ '^[0-9]{4}([0-9]{2}){0,2}$'", name="tax_rate_hsn_valid"),
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["products.tenant_id", "products.id"],
            name="fk_tax_rate_product_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "category_id"],
            ["categories.tenant_id", "categories.id"],
            name="fk_tax_rate_category_tenant",
            ondelete="RESTRICT",
        ),
        Index("ix_tax_rate_tenant_product_effective", "tenant_id", "product_id", "effective_from"),
        Index(
            "ix_tax_rate_tenant_category_effective", "tenant_id", "category_id", "effective_from"
        ),
    )

    product_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    hsn_code: Mapped[str] = mapped_column(String(8), nullable=False)
    gst_rate: Mapped[Decimal] = mapped_column(Numeric(TAX_PRECISION, TAX_SCALE), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, default="PENDING", server_default="PENDING"
    )
    ca_confirmed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id", name="fk_tax_rate_configurations_created_by_id_users", ondelete="SET NULL"
        ),
        nullable=True,
    )
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id", name="fk_tax_rate_configurations_approved_by_id_users", ondelete="SET NULL"
        ),
        nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
