import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    and_,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.catalogue.constants import (
    GST_RATE_PRECISION,
    GST_RATE_SCALE,
    MAX_ALT_TEXT_LENGTH,
    MAX_BRAND_LENGTH,
    MAX_COUNTRY_LENGTH,
    MAX_DESCRIPTION_LENGTH,
    MAX_GST_RATE,
    MAX_HSN_CODE_LENGTH,
    MAX_IMAGE_URL_LENGTH,
    MAX_NAME_LENGTH,
    MAX_OPTION_NAME_LENGTH,
    MAX_OPTION_VALUE_LENGTH,
    MAX_PRODUCT_ATTRIBUTE_LENGTH,
    MAX_PRODUCT_INFO_LENGTH,
    MAX_SEO_DESCRIPTION_LENGTH,
    MAX_SEO_TITLE_LENGTH,
    MAX_SHORT_DESCRIPTION_LENGTH,
    MAX_SKU_LENGTH,
    MAX_SLUG_LENGTH,
    PRICE_PRECISION,
    PRICE_SCALE,
    CatalogueStatus,
    InventoryReason,
    ProductGender,
)
from app.models.base import Base, IdMixin, TenantMixin, TimestampMixin

_STATUS_VALUES = ", ".join(f"'{status.value}'" for status in CatalogueStatus)
_REASON_VALUES = ", ".join(f"'{reason.value}'" for reason in InventoryReason)
_GENDER_VALUES = ", ".join(f"'{gender.value}'" for gender in ProductGender)

_GST_RATE_IN_RANGE = f"gst_rate IS NULL OR (gst_rate >= 0 AND gst_rate <= {MAX_GST_RATE})"


class Category(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "categories"

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_categories_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "parent_id"],
            ["categories.tenant_id", "categories.id"],
            name="fk_categories_tenant_parent_categories",
            ondelete="NO ACTION",
        ),
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint(f"status IN ({_STATUS_VALUES})", name="status_valid"),
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="parent_not_self"),
        CheckConstraint(_GST_RATE_IN_RANGE, name="gst_rate_in_range"),
        Index("ix_categories_tenant_id_status", "tenant_id", "status"),
        Index("ix_categories_tenant_id_parent_id", "tenant_id", "parent_id"),
    )

    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    name: Mapped[str] = mapped_column(String(MAX_NAME_LENGTH), nullable=False)

    description: Mapped[str | None] = mapped_column(
        String(MAX_DESCRIPTION_LENGTH), nullable=True
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=CatalogueStatus.ACTIVE.value,
    )

    # GST defaults for every product in the category; a product may override them.
    hsn_code: Mapped[str | None] = mapped_column(String(MAX_HSN_CODE_LENGTH), nullable=True)

    gst_rate: Mapped[Decimal | None] = mapped_column(
        Numeric(GST_RATE_PRECISION, GST_RATE_SCALE), nullable=True
    )


class Product(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "products"

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_products_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "category_id"],
            ["categories.tenant_id", "categories.id"],
            name="fk_products_tenant_category_categories",
            ondelete="NO ACTION",
        ),
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint(f"status IN ({_STATUS_VALUES})", name="status_valid"),
        CheckConstraint(f"gender IS NULL OR gender IN ({_GENDER_VALUES})", name="gender_valid"),
        CheckConstraint(_GST_RATE_IN_RANGE, name="gst_rate_in_range"),
        Index("ix_products_tenant_id_category_id", "tenant_id", "category_id"),
        Index("ix_products_tenant_id_status", "tenant_id", "status"),
        Index("ix_products_tenant_id_is_featured", "tenant_id", "is_featured"),
        Index("ix_products_tenant_id_brand", "tenant_id", "brand"),
        Index("ix_products_tenant_id_gender", "tenant_id", "gender"),
        Index("ix_products_tenant_id_fabric", "tenant_id", "fabric"),
        Index("ix_products_tenant_id_occasion", "tenant_id", "occasion"),
        Index("ix_products_tenant_id_sleeve", "tenant_id", "sleeve"),
        Index("ix_products_tenant_id_neckline", "tenant_id", "neckline"),
        UniqueConstraint("tenant_id", "slug", name="uq_products_tenant_id_slug"),
    )

    category_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    name: Mapped[str] = mapped_column(String(MAX_NAME_LENGTH), nullable=False)

    # SEO-friendly URL part, unique per store. Made from the name on creation and
    # kept stable afterwards (renaming a product does not break shared links).
    slug: Mapped[str] = mapped_column(String(MAX_SLUG_LENGTH), nullable=False)

    short_description: Mapped[str | None] = mapped_column(
        String(MAX_SHORT_DESCRIPTION_LENGTH), nullable=True
    )

    description: Mapped[str | None] = mapped_column(
        String(MAX_DESCRIPTION_LENGTH), nullable=True
    )

    brand: Mapped[str | None] = mapped_column(String(MAX_BRAND_LENGTH), nullable=True)

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=CatalogueStatus.DRAFT.value,
    )

    # Product-level attribute (not a variant or category one). Nullable --
    # gender isn't meaningful for every product line, and defaulting every
    # existing/ungendered product to a specific value would misclassify it.
    gender: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Filterable product-level attributes, nullable for the same reason as gender.
    fabric: Mapped[str | None] = mapped_column(
        String(MAX_PRODUCT_ATTRIBUTE_LENGTH), nullable=True
    )
    occasion: Mapped[str | None] = mapped_column(
        String(MAX_PRODUCT_ATTRIBUTE_LENGTH), nullable=True
    )
    sleeve: Mapped[str | None] = mapped_column(
        String(MAX_PRODUCT_ATTRIBUTE_LENGTH), nullable=True
    )
    neckline: Mapped[str | None] = mapped_column(
        String(MAX_PRODUCT_ATTRIBUTE_LENGTH), nullable=True
    )

    # Product-page information blocks.
    fabric_details: Mapped[str | None] = mapped_column(
        String(MAX_PRODUCT_INFO_LENGTH), nullable=True
    )
    washing_instructions: Mapped[str | None] = mapped_column(
        String(MAX_PRODUCT_INFO_LENGTH), nullable=True
    )
    country_of_origin: Mapped[str | None] = mapped_column(
        String(MAX_COUNTRY_LENGTH), nullable=True
    )

    # {"unit": "in", "measurements": [...], "rows": [{"size": "S", "values": {...}}]}
    size_chart: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Overrides the category's GST defaults when set.
    hsn_code: Mapped[str | None] = mapped_column(String(MAX_HSN_CODE_LENGTH), nullable=True)

    gst_rate: Mapped[Decimal | None] = mapped_column(
        Numeric(GST_RATE_PRECISION, GST_RATE_SCALE), nullable=True
    )

    is_featured: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    seo_title: Mapped[str | None] = mapped_column(
        String(MAX_SEO_TITLE_LENGTH), nullable=True
    )

    seo_description: Mapped[str | None] = mapped_column(
        String(MAX_SEO_DESCRIPTION_LENGTH), nullable=True
    )

    images: Mapped[list["ProductImage"]] = relationship(
        "ProductImage",
        primaryjoin=lambda: and_(
            Product.id == ProductImage.product_id,
            Product.tenant_id == ProductImage.tenant_id,
        ),
        foreign_keys=lambda: [ProductImage.product_id, ProductImage.tenant_id],
        order_by=lambda: (ProductImage.sort_order, ProductImage.created_at),
        lazy="selectin",
        viewonly=True,
    )

    options: Mapped[list["ProductOption"]] = relationship(
        "ProductOption",
        primaryjoin=lambda: and_(
            Product.id == ProductOption.product_id,
            Product.tenant_id == ProductOption.tenant_id,
        ),
        foreign_keys=lambda: [ProductOption.product_id, ProductOption.tenant_id],
        order_by=lambda: (ProductOption.position, ProductOption.name),
        lazy="selectin",
        viewonly=True,
    )

    variants: Mapped[list["ProductVariant"]] = relationship(
        "ProductVariant",
        primaryjoin=lambda: and_(
            Product.id == ProductVariant.product_id,
            Product.tenant_id == ProductVariant.tenant_id,
        ),
        foreign_keys=lambda: [ProductVariant.product_id, ProductVariant.tenant_id],
        order_by=lambda: ProductVariant.sku,
        lazy="selectin",
        viewonly=True,
    )


class ProductRelation(IdMixin, TenantMixin, TimestampMixin, Base):
    """A hand-picked "you may also like" link from one product to another."""

    __tablename__ = "product_relations"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "product_id",
            "related_product_id",
            name="uq_product_relations_tenant_product_related",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["products.tenant_id", "products.id"],
            name="fk_product_relations_tenant_product_products",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "related_product_id"],
            ["products.tenant_id", "products.id"],
            name="fk_product_relations_tenant_related_products",
            ondelete="CASCADE",
        ),
        CheckConstraint("product_id <> related_product_id", name="not_self_related"),
        CheckConstraint("position >= 0", name="position_not_negative"),
        Index("ix_product_relations_tenant_id_product_id", "tenant_id", "product_id"),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    related_product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )

    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ProductOption(IdMixin, TenantMixin, TimestampMixin, Base):
    """A dimension a product varies along, such as Color or Size."""

    __tablename__ = "product_options"

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_product_options_tenant_id_id"),
        UniqueConstraint(
            "tenant_id", "product_id", "name", name="uq_product_options_tenant_product_name"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["products.tenant_id", "products.id"],
            name="fk_product_options_tenant_product_products",
            ondelete="CASCADE",
        ),
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint("position >= 0", name="position_not_negative"),
        Index("ix_product_options_tenant_id_product_id", "tenant_id", "product_id"),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    name: Mapped[str] = mapped_column(String(MAX_OPTION_NAME_LENGTH), nullable=False)

    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ProductVariant(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "product_variants"

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_product_variants_tenant_id_id"),
        UniqueConstraint("tenant_id", "sku", name="uq_product_variants_tenant_sku"),
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["products.tenant_id", "products.id"],
            name="fk_product_variants_tenant_product_products",
            ondelete="CASCADE",
        ),
        CheckConstraint("sku = upper(sku)", name="sku_is_uppercase"),
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint(f"status IN ({_STATUS_VALUES})", name="status_valid"),
        CheckConstraint("price >= 0", name="price_not_negative"),
        CheckConstraint(
            "sale_price IS NULL OR sale_price >= 0", name="sale_price_not_negative"
        ),
        CheckConstraint(
            "sale_starts_at IS NULL OR sale_ends_at IS NULL OR sale_starts_at < sale_ends_at",
            name="sale_window_ordered",
        ),
        Index("ix_product_variants_tenant_id_product_id", "tenant_id", "product_id"),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    sku: Mapped[str] = mapped_column(String(MAX_SKU_LENGTH), nullable=False)

    name: Mapped[str] = mapped_column(String(MAX_NAME_LENGTH), nullable=False)

    price: Mapped[Decimal] = mapped_column(
        Numeric(PRICE_PRECISION, PRICE_SCALE), nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=CatalogueStatus.DRAFT.value
    )

    # A scheduled sale: `sale_price` is charged inside the window and `price`
    # outside it, so the regular price comes back on its own when it ends.
    sale_price: Mapped[Decimal | None] = mapped_column(
        Numeric(PRICE_PRECISION, PRICE_SCALE), nullable=True
    )
    sale_starts_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sale_ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    option_values: Mapped[list["ProductVariantOption"]] = relationship(
        "ProductVariantOption",
        primaryjoin=lambda: and_(
            ProductVariant.id == ProductVariantOption.variant_id,
            ProductVariant.tenant_id == ProductVariantOption.tenant_id,
        ),
        foreign_keys=lambda: [
            ProductVariantOption.variant_id,
            ProductVariantOption.tenant_id,
        ],
        lazy="selectin",
        viewonly=True,
    )

    inventory: Mapped["InventoryItem | None"] = relationship(
        "InventoryItem",
        primaryjoin=lambda: and_(
            ProductVariant.id == InventoryItem.variant_id,
            ProductVariant.tenant_id == InventoryItem.tenant_id,
        ),
        foreign_keys=lambda: [InventoryItem.variant_id, InventoryItem.tenant_id],
        lazy="selectin",
        uselist=False,
        viewonly=True,
    )


class ProductVariantOption(IdMixin, TenantMixin, TimestampMixin, Base):
    """One option value for one variant -- "Color = Black"."""

    __tablename__ = "product_variant_options"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "variant_id",
            "option_id",
            name="uq_product_variant_options_tenant_variant_option",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "variant_id"],
            ["product_variants.tenant_id", "product_variants.id"],
            name="fk_product_variant_options_tenant_variant_product_variants",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "option_id"],
            ["product_options.tenant_id", "product_options.id"],
            name="fk_product_variant_options_tenant_option_product_options",
            ondelete="CASCADE",
        ),
        CheckConstraint("length(trim(value)) > 0", name="value_not_blank"),
        Index("ix_product_variant_options_tenant_id_option_id", "tenant_id", "option_id"),
    )

    variant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    option_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    value: Mapped[str] = mapped_column(String(MAX_OPTION_VALUE_LENGTH), nullable=False)

    option: Mapped["ProductOption"] = relationship(
        "ProductOption",
        primaryjoin=lambda: and_(
            ProductVariantOption.option_id == ProductOption.id,
            ProductVariantOption.tenant_id == ProductOption.tenant_id,
        ),
        foreign_keys=lambda: [
            ProductVariantOption.option_id,
            ProductVariantOption.tenant_id,
        ],
        lazy="selectin",
        viewonly=True,
    )


class ProductImage(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "product_images"

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_product_images_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["products.tenant_id", "products.id"],
            name="fk_product_images_tenant_product_products",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "media_asset_id"],
            ["media_assets.tenant_id", "media_assets.id"],
            name="fk_product_images_tenant_media_asset_media_assets",
            ondelete="RESTRICT",
        ),
        CheckConstraint("source IN ('UPLOAD', 'AI_GENERATED')", name="image_source_valid"),
        CheckConstraint(
            "source = 'UPLOAD' OR media_asset_id IS NOT NULL", name="ai_image_has_asset"
        ),
        Index("ix_product_images_tenant_id_product_id", "tenant_id", "product_id"),
        CheckConstraint("length(trim(url)) > 0", name="image_url_not_blank"),
        CheckConstraint("sort_order >= 0", name="image_sort_order_valid"),
        Index(
            "uq_product_images_one_primary_per_product",
            "tenant_id",
            "product_id",
            unique=True,
            postgresql_where=text("is_primary"),
        ),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    url: Mapped[str] = mapped_column(String(MAX_IMAGE_URL_LENGTH), nullable=False)

    alt_text: Mapped[str | None] = mapped_column(
        String(MAX_ALT_TEXT_LENGTH), nullable=True
    )

    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # UPLOAD: the brand's own photo. AI_GENERATED: an approved AI image
    # (media_asset_id points at its public STOREFRONT copy). The original
    # upload is never replaced by a generated one.
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="UPLOAD", server_default=text("'UPLOAD'")
    )
    media_asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class InventoryItem(IdMixin, TenantMixin, TimestampMixin, Base):
    """Stock for one variant; sellable stock is available minus reserved."""

    __tablename__ = "inventory_items"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "variant_id", name="uq_inventory_items_tenant_variant"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "variant_id"],
            ["product_variants.tenant_id", "product_variants.id"],
            name="fk_inventory_items_tenant_variant_product_variants",
            ondelete="CASCADE",
        ),
        CheckConstraint("available_quantity >= 0", name="available_not_negative"),
        CheckConstraint("reserved_quantity >= 0", name="reserved_not_negative"),
        CheckConstraint(
            "reserved_quantity <= available_quantity", name="reserved_within_available"
        ),
        CheckConstraint("low_stock_threshold >= 0", name="threshold_not_negative"),
    )

    variant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    available_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    reserved_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    low_stock_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class InventoryMovement(IdMixin, TenantMixin, Base):
    """Append-only record of every stock change."""

    __tablename__ = "inventory_movements"

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "variant_id"],
            ["product_variants.tenant_id", "product_variants.id"],
            name="fk_inventory_movements_tenant_variant_product_variants",
            ondelete="CASCADE",
        ),
        CheckConstraint(f"reason IN ({_REASON_VALUES})", name="reason_valid"),
        Index(
            "ix_inventory_movements_tenant_id_variant_id_created_at",
            "tenant_id",
            "variant_id",
            "created_at",
        ),
    )

    variant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    delta: Mapped[int] = mapped_column(Integer, nullable=False)

    reason: Mapped[str] = mapped_column(String(20), nullable=False)

    reference: Mapped[str | None] = mapped_column(String(120), nullable=True)

    note: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ProductAttributeValue(IdMixin, TenantMixin, TimestampMixin, Base):
    """One allowed value of a filterable attribute, e.g. fabric = "Cotton".

    Products still store the value as text, so values that were typed in before
    this list existed keep working.
    """

    __tablename__ = "product_attribute_values"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_product_attribute_values_tenant_id_id"),
        Index(
            "uq_product_attribute_values_tenant_attribute_value",
            "tenant_id",
            "attribute",
            text("lower(value)"),
            unique=True,
        ),
        CheckConstraint(
            "attribute IN ('fabric', 'occasion', 'sleeve', 'neckline')", name="attribute_valid"
        ),
        CheckConstraint("length(trim(value)) > 0", name="value_not_blank"),
    )

    attribute: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[str] = mapped_column(String(MAX_PRODUCT_ATTRIBUTE_LENGTH), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
