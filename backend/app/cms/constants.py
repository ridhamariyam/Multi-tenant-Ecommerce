from enum import Enum


class ContentStatus(str, Enum):
    DRAFT = "DRAFT"
    # Live once published_at has passed (a future published_at = scheduled).
    PUBLISHED = "PUBLISHED"


class SectionType(str, Enum):
    HERO_BANNER = "HERO_BANNER"
    PROMO_STRIP = "PROMO_STRIP"
    FEATURED_PRODUCTS = "FEATURED_PRODUCTS"
    NEW_ARRIVALS = "NEW_ARRIVALS"
    BESTSELLERS = "BESTSELLERS"
    SEASONAL = "SEASONAL"


PRODUCT_SECTIONS = frozenset(
    {
        SectionType.FEATURED_PRODUCTS,
        SectionType.NEW_ARRIVALS,
        SectionType.BESTSELLERS,
        SectionType.SEASONAL,
    }
)


class PageType(str, Enum):
    ABOUT = "ABOUT"
    CONTACT = "CONTACT"
    SHIPPING_POLICY = "SHIPPING_POLICY"
    RETURN_POLICY = "RETURN_POLICY"
    PRIVACY_POLICY = "PRIVACY_POLICY"
    TERMS = "TERMS"
    FAQ = "FAQ"
    CUSTOM = "CUSTOM"


class MenuLocation(str, Enum):
    HEADER = "HEADER"
    FOOTER = "FOOTER"


class LinkType(str, Enum):
    URL = "URL"
    HOME = "HOME"
    CATEGORY = "CATEGORY"
    PRODUCT = "PRODUCT"
    PAGE = "PAGE"
    BLOG_POST = "BLOG_POST"
    BLOG_INDEX = "BLOG_INDEX"
    FAQ = "FAQ"


SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
MAX_SLUG_LENGTH = 120
MAX_TITLE_LENGTH = 200
MAX_BODY_LENGTH = 100_000
MAX_SECTION_ITEMS = 12
MAX_SECTION_PRODUCTS = 48
DEFAULT_SECTION_LIMIT = 8
MAX_TAGS = 20
