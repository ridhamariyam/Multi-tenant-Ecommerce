from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.catalogue.constants import (
    CM_PER_INCH,
    HSN_CODE_PATTERN,
    MAX_ALT_TEXT_LENGTH,
    MAX_BRAND_LENGTH,
    MAX_COUNTRY_LENGTH,
    MAX_DESCRIPTION_LENGTH,
    MAX_GST_RATE,
    MAX_IMAGE_URL_LENGTH,
    MAX_NAME_LENGTH,
    MAX_OPTION_NAME_LENGTH,
    MAX_OPTION_VALUE_LENGTH,
    MAX_OPTIONS_PER_PRODUCT,
    MAX_PRODUCT_ATTRIBUTE_LENGTH,
    MAX_PRODUCT_INFO_LENGTH,
    MAX_RELATED_PRODUCTS,
    MAX_SEO_DESCRIPTION_LENGTH,
    MAX_SEO_TITLE_LENGTH,
    MAX_SHORT_DESCRIPTION_LENGTH,
    MAX_SIZE_CHART_LABEL_LENGTH,
    MAX_SIZE_CHART_MEASUREMENTS,
    MAX_SIZE_CHART_NOTE_LENGTH,
    MAX_SIZE_CHART_ROWS,
    MAX_SKU_LENGTH,
    MAX_SLUG_LENGTH,
    MIN_PRODUCT_IMAGES,
    PRICE_PRECISION,
    PRICE_SCALE,
    CatalogueStatus,
    InventoryReason,
    ProductAttribute,
    ProductGender,
    ProductSort,
    SizeChartUnit,
)
from app.core.config import get_settings
from app.core.pagination import PageParams
from app.core.schemas import PartialUpdate, StrictModel, blank_to_none, not_blank
from app.core.slugs import SLUG_PATTERN

SKU_PATTERN = r"^[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*$"

Name = Field(min_length=1, max_length=MAX_NAME_LENGTH)
Sku = Field(min_length=1, max_length=MAX_SKU_LENGTH, pattern=SKU_PATTERN)
Description = Field(default=None, max_length=MAX_DESCRIPTION_LENGTH)
Price = Field(ge=0, max_digits=PRICE_PRECISION, decimal_places=PRICE_SCALE)
Attribute = Field(default=None, max_length=MAX_PRODUCT_ATTRIBUTE_LENGTH)
HsnCode = Field(default=None, pattern=HSN_CODE_PATTERN, description="4, 6 or 8 digit HSN code")
GstRate = Field(
    default=None, ge=0, le=MAX_GST_RATE, decimal_places=2, description="GST %, e.g. 5.00"
)
ProductInfo = Field(default=None, max_length=MAX_PRODUCT_INFO_LENGTH)
SalePrice = Field(default=None, ge=0, max_digits=PRICE_PRECISION, decimal_places=PRICE_SCALE)


def _strip_optional(value: str | None) -> str | None:
    return value if value is None else value.strip()


def _require_url(value: str) -> str:
    url = not_blank(value)
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("must be a valid http or https URL")
    return url


def _require_image_url(value: str) -> str:
    """An http(s) URL, or a file this store uploaded itself (e.g. /media/<tenant>/x.jpg)."""
    url = not_blank(value)
    base = get_settings().storage_public_base_url.rstrip("/")
    if base.startswith("/") and url.startswith(base + "/"):
        if ".." in url.split("/") or "\\" in url or "?" in url or "#" in url:
            raise ValueError("must be a valid image path")
        return url
    return _require_url(url)


def _require_url_optional(value: str | None) -> str | None:
    return value if value is None else _require_url(value)


class CategoryCreate(StrictModel):
    name: str = Name
    description: str | None = Description
    status: CatalogueStatus = CatalogueStatus.ACTIVE
    parent_id: UUID | None = Field(
        default=None, description="Parent category; omit for a top-level category"
    )
    hsn_code: str | None = HsnCode
    gst_rate: Decimal | None = GstRate

    _strip_name = field_validator("name")(not_blank)


class CategoryUpdate(PartialUpdate):
    name: str | None = Field(default=None, min_length=1, max_length=MAX_NAME_LENGTH)
    description: str | None = Description
    status: CatalogueStatus | None = None
    parent_id: UUID | None = Field(
        default=None, description="New parent category; null moves it to the top level"
    )
    hsn_code: str | None = HsnCode
    gst_rate: Decimal | None = GstRate

    _strip_name = field_validator("name")(not_blank)


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    parent_id: UUID | None = None
    name: str
    description: str | None
    status: CatalogueStatus
    hsn_code: str | None = None
    gst_rate: Decimal | None = None


class CategoryStorefrontRead(BaseModel):
    """Public view. Omits tenant_id and lifecycle state."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    parent_id: UUID | None = None
    name: str
    description: str | None


class CategoryQuery(PageParams):
    """Narrow a category listing to one level of the tree."""

    parent_id: UUID | None = Field(
        default=None, description="Only the direct sub-categories of this category"
    )
    top_level: bool = Field(
        default=False, description="Only categories that have no parent"
    )


class AdminCategoryQuery(CategoryQuery):
    """Admin-only lifecycle filters; ordinary listings still hide archived rows."""

    status: CatalogueStatus | None = Field(
        default=None,
        description="Lifecycle status; archived rows require explicit selection",
    )
    include_archived: bool = Field(
        default=False, description="Include archived categories with other statuses"
    )


class ProductImageCreate(StrictModel):
    url: str = Field(min_length=1, max_length=MAX_IMAGE_URL_LENGTH)
    alt_text: str | None = Field(default=None, max_length=MAX_ALT_TEXT_LENGTH)
    sort_order: int = Field(default=0, ge=0)
    is_primary: bool = False

    _check_url = field_validator("url")(_require_image_url)
    _strip_alt_text = field_validator("alt_text")(_strip_optional)


class ProductImageUpdate(PartialUpdate):
    url: str | None = Field(default=None, min_length=1, max_length=MAX_IMAGE_URL_LENGTH)
    alt_text: str | None = Field(default=None, max_length=MAX_ALT_TEXT_LENGTH)
    sort_order: int | None = Field(default=None, ge=0)
    is_primary: bool | None = None

    _check_url = field_validator("url")(_require_url_optional)
    _strip_alt_text = field_validator("alt_text")(_strip_optional)


class ImageOrderItem(StrictModel):
    id: UUID
    sort_order: int = Field(ge=0)


class ImageReorderPayload(StrictModel):
    images: list[ImageOrderItem] = Field(min_length=1)


class ProductImageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    product_id: UUID
    url: str
    alt_text: str | None
    sort_order: int
    is_primary: bool


class ProductImageSummary(BaseModel):
    """The one image shown beside a cart or wishlist line."""

    model_config = ConfigDict(from_attributes=True)

    url: str
    alt_text: str | None = None


class ProductImageStorefrontRead(BaseModel):
    """Public view. Exposes the URL only -- never a storage path or credential."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    url: str
    alt_text: str | None
    sort_order: int
    is_primary: bool


class VariantOptionValue(StrictModel):
    """One dimension of a variant, e.g. name="Color", value="Black"."""

    name: str = Field(min_length=1, max_length=MAX_OPTION_NAME_LENGTH)
    value: str = Field(min_length=1, max_length=MAX_OPTION_VALUE_LENGTH)

    _strip_name = field_validator("name")(not_blank)
    _strip_value = field_validator("value")(not_blank)


class ProductOptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    position: int


class StorefrontOption(BaseModel):
    """An option plus every value that an in-stock variant actually offers."""

    name: str
    values: list[str]


class InventoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    variant_id: UUID
    available_quantity: int
    reserved_quantity: int
    low_stock_threshold: int


class InventoryStatus(InventoryRead):
    sellable_quantity: int
    is_low_stock: bool


class InventorySet(StrictModel):
    available_quantity: int = Field(ge=0)
    note: str | None = Field(default=None, max_length=255)


class InventoryAdjust(StrictModel):
    delta: int = Field(description="Signed change; negative removes stock")
    reason: InventoryReason = InventoryReason.ADJUSTMENT
    reference: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=255)

    @field_validator("delta")
    @classmethod
    def _reject_zero(cls, value: int) -> int:
        if value == 0:
            raise ValueError("delta must not be zero")
        return value


class InventoryThreshold(StrictModel):
    low_stock_threshold: int = Field(ge=0)


class InventoryMovementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    variant_id: UUID
    delta: int
    reason: InventoryReason
    reference: str | None
    note: str | None


class VariantCreate(StrictModel):
    sku: str = Sku
    name: str = Name
    price: Decimal = Price
    status: CatalogueStatus = CatalogueStatus.DRAFT

    options: list[VariantOptionValue] = Field(
        default_factory=list, max_length=MAX_OPTIONS_PER_PRODUCT
    )
    initial_quantity: int = Field(default=0, ge=0)
    low_stock_threshold: int = Field(default=0, ge=0)

    sale_price: Decimal | None = SalePrice
    sale_starts_at: datetime | None = None
    sale_ends_at: datetime | None = None

    _strip_name = field_validator("name")(not_blank)

    @field_validator("options")
    @classmethod
    def _reject_duplicate_options(
        cls, value: list[VariantOptionValue]
    ) -> list[VariantOptionValue]:
        names = [option.name.lower() for option in value]
        if len(names) != len(set(names)):
            raise ValueError("an option name may only appear once per variant")
        return value


class VariantUpdate(PartialUpdate):
    sku: str | None = Field(
        default=None, min_length=1, max_length=MAX_SKU_LENGTH, pattern=SKU_PATTERN
    )
    name: str | None = Field(default=None, min_length=1, max_length=MAX_NAME_LENGTH)
    price: Decimal | None = Field(
        default=None, ge=0, max_digits=PRICE_PRECISION, decimal_places=PRICE_SCALE
    )
    status: CatalogueStatus | None = None
    options: list[VariantOptionValue] | None = Field(
        default=None, max_length=MAX_OPTIONS_PER_PRODUCT
    )
    sale_price: Decimal | None = SalePrice
    sale_starts_at: datetime | None = None
    sale_ends_at: datetime | None = None

    _strip_name = field_validator("name")(not_blank)


class VariantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    product_id: UUID
    sku: str
    name: str
    price: Decimal
    status: CatalogueStatus

    sale_price: Decimal | None = None
    sale_starts_at: datetime | None = None
    sale_ends_at: datetime | None = None
    effective_price: Decimal | None = Field(
        default=None, description="What a shopper pays right now"
    )
    is_on_sale: bool = False

    options: dict[str, str] = {}
    inventory: InventoryStatus | None = None


class VariantStorefrontRead(BaseModel):
    """Public view. Exposes availability, never raw reservation bookkeeping."""

    id: UUID
    product_id: UUID
    sku: str
    name: str
    price: Decimal = Field(description="What the shopper pays now, sale included")
    compare_at_price: Decimal | None = Field(
        default=None, description="The regular price, set only while a sale is on"
    )
    sale_ends_at: datetime | None = None
    options: dict[str, str] = {}
    in_stock: bool
    available_quantity: int


class SizeChartRow(StrictModel):
    """One size and its measurements, in the chart's unit."""

    size: str = Field(min_length=1, max_length=MAX_SIZE_CHART_LABEL_LENGTH)
    values: dict[str, Decimal] = Field(min_length=1)

    _strip_size = field_validator("size")(not_blank)

    @field_validator("values")
    @classmethod
    def _positive_measurements(cls, value: dict[str, Decimal]) -> dict[str, Decimal]:
        for measurement, amount in value.items():
            if amount <= 0 or amount > 1000:
                raise ValueError(f"{measurement} must be between 0 and 1000")
        return value


class SizeChart(StrictModel):
    """A product's size chart. Entered in one unit; read back in both."""

    unit: SizeChartUnit = SizeChartUnit.INCH
    measurements: list[str] = Field(min_length=1, max_length=MAX_SIZE_CHART_MEASUREMENTS)
    rows: list[SizeChartRow] = Field(min_length=1, max_length=MAX_SIZE_CHART_ROWS)
    note: str | None = Field(default=None, max_length=MAX_SIZE_CHART_NOTE_LENGTH)

    @field_validator("measurements")
    @classmethod
    def _clean_measurements(cls, value: list[str]) -> list[str]:
        cleaned = [not_blank(name) for name in value]
        if any(len(name) > MAX_SIZE_CHART_LABEL_LENGTH for name in cleaned):
            raise ValueError("measurement names are too long")
        if len({name.lower() for name in cleaned}) != len(cleaned):
            raise ValueError("each measurement may only appear once")
        return cleaned

    @model_validator(mode="after")
    def _rows_match_measurements(self) -> SizeChart:
        known = set(self.measurements)
        sizes = [row.size.lower() for row in self.rows]
        if len(sizes) != len(set(sizes)):
            raise ValueError("each size may only appear once")
        for row in self.rows:
            unknown = set(row.values) - known
            if unknown:
                raise ValueError(
                    f"size {row.size} has unknown measurements: {', '.join(sorted(unknown))}"
                )
        return self

    def to_storage(self) -> dict:
        return {
            "unit": self.unit.value,
            "measurements": self.measurements,
            "rows": [
                {"size": row.size, "values": {k: str(v) for k, v in row.values.items()}}
                for row in self.rows
            ],
            "note": self.note,
        }


class SizeChartRowRead(BaseModel):
    size: str
    values_in: dict[str, Decimal]
    values_cm: dict[str, Decimal]


class SizeChartRead(BaseModel):
    unit: SizeChartUnit
    measurements: list[str]
    rows: list[SizeChartRowRead]
    note: str | None = None


_TENTH = Decimal("0.1")


def render_size_chart(stored: dict | None) -> SizeChartRead | None:
    """Stored chart -> both inches and centimetres, rounded to one decimal."""
    if not stored:
        return None

    unit = SizeChartUnit(stored.get("unit", SizeChartUnit.INCH.value))
    factor = Decimal(CM_PER_INCH)
    rows = []
    for row in stored.get("rows", []):
        given = {name: Decimal(str(amount)) for name, amount in row["values"].items()}
        if unit is SizeChartUnit.INCH:
            inches = given
            cms = {name: amount * factor for name, amount in given.items()}
        else:
            cms = given
            inches = {name: amount / factor for name, amount in given.items()}
        rows.append(
            SizeChartRowRead(
                size=row["size"],
                values_in={k: v.quantize(_TENTH, ROUND_HALF_UP) for k, v in inches.items()},
                values_cm={k: v.quantize(_TENTH, ROUND_HALF_UP) for k, v in cms.items()},
            )
        )
    return SizeChartRead(
        unit=unit,
        measurements=list(stored.get("measurements", [])),
        rows=rows,
        note=stored.get("note"),
    )


ProductSlug = Field(
    default=None,
    max_length=MAX_SLUG_LENGTH,
    pattern=SLUG_PATTERN,
    description="URL part, e.g. cotton-kurta-navy. Omit to make one from the name.",
)


class ProductCreate(StrictModel):
    category_id: UUID
    name: str = Name
    slug: str | None = ProductSlug
    short_description: str | None = Field(
        default=None, max_length=MAX_SHORT_DESCRIPTION_LENGTH
    )
    description: str | None = Description
    brand: str | None = Field(default=None, max_length=MAX_BRAND_LENGTH)
    status: CatalogueStatus = CatalogueStatus.DRAFT
    gender: ProductGender | None = None
    fabric: str | None = Attribute
    occasion: str | None = Attribute
    sleeve: str | None = Attribute
    neckline: str | None = Attribute
    fabric_details: str | None = ProductInfo
    washing_instructions: str | None = ProductInfo
    country_of_origin: str | None = Field(default=None, max_length=MAX_COUNTRY_LENGTH)
    size_chart: SizeChart | None = None
    hsn_code: str | None = HsnCode
    gst_rate: Decimal | None = GstRate
    is_featured: bool = False
    seo_title: str | None = Field(default=None, max_length=MAX_SEO_TITLE_LENGTH)
    seo_description: str | None = Field(
        default=None, max_length=MAX_SEO_DESCRIPTION_LENGTH
    
    )

    images: list[ProductImageCreate] = Field(min_length=MIN_PRODUCT_IMAGES)

    _strip_name = field_validator("name")(not_blank)
    _strip_short_description = field_validator("short_description")(_strip_optional)
    _strip_brand = field_validator("brand")(_strip_optional)
    _clean_attributes = field_validator("fabric", "occasion", "sleeve", "neckline")(
        blank_to_none
    )
    _clean_info = field_validator(
        "fabric_details", "washing_instructions", "country_of_origin"
    )(blank_to_none)

    @field_validator("images")
    @classmethod
    def _at_most_one_primary(
        cls, value: list[ProductImageCreate]
    ) -> list[ProductImageCreate]:
        if sum(1 for image in value if image.is_primary) > 1:
            raise ValueError("only one image can be marked as primary")
        return value


class ProductUpdate(PartialUpdate):
    category_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=MAX_NAME_LENGTH)
    slug: str | None = ProductSlug
    short_description: str | None = Field(
        default=None, max_length=MAX_SHORT_DESCRIPTION_LENGTH
    )
    description: str | None = Description
    brand: str | None = Field(default=None, max_length=MAX_BRAND_LENGTH)
    status: CatalogueStatus | None = None
    gender: ProductGender | None = None
    fabric: str | None = Attribute
    occasion: str | None = Attribute
    sleeve: str | None = Attribute
    neckline: str | None = Attribute
    fabric_details: str | None = ProductInfo
    washing_instructions: str | None = ProductInfo
    country_of_origin: str | None = Field(default=None, max_length=MAX_COUNTRY_LENGTH)
    size_chart: SizeChart | None = None
    hsn_code: str | None = HsnCode
    gst_rate: Decimal | None = GstRate
    is_featured: bool | None = None
    seo_title: str | None = Field(default=None, max_length=MAX_SEO_TITLE_LENGTH)
    seo_description: str | None = Field(
        default=None, max_length=MAX_SEO_DESCRIPTION_LENGTH
    )

    _strip_name = field_validator("name")(not_blank)
    _strip_short_description = field_validator("short_description")(_strip_optional)
    _strip_brand = field_validator("brand")(_strip_optional)
    _clean_attributes = field_validator("fabric", "occasion", "sleeve", "neckline")(
        blank_to_none
    )
    _clean_info = field_validator(
        "fabric_details", "washing_instructions", "country_of_origin"
    )(blank_to_none)


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    category_id: UUID
    name: str
    slug: str
    short_description: str | None
    description: str | None
    brand: str | None
    status: CatalogueStatus
    gender: ProductGender | None
    fabric: str | None = None
    occasion: str | None = None
    sleeve: str | None = None
    neckline: str | None = None
    fabric_details: str | None = None
    washing_instructions: str | None = None
    country_of_origin: str | None = None
    size_chart: SizeChartRead | None = None
    hsn_code: str | None = None
    gst_rate: Decimal | None = None
    is_featured: bool
    seo_title: str | None
    seo_description: str | None

    images: list[ProductImageRead] = []
    options: list[ProductOptionRead] = []

    @field_validator("size_chart", mode="before")
    @classmethod
    def _render_size_chart(cls, value):
        return render_size_chart(value) if isinstance(value, dict) else value


class ProductSummaryStorefrontRead(BaseModel):
    """Lightweight listing row: primary image and price range only."""

    id: UUID
    slug: str
    category_id: UUID
    name: str
    short_description: str | None
    brand: str | None
    fabric: str | None = None
    occasion: str | None = None
    sleeve: str | None = None
    neckline: str | None = None
    is_featured: bool

    primary_image: ProductImageStorefrontRead | None = None
    price_from: Decimal | None = None
    price_to: Decimal | None = None
    on_sale: bool = False
    in_stock: bool = False


class ProductStorefrontRead(BaseModel):
    """Full public product. Omits tenant_id, lifecycle state and audit fields."""

    id: UUID
    slug: str
    category: CategoryStorefrontRead
    name: str
    short_description: str | None
    description: str | None
    brand: str | None
    fabric: str | None = None
    occasion: str | None = None
    sleeve: str | None = None
    neckline: str | None = None
    fabric_details: str | None = None
    washing_instructions: str | None = None
    country_of_origin: str | None = None
    size_chart: SizeChartRead | None = None
    is_featured: bool

    seo_title: str | None
    seo_description: str | None

    images: list[ProductImageStorefrontRead] = []
    options: list[StorefrontOption] = []
    variants: list[VariantStorefrontRead] = []

    price_from: Decimal | None = None
    price_to: Decimal | None = None
    on_sale: bool = False
    in_stock: bool = False


class ProductQuery(PageParams):
    """Shared product filters and sort options."""

    category_id: UUID | None = Field(
        default=None, description="Products in this category or any of its sub-categories"
    )
    search: str | None = Field(default=None, max_length=120)
    brand: str | None = Field(default=None, max_length=150)
    fabric: str | None = Field(default=None, max_length=MAX_PRODUCT_ATTRIBUTE_LENGTH)
    occasion: str | None = Field(default=None, max_length=MAX_PRODUCT_ATTRIBUTE_LENGTH)
    sleeve: str | None = Field(default=None, max_length=MAX_PRODUCT_ATTRIBUTE_LENGTH)
    neckline: str | None = Field(default=None, max_length=MAX_PRODUCT_ATTRIBUTE_LENGTH)
    featured: bool | None = None
    sort: ProductSort = ProductSort.NAME_ASC


class AdminProductQuery(ProductQuery):
    """Admin-only status filter; omitted status keeps archived rows hidden."""

    status: CatalogueStatus | None = None


class StorefrontProductQuery(ProductQuery):
    """The public listing filters, which add a price range."""

    min_price: Decimal | None = Field(default=None, ge=0)
    max_price: Decimal | None = Field(default=None, ge=0)


class RelatedProductsUpdate(StrictModel):
    """The hand-picked "you may also like" list, in display order."""

    product_ids: list[UUID] = Field(max_length=MAX_RELATED_PRODUCTS)

    @field_validator("product_ids")
    @classmethod
    def _unique(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("a product may only be listed once")
        return value


class RelatedProductRead(BaseModel):
    id: UUID
    name: str
    status: CatalogueStatus
    position: int


class RelatedProductsStorefrontRead(BaseModel):
    you_may_also_like: list[ProductSummaryStorefrontRead] = []
    customers_also_bought: list[ProductSummaryStorefrontRead] = []


class FilterValueCount(BaseModel):
    value: str
    count: int


class FilterOptionsRead(BaseModel):
    """Distinct values with product counts, for building filter dropdowns."""

    fabric: list[FilterValueCount] = []
    occasion: list[FilterValueCount] = []
    sleeve: list[FilterValueCount] = []
    neckline: list[FilterValueCount] = []


class FilterOptionsQuery(StrictModel):
    category_id: UUID | None = Field(
        default=None, description="Only products in this category or its sub-categories"
    )


class ImportErrorRow(BaseModel):
    row: int
    message: str


class UploadedImageRead(BaseModel):
    url: str


class ImageUploadPresignRequest(StrictModel):
    content_type: str = Field(min_length=1, max_length=100, examples=["image/jpeg"])
    size_bytes: int = Field(gt=0, description="Size of the file the browser will send")


class ImageUploadPresignRead(BaseModel):
    """POST `fields` plus the file (as the last form field, named `file`) to `url`."""

    upload_id: str
    url: str
    fields: dict[str, str]
    expires_at: datetime
    max_bytes: int


class ImageUploadComplete(StrictModel):
    upload_id: str = Field(min_length=1, max_length=200)


class ProductImageUploadComplete(ImageUploadComplete):
    alt_text: str | None = Field(default=None, max_length=MAX_ALT_TEXT_LENGTH)
    sort_order: int = Field(default=0, ge=0)
    is_primary: bool = False

    _strip_alt_text = field_validator("alt_text")(_strip_optional)


class ProductImportResult(BaseModel):
    rows: int
    products: int
    variants: int
    dry_run: bool
    errors: list[ImportErrorRow]


# Managed value lists for fabric, occasion, sleeve and neckline.


class AttributeValueCreate(StrictModel):
    attribute: ProductAttribute
    value: str = Field(min_length=1, max_length=MAX_PRODUCT_ATTRIBUTE_LENGTH)
    is_active: bool = True

    _clean = field_validator("value")(not_blank)


class AttributeValueUpdate(PartialUpdate):
    value: str | None = Field(default=None, min_length=1, max_length=MAX_PRODUCT_ATTRIBUTE_LENGTH)
    is_active: bool | None = None
    position: int | None = Field(default=None, ge=0)

    _clean = field_validator("value")(not_blank)


class AttributeValueRead(BaseModel):
    id: UUID
    attribute: ProductAttribute
    value: str
    is_active: bool
    position: int
    product_count: int = Field(description="Products using this value (any status)")
