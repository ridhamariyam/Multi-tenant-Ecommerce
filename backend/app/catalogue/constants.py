from enum import Enum


class CatalogueStatus(str, Enum):
    """Lifecycle shared by categories, products and variants; ARCHIVED is a soft delete."""

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class ProductGender(str, Enum):
    """Who a product is marketed for -- a product-level attribute, not a
    variant or category one."""

    MEN = "MEN"
    WOMEN = "WOMEN"
    UNISEX = "UNISEX"


class ProductSort(str, Enum):
    """Sort orders the storefront may ask for."""

    NEWEST = "newest"
    NAME_ASC = "name_asc"
    NAME_DESC = "name_desc"
    PRICE_LOW = "price_low"
    PRICE_HIGH = "price_high"


class InventoryReason(str, Enum):
    """Why a stock level changed. Every movement records one."""

    INITIAL = "INITIAL"
    ADJUSTMENT = "ADJUSTMENT"
    RESTOCK = "RESTOCK"
    RESERVATION = "RESERVATION"
    RELEASE = "RELEASE"
    FULFILLMENT = "FULFILLMENT"


MAX_SKU_LENGTH = 64
MAX_NAME_LENGTH = 150
MAX_DESCRIPTION_LENGTH = 2000

PRICE_PRECISION = 12
PRICE_SCALE = 2

MAX_BRAND_LENGTH = 150

MAX_PRODUCT_ATTRIBUTE_LENGTH = 100

# Product information blocks shown on the product page.
MAX_PRODUCT_INFO_LENGTH = 2000
MAX_COUNTRY_LENGTH = 100

# GST: an HSN code is 4, 6 or 8 digits; a rate is a percentage like 5.00.
HSN_CODE_PATTERN = r"^\d{4}(\d{2}){0,2}$"
MAX_HSN_CODE_LENGTH = 8
GST_RATE_PRECISION = 5
GST_RATE_SCALE = 2
MAX_GST_RATE = 100

# Size chart limits keep one product's chart a readable table.
MAX_SIZE_CHART_MEASUREMENTS = 15
MAX_SIZE_CHART_ROWS = 30
MAX_SIZE_CHART_LABEL_LENGTH = 40
MAX_SIZE_CHART_NOTE_LENGTH = 500
CM_PER_INCH = "2.54"

MAX_RELATED_PRODUCTS = 20
MAX_SLUG_LENGTH = 140
DEFAULT_RELATED_LIMIT = 8
MAX_RELATED_LIMIT = 24


class SizeChartUnit(str, Enum):
    INCH = "in"
    CENTIMETRE = "cm"

MAX_SHORT_DESCRIPTION_LENGTH = 500

MAX_SEO_TITLE_LENGTH = 200

MAX_SEO_DESCRIPTION_LENGTH = 500

MAX_IMAGE_URL_LENGTH = 2048
MAX_ALT_TEXT_LENGTH = 255

MAX_OPTION_NAME_LENGTH = 60
MAX_OPTION_VALUE_LENGTH = 100

MIN_PRODUCT_IMAGES = 1

MAX_OPTIONS_PER_PRODUCT = 3


class ProductAttribute(str, Enum):
    """Product fields whose values the store keeps as a managed list."""

    FABRIC = "fabric"
    OCCASION = "occasion"
    SLEEVE = "sleeve"
    NECKLINE = "neckline"
