import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TenantMixin, TimestampMixin

MAX_NAME_LENGTH = 150
MAX_LINE_LENGTH = 255
MAX_CITY_LENGTH = 100
MAX_POSTAL_CODE_LENGTH = 20


class Address(IdMixin, TenantMixin, TimestampMixin, Base):
    """A customer's delivery address, copied onto orders at checkout."""

    __tablename__ = "addresses"

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_addresses_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["users.tenant_id", "users.id"],
            name="fk_addresses_tenant_customer_users",
            ondelete="CASCADE",
        ),
        CheckConstraint("length(trim(full_name)) > 0", name="full_name_not_blank"),
        CheckConstraint("length(trim(address_line_1)) > 0", name="address_line_1_not_blank"),
        CheckConstraint("length(trim(city)) > 0", name="city_not_blank"),
        CheckConstraint("length(trim(postal_code)) > 0", name="postal_code_not_blank"),
        CheckConstraint(r"phone ~ '^\+[1-9][0-9]{7,14}$'", name="phone_is_e164"),
        Index(
            "uq_addresses_one_default_per_customer",
            "tenant_id",
            "customer_id",
            unique=True,
            postgresql_where=text("is_default"),
        ),
        Index("ix_addresses_tenant_id_customer_id", "tenant_id", "customer_id"),
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    full_name: Mapped[str] = mapped_column(String(MAX_NAME_LENGTH), nullable=False)

    phone: Mapped[str] = mapped_column(String(16), nullable=False)

    address_line_1: Mapped[str] = mapped_column(String(MAX_LINE_LENGTH), nullable=False)

    address_line_2: Mapped[str | None] = mapped_column(
        String(MAX_LINE_LENGTH), nullable=True
    )

    city: Mapped[str] = mapped_column(String(MAX_CITY_LENGTH), nullable=False)

    state: Mapped[str] = mapped_column(String(MAX_CITY_LENGTH), nullable=False)

    postal_code: Mapped[str] = mapped_column(
        String(MAX_POSTAL_CODE_LENGTH), nullable=False
    )

    country: Mapped[str] = mapped_column(String(MAX_CITY_LENGTH), nullable=False)

    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
