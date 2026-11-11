"""CMS logic: editing, publishing and what the storefront may show."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import Text, and_, cast, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalogue.constants import CatalogueStatus
from app.catalogue.models import Category, Product
from app.catalogue.repository import category_subtree
from app.catalogue.uploads import store_image
from app.cms.constants import PRODUCT_SECTIONS, ContentStatus, LinkType, SectionType
from app.cms.models import (
    BlogPost,
    CmsMedia,
    ContentPage,
    Faq,
    FaqCategory,
    HomeSection,
    NavigationItem,
    SiteSettings,
)
from app.cms.schemas import _link, slugify
from app.core.database import conflict_on_integrity_error
from app.core.error_codes import CommonErrorCode, ContentErrorCode, ProductErrorCode
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.orders.constants import OrderStatus
from app.orders.models import Order, OrderItem
from app.users.models import User


def now() -> datetime:
    return datetime.now(timezone.utc)


def is_live(item, at: datetime | None = None) -> bool:
    """Published, and its publish time (if scheduled) has come."""
    moment = at or now()
    return (
        item.status == ContentStatus.PUBLISHED.value
        and item.published_at is not None
        and item.published_at <= moment
    )


def section_is_live(section: HomeSection, at: datetime | None = None) -> bool:
    moment = at or now()
    return (
        section.is_active
        and (section.starts_at is None or section.starts_at <= moment)
        and (section.ends_at is None or section.ends_at > moment)
    )


def _live_clause(model):
    return and_(
        model.status == ContentStatus.PUBLISHED.value,
        model.published_at.isnot(None),
        model.published_at <= func.now(),
    )


def href_for(link_type: str, target: str | None) -> str:
    return {
        LinkType.HOME.value: "/",
        LinkType.BLOG_INDEX.value: "/blog",
        LinkType.FAQ.value: "/faq",
        LinkType.CATEGORY.value: f"/categories/{target}",
        LinkType.PRODUCT.value: f"/products/{target}",
        LinkType.PAGE.value: f"/pages/{target}",
        LinkType.BLOG_POST.value: f"/blog/{target}",
    }.get(link_type, target or "/")


class CmsService:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id

    # ------------------------------------------------------------- helpers

    async def _get(self, model, entity_id: UUID, label: str):
        row = await self.session.scalar(
            select(model).where(model.tenant_id == self.tenant_id, model.id == entity_id)
        )
        if row is None:
            raise NotFoundError(f"{label} not found")
        return row

    async def _paginate(self, stmt, params):
        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = await self.session.scalars(stmt.offset(params.offset).limit(params.limit))
        return list(rows.all()), int(total or 0)

    async def _commit(self, conflict_message: str) -> None:
        async with conflict_on_integrity_error(self.session, conflict_message):
            await self.session.commit()

    async def _next_position(self, model, *conditions) -> int:
        current = await self.session.scalar(
            select(func.max(model.position)).where(model.tenant_id == self.tenant_id, *conditions)
        )
        return 0 if current is None else current + 1

    async def _reorder(self, model, ids: list[UUID], *conditions) -> None:
        """Put `ids` first, in that order; rows not listed keep their order after them."""
        query = select(model).where(model.tenant_id == self.tenant_id, *conditions)
        rows = (await self.session.scalars(query)).all()
        by_id = {row.id: row for row in rows}

        unknown = [str(i) for i in ids if i not in by_id]
        if unknown:
            raise NotFoundError("Unknown id(s): " + ", ".join(unknown[:5]))
        if len(set(ids)) != len(ids):
            raise ValidationError("Each id may only appear once")

        listed = [by_id[i] for i in ids]
        rest = sorted((row for row in rows if row.id not in ids), key=lambda row: row.position)
        for position, row in enumerate(listed + rest):
            row.position = position
        await self.session.commit()

    async def _check_slug(self, model, slug: str, own_id: UUID | None = None) -> None:
        """A slug is used once per store; an item being edited may keep its own."""
        taken = await self.session.scalar(
            select(model.id).where(
                model.tenant_id == self.tenant_id, model.slug == slug, model.id != own_id
            )
        )
        if taken is not None:
            raise ConflictError(
                f"The slug '{slug}' is already used", error_code=CommonErrorCode.SLUG_TAKEN
            )

    # --------------------------------------------------------------- media

    async def list_media(self, params, search: str | None = None):
        stmt = select(CmsMedia).where(CmsMedia.tenant_id == self.tenant_id)
        if search:
            term = f"%{search.strip()}%"
            stmt = stmt.where(or_(CmsMedia.filename.ilike(term), CmsMedia.alt_text.ilike(term)))
        return await self._paginate(stmt.order_by(desc(CmsMedia.created_at)), params)

    async def upload_media(
        self, *, filename: str, content_type: str, data: bytes, alt_text: str | None, user: User
    ) -> CmsMedia:
        # Same validation and original-byte storage as product images:
        # JPEG/PNG/WebP, size-capped, with files outside the database.
        url = await store_image(self.tenant_id, content_type, data)
        media = CmsMedia(
            tenant_id=self.tenant_id,
            url=url,
            filename=(filename or "upload")[:255],
            content_type=content_type,
            size_bytes=len(data),
            alt_text=alt_text,
            uploaded_by_id=user.id,
        )
        self.session.add(media)
        await self.session.commit()
        await self.session.refresh(media)
        return media

    async def update_media(self, media_id: UUID, alt_text: str | None) -> CmsMedia:
        media = await self._get(CmsMedia, media_id, "Media")
        media.alt_text = alt_text
        await self.session.commit()
        await self.session.refresh(media)
        return media

    async def media_in_use(self, url: str) -> bool:
        """Whether a section, page or article still points at this file."""
        needle = f"%{url}%"
        in_sections = await self.session.scalar(
            select(func.count(HomeSection.id)).where(
                HomeSection.tenant_id == self.tenant_id,
                cast(HomeSection.items, Text).like(needle),
            )
        )
        in_posts = await self.session.scalar(
            select(func.count(BlogPost.id)).where(
                BlogPost.tenant_id == self.tenant_id,
                or_(BlogPost.featured_image_url == url, BlogPost.content.like(needle)),
            )
        )
        in_pages = await self.session.scalar(
            select(func.count(ContentPage.id)).where(
                ContentPage.tenant_id == self.tenant_id, ContentPage.body.like(needle)
            )
        )
        in_site = await self.session.scalar(
            select(func.count(SiteSettings.id)).where(
                SiteSettings.tenant_id == self.tenant_id, SiteSettings.logo_url == url
            )
        )
        return bool(in_sections or in_posts or in_pages or in_site)

    async def delete_media(self, media_id: UUID) -> None:
        media = await self._get(CmsMedia, media_id, "Media")
        if await self.media_in_use(media.url):
            raise ConflictError(
                "This image is used by a homepage section, page, article or the site logo",
                error_code=ContentErrorCode.MEDIA_IN_USE,
            )
        await self.session.delete(media)
        await self.session.commit()

    # ------------------------------------------------------------ sections

    async def _check_settings(self, section_type: str, settings: dict | None) -> None:
        if not settings:
            return
        for product_id in settings.get("product_ids") or []:
            exists = await self.session.scalar(
                select(Product.id).where(
                    Product.tenant_id == self.tenant_id, Product.id == product_id
                )
            )
            if exists is None:
                raise NotFoundError(f"Product {product_id} not found")
        if settings.get("category_id"):
            exists = await self.session.scalar(
                select(Category.id).where(
                    Category.tenant_id == self.tenant_id, Category.id == settings["category_id"]
                )
            )
            if exists is None:
                raise NotFoundError(
                    "Category not found",
                    error_code=ProductErrorCode.CATEGORY_NOT_FOUND,
                )

    @staticmethod
    def _check_items(section_type: str, items: list | None) -> None:
        """A hero banner needs at least one slide, and every slide needs an image."""
        if section_type != SectionType.HERO_BANNER.value:
            return
        slides = items or []
        if not slides:
            raise ValidationError("A hero banner needs at least one slide with an image")
        for number, slide in enumerate(slides, start=1):
            if not (slide or {}).get("image_url"):
                raise ValidationError(
                    f"Slide {number} needs an image", error_code=ContentErrorCode.IMAGE_REQUIRED
                )

    async def list_sections(self) -> list[HomeSection]:
        rows = await self.session.scalars(
            select(HomeSection)
            .where(HomeSection.tenant_id == self.tenant_id)
            .order_by(HomeSection.position, HomeSection.created_at)
        )
        return list(rows.all())

    async def get_section(self, section_id: UUID) -> HomeSection:
        return await self._get(HomeSection, section_id, "Section")

    async def create_section(self, data, user: User) -> HomeSection:
        values = data.model_dump(mode="json")
        self._check_items(data.section_type.value, values.get("items"))
        await self._check_settings(data.section_type.value, values.get("settings"))
        section = HomeSection(
            tenant_id=self.tenant_id,
            section_type=data.section_type.value,
            title=data.title,
            subtitle=data.subtitle,
            is_active=data.is_active,
            starts_at=data.starts_at,
            ends_at=data.ends_at,
            items=values.get("items") or [],
            settings=values.get("settings") or {},
            position=await self._next_position(HomeSection),
            created_by_id=user.id,
            updated_by_id=user.id,
        )
        self.session.add(section)
        await self._commit("Unable to save the section")
        await self.session.refresh(section)
        return section

    async def update_section(self, section_id: UUID, data, user: User) -> HomeSection:
        section = await self.get_section(section_id)
        changes = data.model_dump(exclude_unset=True)
        # items and settings are stored as JSON, so they are taken in JSON form.
        stored = data.model_dump(exclude_unset=True, mode="json")
        if "items" in changes:
            self._check_items(section.section_type, stored["items"])
            changes["items"] = stored["items"] or []
        if "settings" in changes:
            await self._check_settings(section.section_type, stored["settings"])
            changes["settings"] = stored["settings"] or {}
        for field, value in changes.items():
            setattr(section, field, value)
        if section.starts_at and section.ends_at and section.starts_at >= section.ends_at:
            raise ValidationError("starts_at must be before ends_at")
        section.updated_by_id = user.id
        await self._commit("Unable to save the section")
        await self.session.refresh(section)
        return section

    async def delete_section(self, section_id: UUID) -> None:
        await self.session.delete(await self.get_section(section_id))
        await self.session.commit()

    async def reorder_sections(self, ids: list[UUID]) -> list[HomeSection]:
        await self._reorder(HomeSection, ids)
        return await self.list_sections()

    # --------------------------------------------------------- site settings

    async def get_site(self) -> SiteSettings | None:
        return await self.session.scalar(
            select(SiteSettings).where(SiteSettings.tenant_id == self.tenant_id)
        )

    async def update_site(self, data, user: User) -> SiteSettings:
        site = await self.get_site()
        if site is None:
            site = SiteSettings(tenant_id=self.tenant_id)
            self.session.add(site)
        for field, value in data.model_dump().items():
            setattr(site, field, value)
        site.updated_by_id = user.id
        # Two first saves at once both insert; the second hits the one-per-store rule.
        await self._commit("Unable to save the site settings, please try again")
        await self.session.refresh(site)
        return site

    # --------------------------------------------------------------- pages

    async def list_pages(self, params, status=None, search=None):
        stmt = select(ContentPage).where(ContentPage.tenant_id == self.tenant_id)
        if status:
            stmt = stmt.where(ContentPage.status == status.value)
        if search:
            stmt = stmt.where(ContentPage.title.ilike(f"%{search.strip()}%"))
        return await self._paginate(stmt.order_by(ContentPage.title), params)

    async def get_page(self, page_id: UUID) -> ContentPage:
        return await self._get(ContentPage, page_id, "Page")

    async def create_page(self, data, user: User) -> ContentPage:
        slug = data.slug or slugify(data.title)
        await self._check_slug(ContentPage, slug)
        page = ContentPage(
            tenant_id=self.tenant_id,
            slug=slug,
            title=data.title.strip(),
            page_type=data.page_type.value,
            body=data.body,
            seo_title=data.seo_title,
            seo_description=data.seo_description,
            status=ContentStatus.DRAFT.value,
            created_by_id=user.id,
            updated_by_id=user.id,
        )
        self.session.add(page)
        await self._commit("A page with this slug already exists")
        await self.session.refresh(page)
        return page

    async def update_page(self, page_id: UUID, data, user: User) -> ContentPage:
        page = await self.get_page(page_id)
        changes = data.model_dump(exclude_unset=True)
        if not changes.get("slug"):
            changes.pop("slug", None)  # a blank slug keeps the current one
        else:
            await self._check_slug(ContentPage, changes["slug"], page.id)
        if changes.get("page_type") is not None:
            changes["page_type"] = changes["page_type"].value
        for field, value in changes.items():
            setattr(page, field, value)
        page.updated_by_id = user.id
        await self._commit("A page with this slug already exists")
        await self.session.refresh(page)
        return page

    async def delete_page(self, page_id: UUID) -> None:
        await self.session.delete(await self.get_page(page_id))
        await self.session.commit()

    async def publish(self, model, entity_id: UUID, label: str, user: User, publish_at=None):
        item = await self._get(model, entity_id, label)
        item.status = ContentStatus.PUBLISHED.value
        item.published_at = publish_at or now()
        item.published_by_id = user.id
        item.updated_by_id = user.id
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def unpublish(self, model, entity_id: UUID, label: str, user: User):
        item = await self._get(model, entity_id, label)
        item.status = ContentStatus.DRAFT.value
        item.updated_by_id = user.id
        await self.session.commit()
        await self.session.refresh(item)
        return item

    # ---------------------------------------------------------------- FAQs

    async def list_faq_categories(self) -> list[FaqCategory]:
        rows = await self.session.scalars(
            select(FaqCategory)
            .where(FaqCategory.tenant_id == self.tenant_id)
            .order_by(FaqCategory.position, FaqCategory.name)
        )
        return list(rows.all())

    async def create_faq_category(self, data, user: User) -> FaqCategory:
        category = FaqCategory(
            tenant_id=self.tenant_id,
            name=data.name.strip(),
            is_active=data.is_active,
            position=await self._next_position(FaqCategory),
            created_by_id=user.id,
            updated_by_id=user.id,
        )
        self.session.add(category)
        await self.session.commit()
        await self.session.refresh(category)
        return category

    async def update_faq_category(self, category_id: UUID, data, user: User) -> FaqCategory:
        category = await self._get(FaqCategory, category_id, "FAQ category")
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(category, field, value.strip() if isinstance(value, str) else value)
        category.updated_by_id = user.id
        await self.session.commit()
        await self.session.refresh(category)
        return category

    async def delete_faq_category(self, category_id: UUID) -> None:
        await self.session.delete(await self._get(FaqCategory, category_id, "FAQ category"))
        await self.session.commit()

    async def reorder_faq_categories(self, ids: list[UUID]) -> list[FaqCategory]:
        await self._reorder(FaqCategory, ids)
        return await self.list_faq_categories()

    async def list_faqs(self, category_id: UUID | None = None) -> list[Faq]:
        stmt = select(Faq).where(Faq.tenant_id == self.tenant_id)
        if category_id:
            stmt = stmt.where(Faq.category_id == category_id)
        rows = await self.session.scalars(stmt.order_by(Faq.category_id, Faq.position))
        return list(rows.all())

    async def create_faq(self, data, user: User) -> Faq:
        await self._get(FaqCategory, data.category_id, "FAQ category")
        faq = Faq(
            tenant_id=self.tenant_id,
            category_id=data.category_id,
            question=data.question.strip(),
            answer=data.answer,
            position=await self._next_position(Faq, Faq.category_id == data.category_id),
            status=ContentStatus.DRAFT.value,
            created_by_id=user.id,
            updated_by_id=user.id,
        )
        self.session.add(faq)
        await self.session.commit()
        await self.session.refresh(faq)
        return faq

    async def update_faq(self, faq_id: UUID, data, user: User) -> Faq:
        faq = await self._get(Faq, faq_id, "FAQ")
        changes = data.model_dump(exclude_unset=True)
        if changes.get("category_id") and changes["category_id"] != faq.category_id:
            await self._get(FaqCategory, changes["category_id"], "FAQ category")
            faq.position = await self._next_position(Faq, Faq.category_id == changes["category_id"])
        for field, value in changes.items():
            setattr(faq, field, value)
        faq.updated_by_id = user.id
        await self.session.commit()
        await self.session.refresh(faq)
        return faq

    async def delete_faq(self, faq_id: UUID) -> None:
        await self.session.delete(await self._get(Faq, faq_id, "FAQ"))
        await self.session.commit()

    async def reorder_faqs(self, category_id: UUID, ids: list[UUID]) -> list[Faq]:
        await self._get(FaqCategory, category_id, "FAQ category")
        await self._reorder(Faq, ids, Faq.category_id == category_id)
        return await self.list_faqs(category_id)

    # ---------------------------------------------------------- navigation

    async def _check_target(self, link_type: str, target: str | None) -> str | None:
        kind = LinkType(link_type)
        if kind in {LinkType.HOME, LinkType.BLOG_INDEX, LinkType.FAQ}:
            return None
        if not target or not target.strip():
            raise ValidationError(f"A {kind.value} link needs a target")
        target = target.strip()
        if kind is LinkType.URL:
            try:
                return _link(target)
            except ValueError as exc:
                raise ValidationError(f"Link {exc}") from exc
        if kind in {LinkType.CATEGORY, LinkType.PRODUCT}:
            try:
                target_id = UUID(target)
            except ValueError as exc:
                raise ValidationError("The target must be an id") from exc
            model = Category if kind is LinkType.CATEGORY else Product
            found = await self.session.scalar(
                select(model.id).where(model.tenant_id == self.tenant_id, model.id == target_id)
            )
            if found is None:
                raise NotFoundError(f"{kind.value.title()} not found")
            return str(target_id)
        model = ContentPage if kind is LinkType.PAGE else BlogPost
        found = await self.session.scalar(
            select(model.id).where(model.tenant_id == self.tenant_id, model.slug == target)
        )
        if found is None:
            raise NotFoundError(f"No {'page' if kind is LinkType.PAGE else 'article'} '{target}'")
        return target

    async def _check_parent(self, parent_id: UUID | None, menu: str, self_id=None) -> None:
        if parent_id is None:
            return
        parent = await self._get(NavigationItem, parent_id, "Parent menu item")
        if parent.menu != menu:
            raise ValidationError("The parent item belongs to a different menu")
        if parent.parent_id is not None:
            raise ValidationError("Menus nest one level deep")
        if self_id is not None and parent.id == self_id:
            raise ValidationError("A menu item cannot be its own parent")

    async def list_navigation(self, menu: str | None = None) -> list[NavigationItem]:
        stmt = select(NavigationItem).where(NavigationItem.tenant_id == self.tenant_id)
        if menu:
            stmt = stmt.where(NavigationItem.menu == menu)
        rows = await self.session.scalars(
            stmt.order_by(NavigationItem.menu, NavigationItem.position, NavigationItem.created_at)
        )
        return list(rows.all())

    async def create_navigation(self, data, user: User) -> NavigationItem:
        target = await self._check_target(data.link_type.value, data.target)
        await self._check_parent(data.parent_id, data.menu.value)
        item = NavigationItem(
            tenant_id=self.tenant_id,
            menu=data.menu.value,
            label=data.label.strip(),
            link_type=data.link_type.value,
            target=target,
            parent_id=data.parent_id,
            is_active=data.is_active,
            open_in_new_tab=data.open_in_new_tab,
            position=await self._next_position(
                NavigationItem,
                NavigationItem.menu == data.menu.value,
                NavigationItem.parent_id.is_(None)
                if data.parent_id is None
                else NavigationItem.parent_id == data.parent_id,
            ),
            created_by_id=user.id,
            updated_by_id=user.id,
        )
        self.session.add(item)
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def update_navigation(self, item_id: UUID, data, user: User) -> NavigationItem:
        item = await self._get(NavigationItem, item_id, "Menu item")
        changes = data.model_dump(exclude_unset=True)
        link_type = changes.get("link_type") or LinkType(item.link_type)
        if "link_type" in changes or "target" in changes:
            item.target = await self._check_target(
                link_type.value, changes.get("target", item.target)
            )
            item.link_type = link_type.value
        if "parent_id" in changes:
            await self._check_parent(changes["parent_id"], item.menu, item.id)
            if changes["parent_id"] is not None:
                children = await self.session.scalar(
                    select(func.count(NavigationItem.id)).where(
                        NavigationItem.tenant_id == self.tenant_id,
                        NavigationItem.parent_id == item.id,
                    )
                )
                if children:
                    raise ValidationError("An item with sub-items cannot become a sub-item")
            item.parent_id = changes["parent_id"]
        for field in ("label", "is_active", "open_in_new_tab"):
            if field in changes and changes[field] is not None:
                setattr(item, field, changes[field])
        item.updated_by_id = user.id
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def delete_navigation(self, item_id: UUID) -> None:
        await self.session.delete(await self._get(NavigationItem, item_id, "Menu item"))
        await self.session.commit()

    async def reorder_navigation(self, menu: str, ids: list[UUID]) -> list[NavigationItem]:
        await self._reorder(NavigationItem, ids, NavigationItem.menu == menu)
        return await self.list_navigation(menu)

    # ---------------------------------------------------------------- blog

    async def list_posts(self, params, status=None, search=None, tag=None, category=None):
        stmt = select(BlogPost).where(BlogPost.tenant_id == self.tenant_id)
        if status:
            stmt = stmt.where(BlogPost.status == status.value)
        if search:
            stmt = stmt.where(BlogPost.title.ilike(f"%{search.strip()}%"))
        if tag:
            stmt = stmt.where(BlogPost.tags.contains([tag]))
        if category:
            stmt = stmt.where(BlogPost.category == category)
        return await self._paginate(
            stmt.order_by(desc(BlogPost.published_at).nulls_first(), desc(BlogPost.created_at)),
            params,
        )

    async def get_post(self, post_id: UUID) -> BlogPost:
        return await self._get(BlogPost, post_id, "Article")

    async def create_post(self, data, user: User) -> BlogPost:
        slug = data.slug or slugify(data.title)
        await self._check_slug(BlogPost, slug)
        post = BlogPost(
            tenant_id=self.tenant_id,
            slug=slug,
            title=data.title.strip(),
            excerpt=data.excerpt,
            content=data.content,
            featured_image_url=data.featured_image_url,
            author_name=data.author_name or user.name,
            category=data.category,
            tags=data.tags,
            seo_title=data.seo_title,
            seo_description=data.seo_description,
            status=ContentStatus.DRAFT.value,
            created_by_id=user.id,
            updated_by_id=user.id,
        )
        self.session.add(post)
        await self._commit("An article with this slug already exists")
        await self.session.refresh(post)
        return post

    async def update_post(self, post_id: UUID, data, user: User) -> BlogPost:
        post = await self.get_post(post_id)
        changes = data.model_dump(exclude_unset=True)
        if not changes.get("slug"):
            changes.pop("slug", None)  # a blank slug keeps the current one
        else:
            await self._check_slug(BlogPost, changes["slug"], post.id)
        for field, value in changes.items():
            setattr(post, field, [] if field == "tags" and value is None else value)
        post.updated_by_id = user.id
        await self._commit("An article with this slug already exists")
        await self.session.refresh(post)
        return post

    async def delete_post(self, post_id: UUID) -> None:
        await self.session.delete(await self.get_post(post_id))
        await self.session.commit()

    # ---------------------------------------------------------- storefront

    async def live_sections(self) -> list[HomeSection]:
        return [s for s in await self.list_sections() if section_is_live(s)]

    async def section_products(self, section: HomeSection) -> list[Product]:
        """The products a shelf shows, live ones only, in display order."""
        if SectionType(section.section_type) not in PRODUCT_SECTIONS:
            return []
        settings = section.settings or {}
        limit = int(settings.get("limit") or 8)
        live = and_(
            Product.tenant_id == self.tenant_id,
            Product.status == CatalogueStatus.ACTIVE.value,
            Category.status == CatalogueStatus.ACTIVE.value,
        )
        base = select(Product).join(
            Category,
            and_(Category.tenant_id == Product.tenant_id, Category.id == Product.category_id),
        )
        category_id = settings.get("category_id")
        if category_id:
            base = base.where(
                Product.category_id.in_(category_subtree(self.tenant_id, UUID(str(category_id))))
            )

        picked = [UUID(str(pid)) for pid in settings.get("product_ids") or []]
        kind = SectionType(section.section_type)
        if picked:
            rows = (await self.session.scalars(base.where(live, Product.id.in_(picked)))).all()
            by_id = {p.id: p for p in rows}
            return [by_id[pid] for pid in picked if pid in by_id][:limit]

        if kind is SectionType.BESTSELLERS:
            since = now() - timedelta(days=int(settings.get("days") or 30))
            sold = (
                select(OrderItem.product_id, func.sum(OrderItem.quantity).label("units"))
                .join(
                    Order,
                    and_(Order.tenant_id == OrderItem.tenant_id, Order.id == OrderItem.order_id),
                )
                .where(
                    OrderItem.tenant_id == self.tenant_id,
                    Order.status != OrderStatus.CANCELLED.value,
                    Order.created_at >= since,
                )
                .group_by(OrderItem.product_id)
                .subquery()
            )
            stmt = (
                base.join(sold, sold.c.product_id == Product.id)
                .where(live)
                .order_by(desc(sold.c.units), Product.id)
            )
        elif kind is SectionType.FEATURED_PRODUCTS:
            stmt = base.where(live, Product.is_featured.is_(True)).order_by(
                desc(Product.created_at)
            )
        elif kind is SectionType.SEASONAL and not category_id:
            return []  # a seasonal shelf needs chosen products or a category
        else:  # NEW_ARRIVALS, or SEASONAL by category
            stmt = base.where(live).order_by(desc(Product.created_at), Product.id)
        return list((await self.session.scalars(stmt.limit(limit))).all())

    async def live_page(self, slug: str) -> ContentPage:
        page = await self.session.scalar(
            select(ContentPage).where(
                ContentPage.tenant_id == self.tenant_id,
                ContentPage.slug == slug,
                _live_clause(ContentPage),
            )
        )
        if page is None:
            raise NotFoundError("Page not found")
        return page

    async def live_faqs(self) -> list[tuple[FaqCategory, list[Faq]]]:
        categories = [c for c in await self.list_faq_categories() if c.is_active]
        faqs = (
            await self.session.scalars(
                select(Faq)
                .where(Faq.tenant_id == self.tenant_id, _live_clause(Faq))
                .order_by(Faq.position)
            )
        ).all()
        grouped = [(c, [f for f in faqs if f.category_id == c.id]) for c in categories]
        return [(c, items) for c, items in grouped if items]

    async def live_posts(self, params, tag=None, category=None):
        stmt = select(BlogPost).where(BlogPost.tenant_id == self.tenant_id, _live_clause(BlogPost))
        if tag:
            stmt = stmt.where(BlogPost.tags.contains([tag]))
        if category:
            stmt = stmt.where(BlogPost.category == category)
        return await self._paginate(stmt.order_by(desc(BlogPost.published_at)), params)

    async def live_post(self, slug: str) -> BlogPost:
        post = await self.session.scalar(
            select(BlogPost).where(
                BlogPost.tenant_id == self.tenant_id,
                BlogPost.slug == slug,
                _live_clause(BlogPost),
            )
        )
        if post is None:
            raise NotFoundError("Article not found")
        return post
