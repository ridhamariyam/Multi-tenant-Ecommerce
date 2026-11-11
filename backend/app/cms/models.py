"""Store content: homepage sections, pages, FAQs, navigation, blog, media.

Every row belongs to one tenant; editors are recorded on the row and every
change also lands in the admin activity log.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.cms.constants import (
    MAX_SLUG_LENGTH,
    MAX_TITLE_LENGTH,
    ContentStatus,
    LinkType,
    MenuLocation,
    PageType,
    SectionType,
)
from app.models.base import Base, IdMixin, TenantMixin, TimestampMixin


def _values(enum) -> str:
    return ", ".join(f"'{member.value}'" for member in enum)


def _editors(table: str):
    """created_by / updated_by -> users, kept if the account is erased later."""
    return (
        ForeignKeyConstraint(
            ["tenant_id", "created_by_id"],
            ["users.tenant_id", "users.id"],
            name=f"fk_{table}_tenant_created_by_users",
            ondelete="SET NULL (created_by_id)",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "updated_by_id"],
            ["users.tenant_id", "users.id"],
            name=f"fk_{table}_tenant_updated_by_users",
            ondelete="SET NULL (updated_by_id)",
        ),
    )


class _Edited:
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class _Published:
    status: Mapped[str] = mapped_column(
        String(10), nullable=False, default=ContentStatus.DRAFT.value
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class CmsMedia(IdMixin, TenantMixin, TimestampMixin, Base):
    """An uploaded image. The file lives in app storage; the row holds its URL."""

    __tablename__ = "cms_media"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "uploaded_by_id"],
            ["users.tenant_id", "users.id"],
            name="fk_cms_media_tenant_uploaded_by_users",
            ondelete="SET NULL (uploaded_by_id)",
        ),
        Index("ix_cms_media_tenant_id_created_at", "tenant_id", "created_at"),
    )

    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    alt_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class HomeSection(IdMixin, TenantMixin, _Edited, TimestampMixin, Base):
    """One block on the homepage: banners, a promo strip or a product shelf."""

    __tablename__ = "cms_home_sections"
    __table_args__ = (
        *_editors("cms_home_sections"),
        CheckConstraint(f"section_type IN ({_values(SectionType)})", name="section_type_valid"),
        CheckConstraint("position >= 0", name="position_not_negative"),
        CheckConstraint(
            "starts_at IS NULL OR ends_at IS NULL OR starts_at < ends_at", name="window_ordered"
        ),
        Index("ix_cms_home_sections_tenant_id_position", "tenant_id", "position"),
    )

    section_type: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str | None] = mapped_column(String(MAX_TITLE_LENGTH), nullable=True)
    subtitle: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Banners: [{"image_url", "mobile_image_url", "heading", "text", "link_url", "cta_label"}]
    items: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Shelf rules: {"product_ids": [...], "category_id", "limit", "days", "countdown_ends_at"}
    settings: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class ContentPage(IdMixin, TenantMixin, _Edited, _Published, TimestampMixin, Base):
    """A static page (About, policies, contact...). Body is Markdown."""

    __tablename__ = "cms_pages"
    __table_args__ = (
        *_editors("cms_pages"),
        UniqueConstraint("tenant_id", "slug", name="uq_cms_pages_tenant_slug"),
        CheckConstraint(f"page_type IN ({_values(PageType)})", name="page_type_valid"),
        CheckConstraint(f"status IN ({_values(ContentStatus)})", name="status_valid"),
    )

    slug: Mapped[str] = mapped_column(String(MAX_SLUG_LENGTH), nullable=False)
    title: Mapped[str] = mapped_column(String(MAX_TITLE_LENGTH), nullable=False)
    page_type: Mapped[str] = mapped_column(String(20), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    seo_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    seo_description: Mapped[str | None] = mapped_column(String(500), nullable=True)


class FaqCategory(IdMixin, TenantMixin, _Edited, TimestampMixin, Base):
    __tablename__ = "cms_faq_categories"
    __table_args__ = (
        *_editors("cms_faq_categories"),
        UniqueConstraint("tenant_id", "id", name="uq_cms_faq_categories_tenant_id_id"),
        CheckConstraint("position >= 0", name="position_not_negative"),
    )

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Faq(IdMixin, TenantMixin, _Edited, _Published, TimestampMixin, Base):
    __tablename__ = "cms_faqs"
    __table_args__ = (
        *_editors("cms_faqs"),
        ForeignKeyConstraint(
            ["tenant_id", "category_id"],
            ["cms_faq_categories.tenant_id", "cms_faq_categories.id"],
            name="fk_cms_faqs_tenant_category_cms_faq_categories",
            ondelete="CASCADE",
        ),
        CheckConstraint(f"status IN ({_values(ContentStatus)})", name="status_valid"),
        CheckConstraint("position >= 0", name="position_not_negative"),
        Index("ix_cms_faqs_tenant_id_category_id", "tenant_id", "category_id"),
    )

    category_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    question: Mapped[str] = mapped_column(String(500), nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class NavigationItem(IdMixin, TenantMixin, _Edited, TimestampMixin, Base):
    __tablename__ = "cms_navigation_items"
    __table_args__ = (
        *_editors("cms_navigation_items"),
        UniqueConstraint("tenant_id", "id", name="uq_cms_navigation_items_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "parent_id"],
            ["cms_navigation_items.tenant_id", "cms_navigation_items.id"],
            name="fk_cms_navigation_items_tenant_parent",
            ondelete="CASCADE",
        ),
        CheckConstraint(f"menu IN ({_values(MenuLocation)})", name="menu_valid"),
        CheckConstraint(f"link_type IN ({_values(LinkType)})", name="link_type_valid"),
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="parent_not_self"),
        CheckConstraint("position >= 0", name="position_not_negative"),
        Index("ix_cms_navigation_items_tenant_id_menu", "tenant_id", "menu", "position"),
    )

    menu: Mapped[str] = mapped_column(String(10), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    link_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # URL for URL links; an id or slug for the others; empty for HOME/BLOG_INDEX/FAQ.
    target: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    open_in_new_tab: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class BlogPost(IdMixin, TenantMixin, _Edited, _Published, TimestampMixin, Base):
    """An article. Body is Markdown."""

    __tablename__ = "cms_blog_posts"
    __table_args__ = (
        *_editors("cms_blog_posts"),
        UniqueConstraint("tenant_id", "slug", name="uq_cms_blog_posts_tenant_slug"),
        CheckConstraint(f"status IN ({_values(ContentStatus)})", name="status_valid"),
        Index("ix_cms_blog_posts_tenant_id_published_at", "tenant_id", "status", "published_at"),
    )

    slug: Mapped[str] = mapped_column(String(MAX_SLUG_LENGTH), nullable=False)
    title: Mapped[str] = mapped_column(String(MAX_TITLE_LENGTH), nullable=False)
    excerpt: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    featured_image_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    author_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    seo_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    seo_description: Mapped[str | None] = mapped_column(String(500), nullable=True)


class SiteSettings(IdMixin, TenantMixin, TimestampMixin, Base):
    """Website-wide content the store manages itself: logo, tagline, contact
    details and social links. One row per store; absent until first saved."""

    __tablename__ = "cms_site_settings"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_cms_site_settings_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "updated_by_id"],
            ["users.tenant_id", "users.id"],
            name="fk_cms_site_settings_tenant_updated_by_users",
            ondelete="SET NULL (updated_by_id)",
        ),
    )

    logo_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    logo_alt: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tagline: Mapped[str | None] = mapped_column(String(500), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    whatsapp_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # {"instagram": "https://...", "facebook": ..., "x": ..., "youtube": ..., ...}
    social_links: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    copyright_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
