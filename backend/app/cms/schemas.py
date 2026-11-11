from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.catalogue.schemas import ProductSummaryStorefrontRead
from app.cms.constants import (
    DEFAULT_SECTION_LIMIT,
    MAX_BODY_LENGTH,
    MAX_SECTION_ITEMS,
    MAX_SECTION_PRODUCTS,
    MAX_SLUG_LENGTH,
    MAX_TAGS,
    MAX_TITLE_LENGTH,
    SLUG_PATTERN,
    ContentStatus,
    LinkType,
    MenuLocation,
    PageType,
    SectionType,
)
from app.core.pagination import PageParams
from app.core.schemas import PartialUpdate, StrictModel
from app.core.slugs import slugify as core_slugify

Slug = Field(default=None, max_length=MAX_SLUG_LENGTH, pattern=SLUG_PATTERN)
Title = Field(min_length=1, max_length=MAX_TITLE_LENGTH)


def slugify(text: str) -> str:
    return core_slugify(text, MAX_SLUG_LENGTH)


def _link(value: str | None) -> str | None:
    """A banner/menu link: a site path ("/sale") or an http(s) URL."""
    if value is None or not value.strip():
        return None
    value = value.strip()
    if value.startswith("/") and not value.startswith("//"):
        return value
    parts = urlsplit(value)
    if parts.scheme in {"http", "https"} and parts.netloc:
        return value
    raise ValueError("must be a path starting with / or an http(s) URL")


def _image(value: str | None) -> str | None:
    """An image URL: an uploaded media path (/media/...) or an http(s) URL."""
    return _link(value)


def _clean_tags(value: list[str] | None) -> list[str] | None:
    if value is None:
        return None
    cleaned: list[str] = []
    for tag in value:
        tag = tag.strip()[:40]
        if tag and tag.lower() not in {t.lower() for t in cleaned}:
            cleaned.append(tag)
    return cleaned


class Publishable(BaseModel):
    status: ContentStatus
    published_at: datetime | None
    is_live: bool = Field(description="Published and its publish time has passed")
    created_by_id: UUID | None = None
    updated_by_id: UUID | None = None
    published_by_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class PublishRequest(StrictModel):
    publish_at: datetime | None = Field(
        default=None, description="Leave empty to publish now; a future time schedules it"
    )


class ReorderRequest(StrictModel):
    ids: list[UUID] = Field(min_length=1, max_length=200)


# ------------------------------------------------------------------ media


class MediaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    url: str
    filename: str
    content_type: str
    size_bytes: int
    alt_text: str | None
    uploaded_by_id: UUID | None
    created_at: datetime


class MediaUpdate(StrictModel):
    alt_text: str | None = Field(default=None, max_length=255)


# --------------------------------------------------------------- sections


class BannerItem(StrictModel):
    image_url: str | None = Field(default=None, max_length=2048)
    mobile_image_url: str | None = Field(default=None, max_length=2048)
    heading: str | None = Field(default=None, max_length=200)
    text: str | None = Field(default=None, max_length=500)
    link_url: str | None = Field(default=None, max_length=2048)
    cta_label: str | None = Field(default=None, max_length=50)
    alt_text: str | None = Field(default=None, max_length=255)

    _links = field_validator("link_url")(_link)
    _images = field_validator("image_url", "mobile_image_url")(_image)


class SectionSettings(StrictModel):
    product_ids: list[UUID] | None = Field(default=None, max_length=MAX_SECTION_PRODUCTS)
    category_id: UUID | None = None
    limit: int = Field(default=DEFAULT_SECTION_LIMIT, ge=1, le=MAX_SECTION_PRODUCTS)
    days: int = Field(default=30, ge=1, le=365, description="Bestsellers look-back window")
    countdown_ends_at: datetime | None = None


class _SectionFields(StrictModel):
    title: str | None = Field(default=None, max_length=MAX_TITLE_LENGTH)
    subtitle: str | None = Field(default=None, max_length=500)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    items: list[BannerItem] | None = Field(default=None, max_length=MAX_SECTION_ITEMS)
    settings: SectionSettings | None = None


class SectionCreate(_SectionFields):
    section_type: SectionType
    is_active: bool = False

    @model_validator(mode="after")
    def _window(self) -> SectionCreate:
        if self.starts_at and self.ends_at and self.starts_at >= self.ends_at:
            raise ValueError("starts_at must be before ends_at")
        return self


class SectionUpdate(PartialUpdate):
    title: str | None = Field(default=None, max_length=MAX_TITLE_LENGTH)
    subtitle: str | None = Field(default=None, max_length=500)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    items: list[BannerItem] | None = Field(default=None, max_length=MAX_SECTION_ITEMS)
    settings: SectionSettings | None = None
    is_active: bool | None = None


class SectionRead(BaseModel):
    id: UUID
    section_type: SectionType
    title: str | None
    subtitle: str | None
    is_active: bool
    position: int
    starts_at: datetime | None
    ends_at: datetime | None
    is_live: bool
    items: list[BannerItem]
    settings: SectionSettings
    created_by_id: UUID | None
    updated_by_id: UUID | None
    created_at: datetime
    updated_at: datetime


# ------------------------------------------------------------------ pages


class PageCreate(StrictModel):
    title: str = Title
    slug: str | None = Slug
    page_type: PageType = PageType.CUSTOM
    body: str = Field(default="", max_length=MAX_BODY_LENGTH, description="Markdown")
    seo_title: str | None = Field(default=None, max_length=200)
    seo_description: str | None = Field(default=None, max_length=500)


class PageUpdate(PartialUpdate):
    title: str | None = Field(default=None, min_length=1, max_length=MAX_TITLE_LENGTH)
    slug: str | None = Slug
    page_type: PageType | None = None
    body: str | None = Field(default=None, max_length=MAX_BODY_LENGTH)
    seo_title: str | None = Field(default=None, max_length=200)
    seo_description: str | None = Field(default=None, max_length=500)


class PageRead(Publishable):
    id: UUID
    slug: str
    title: str
    page_type: PageType
    body: str
    seo_title: str | None
    seo_description: str | None


class PageSummary(BaseModel):
    id: UUID
    slug: str
    title: str
    page_type: PageType
    status: ContentStatus
    published_at: datetime | None
    is_live: bool
    updated_at: datetime


class MediaQuery(PageParams):
    search: str | None = Field(default=None, max_length=100)


class ContentQuery(PageParams):
    status: ContentStatus | None = None
    search: str | None = Field(default=None, max_length=100)


# ------------------------------------------------------------------- FAQs


class FaqCategoryWrite(StrictModel):
    name: str = Field(min_length=1, max_length=150)
    is_active: bool = True


class FaqCategoryUpdate(PartialUpdate):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    is_active: bool | None = None


class FaqCategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    position: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class FaqCreate(StrictModel):
    category_id: UUID
    question: str = Field(min_length=1, max_length=500)
    answer: str = Field(min_length=1, max_length=20_000, description="Markdown")


class FaqUpdate(PartialUpdate):
    category_id: UUID | None = None
    question: str | None = Field(default=None, min_length=1, max_length=500)
    answer: str | None = Field(default=None, min_length=1, max_length=20_000)


class FaqRead(Publishable):
    id: UUID
    category_id: UUID
    question: str
    answer: str
    position: int


# ------------------------------------------------------------- navigation


class _NavFields(StrictModel):
    label: str = Field(min_length=1, max_length=100)
    link_type: LinkType
    target: str | None = Field(default=None, max_length=2048)
    parent_id: UUID | None = None
    is_active: bool = True
    open_in_new_tab: bool = False


class NavigationCreate(_NavFields):
    menu: MenuLocation


class NavigationUpdate(PartialUpdate):
    label: str | None = Field(default=None, min_length=1, max_length=100)
    link_type: LinkType | None = None
    target: str | None = Field(default=None, max_length=2048)
    parent_id: UUID | None = None
    is_active: bool | None = None
    open_in_new_tab: bool | None = None


class NavigationRead(BaseModel):
    id: UUID
    menu: MenuLocation
    label: str
    link_type: LinkType
    target: str | None
    href: str = Field(description="Suggested storefront path or URL for the link")
    parent_id: UUID | None
    position: int
    is_active: bool
    open_in_new_tab: bool
    children: list[NavigationRead] = []


# ------------------------------------------------------------------- blog


class BlogCreate(StrictModel):
    title: str = Title
    slug: str | None = Slug
    excerpt: str | None = Field(default=None, max_length=500)
    content: str = Field(default="", max_length=MAX_BODY_LENGTH, description="Markdown")
    featured_image_url: str | None = Field(default=None, max_length=2048)
    author_name: str | None = Field(default=None, max_length=150)
    category: str | None = Field(default=None, max_length=100)
    tags: list[str] = Field(default_factory=list, max_length=MAX_TAGS)
    seo_title: str | None = Field(default=None, max_length=200)
    seo_description: str | None = Field(default=None, max_length=500)

    _image = field_validator("featured_image_url")(_image)
    _tags = field_validator("tags")(_clean_tags)


class BlogUpdate(PartialUpdate):
    title: str | None = Field(default=None, min_length=1, max_length=MAX_TITLE_LENGTH)
    slug: str | None = Slug
    excerpt: str | None = Field(default=None, max_length=500)
    content: str | None = Field(default=None, max_length=MAX_BODY_LENGTH)
    featured_image_url: str | None = Field(default=None, max_length=2048)
    author_name: str | None = Field(default=None, max_length=150)
    category: str | None = Field(default=None, max_length=100)
    tags: list[str] | None = Field(default=None, max_length=MAX_TAGS)
    seo_title: str | None = Field(default=None, max_length=200)
    seo_description: str | None = Field(default=None, max_length=500)

    _image = field_validator("featured_image_url")(_image)
    _tags = field_validator("tags")(_clean_tags)


class BlogRead(Publishable):
    id: UUID
    slug: str
    title: str
    excerpt: str | None
    content: str
    featured_image_url: str | None
    author_name: str | None
    category: str | None
    tags: list[str]
    seo_title: str | None
    seo_description: str | None


class BlogSummary(BaseModel):
    id: UUID
    slug: str
    title: str
    excerpt: str | None
    featured_image_url: str | None
    author_name: str | None
    category: str | None
    tags: list[str]
    status: ContentStatus
    published_at: datetime | None
    is_live: bool


class BlogQuery(ContentQuery):
    tag: str | None = Field(default=None, max_length=40)
    category: str | None = Field(default=None, max_length=100)


# ------------------------------------------------------------- storefront


class StorefrontSection(BaseModel):
    id: UUID
    section_type: SectionType
    title: str | None
    subtitle: str | None
    position: int
    ends_at: datetime | None
    countdown_ends_at: datetime | None = None
    items: list[BannerItem]
    products: list[ProductSummaryStorefrontRead] = []


class StorefrontPage(BaseModel):
    slug: str
    title: str
    page_type: PageType
    body: str
    body_format: str = "markdown"
    seo_title: str | None
    seo_description: str | None
    published_at: datetime | None
    updated_at: datetime


class StorefrontFaq(BaseModel):
    id: UUID
    question: str
    answer: str


class StorefrontFaqCategory(BaseModel):
    id: UUID
    name: str
    faqs: list[StorefrontFaq]


class StorefrontBlogSummary(BaseModel):
    slug: str
    title: str
    excerpt: str | None
    featured_image_url: str | None
    author_name: str | None
    category: str | None
    tags: list[str]
    published_at: datetime | None


class StorefrontBlogPost(StorefrontBlogSummary):
    content: str
    content_format: str = "markdown"
    seo_title: str | None
    seo_description: str | None


class StorefrontBlogQuery(PageParams):
    tag: str | None = Field(default=None, max_length=40)
    category: str | None = Field(default=None, max_length=100)


# ------------------------------------------------------------- site settings

MAX_SOCIAL_URL_LENGTH = 500
SOCIAL_NETWORKS = ("instagram", "facebook", "x", "youtube", "pinterest", "tiktok", "linkedin")


class SiteSettingsUpdate(StrictModel):
    """Everything is optional; a blank field is shown as nothing on the website."""

    logo_url: str | None = Field(default=None, max_length=2048)
    logo_alt: str | None = Field(default=None, max_length=255)
    tagline: str | None = Field(default=None, max_length=500)
    contact_email: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=30)
    whatsapp_number: str | None = Field(default=None, max_length=30)
    address: str | None = Field(default=None, max_length=500)
    social_links: dict[str, str] = Field(default_factory=dict)
    copyright_text: str | None = Field(default=None, max_length=255)

    _logo = field_validator("logo_url")(_image)

    @field_validator(
        "logo_alt", "tagline", "contact_email", "contact_phone", "whatsapp_number", "address",
        "copyright_text",
    )
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @field_validator("contact_email")
    @classmethod
    def _email(cls, value: str | None) -> str | None:
        if value and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("must be an email address")
        return value

    @field_validator("contact_phone", "whatsapp_number")
    @classmethod
    def _phone(cls, value: str | None) -> str | None:
        if value and not re.fullmatch(r"\+?[0-9][0-9 ()-]{5,}", value):
            raise ValueError("must be a phone number (digits, spaces, + - ( ))")
        return value

    @field_validator("social_links")
    @classmethod
    def _socials(cls, value: dict[str, str]) -> dict[str, str]:
        cleaned: dict[str, str] = {}
        for network, url in value.items():
            if network not in SOCIAL_NETWORKS:
                raise ValueError(f"unknown network '{network}' (use: {', '.join(SOCIAL_NETWORKS)})")
            url = (url or "").strip()
            if not url:
                continue
            if not re.match(r"^https://[^\s]+$", url):
                raise ValueError(f"{network}: must be an https:// link")
            if len(url) > MAX_SOCIAL_URL_LENGTH:
                raise ValueError(f"{network}: link is too long ({MAX_SOCIAL_URL_LENGTH} max)")
            cleaned[network] = url
        return cleaned


class SiteSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    logo_url: str | None = None
    logo_alt: str | None = None
    tagline: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    whatsapp_number: str | None = None
    address: str | None = None
    social_links: dict[str, str] = Field(default_factory=dict)
    copyright_text: str | None = None
    updated_at: datetime | None = None


class StorefrontSite(BaseModel):
    logo_url: str | None = None
    logo_alt: str | None = None
    tagline: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    whatsapp_number: str | None = None
    address: str | None = None
    social_links: dict[str, str] = Field(default_factory=dict)
    copyright_text: str | None = None
