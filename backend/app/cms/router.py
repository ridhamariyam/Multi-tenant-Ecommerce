"""Admin CMS endpoints. Viewing needs cms.view, editing cms.manage, and
publishing (or switching a section/menu item on) cms.publish. Every change
is written to the activity log automatically."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.dependencies import AUDITED
from app.auth.dependencies import require_permission
from app.auth.permissions import Permission, has_permission
from app.catalogue.serializers import storefront_summary
from app.cms.constants import MenuLocation
from app.cms.models import BlogPost, ContentPage, Faq
from app.cms.schemas import (
    BannerItem,
    BlogCreate,
    BlogQuery,
    BlogRead,
    BlogSummary,
    BlogUpdate,
    ContentQuery,
    FaqCategoryRead,
    FaqCategoryUpdate,
    FaqCategoryWrite,
    FaqCreate,
    FaqRead,
    FaqUpdate,
    MediaQuery,
    MediaRead,
    MediaUpdate,
    NavigationCreate,
    NavigationRead,
    NavigationUpdate,
    PageCreate,
    PageRead,
    PageSummary,
    PageUpdate,
    PublishRequest,
    ReorderRequest,
    SectionCreate,
    SectionRead,
    SectionUpdate,
    SiteSettingsRead,
    SiteSettingsUpdate,
    StorefrontBlogPost,
    StorefrontBlogQuery,
    StorefrontBlogSummary,
    StorefrontFaq,
    StorefrontFaqCategory,
    StorefrontPage,
    StorefrontSection,
    StorefrontSite,
)
from app.cms.serializers import (
    blog_read,
    blog_summary,
    faq_read,
    navigation_read,
    navigation_tree,
    page_read,
    page_summary,
    section_read,
    storefront_page,
    storefront_post,
    storefront_post_summary,
)
from app.cms.service import CmsService
from app.core.database import get_db
from app.core.exceptions import PermissionDeniedError
from app.core.responses import ApiResponse, ok, paginated
from app.tenants.resolver import CurrentTenant
from app.users.models import User

router = APIRouter(prefix="/admin/cms", tags=["Admin-CMS"], dependencies=AUDITED)

can_view = require_permission(Permission.CMS_VIEW)
can_edit = require_permission(Permission.CMS_MANAGE)
can_publish = require_permission(Permission.CMS_PUBLISH)

DB = Annotated[AsyncSession, Depends(get_db)]


# ------------------------------------------------------------- site settings


@router.get("/site", response_model=ApiResponse[SiteSettingsRead], summary="Logo, contact, socials")
async def get_site_settings(session: DB, user: User = Depends(can_view)):
    site = await CmsService(session, user.tenant_id).get_site()
    if site is None:
        return ok(SiteSettingsRead(), message="Site settings")
    values = {field: getattr(site, field) for field in SiteSettingsRead.model_fields}
    values["social_links"] = site.social_links or {}
    return ok(SiteSettingsRead(**values), message="Site settings")


@router.put(
    "/site",
    response_model=ApiResponse[SiteSettingsRead],
    summary="Save logo, tagline, contact details and social links (live immediately)",
)
async def update_site_settings(
    data: SiteSettingsUpdate, session: DB, user: User = Depends(can_publish)
):
    site = await CmsService(session, user.tenant_id).update_site(data, user)
    return ok(SiteSettingsRead.model_validate(site), message="Site settings saved")


def _require_publish_to_activate(user: User, activating: bool | None) -> None:
    """Switching content on is a publishing decision."""
    if activating and not has_permission(user, Permission.CMS_PUBLISH):
        raise PermissionDeniedError("Turning content on needs the cms.publish permission")


# ------------------------------------------------------------------- media


@router.get("/media", response_model=ApiResponse[list[MediaRead]], summary="Media library")
async def list_media(
    params: Annotated[MediaQuery, Query()],
    session: DB,
    user: User = Depends(can_view),
):
    rows, total = await CmsService(session, user.tenant_id).list_media(params, params.search)
    return paginated(
        [MediaRead.model_validate(m) for m in rows],
        total_items=total,
        params=params,
        message="Media",
    )


@router.post(
    "/media",
    response_model=ApiResponse[MediaRead],
    status_code=status.HTTP_201_CREATED,
    summary="Upload an image (JPEG, PNG or WebP)",
)
async def upload_media(
    session: DB,
    file: UploadFile = File(description="JPEG, PNG or WebP"),
    alt_text: str | None = Form(default=None, max_length=255),
    user: User = Depends(can_edit),
):
    media = await CmsService(session, user.tenant_id).upload_media(
        filename=file.filename or "",
        content_type=file.content_type or "",
        data=await file.read(),
        alt_text=alt_text,
        user=user,
    )
    return ok(MediaRead.model_validate(media), message="Image uploaded")


@router.patch("/media/{media_id}", response_model=ApiResponse[MediaRead], summary="Edit alt text")
async def update_media(
    media_id: UUID, data: MediaUpdate, session: DB, user: User = Depends(can_edit)
):
    media = await CmsService(session, user.tenant_id).update_media(media_id, data.alt_text)
    return ok(MediaRead.model_validate(media), message="Media updated")


@router.delete(
    "/media/{media_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete unused media"
)
async def delete_media(media_id: UUID, session: DB, user: User = Depends(can_edit)):
    await CmsService(session, user.tenant_id).delete_media(media_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------- homepage sections


@router.get("/sections", response_model=ApiResponse[list[SectionRead]], summary="Homepage sections")
async def list_sections(session: DB, user: User = Depends(can_view)):
    sections = await CmsService(session, user.tenant_id).list_sections()
    return ok([section_read(s) for s in sections], message="Sections")


@router.post(
    "/sections",
    response_model=ApiResponse[SectionRead],
    status_code=status.HTTP_201_CREATED,
    summary="Add a homepage section",
)
async def create_section(data: SectionCreate, session: DB, user: User = Depends(can_edit)):
    _require_publish_to_activate(user, data.is_active)
    section = await CmsService(session, user.tenant_id).create_section(data, user)
    return ok(section_read(section), message="Section created")


@router.put(
    "/sections/order", response_model=ApiResponse[list[SectionRead]], summary="Reorder sections"
)
async def reorder_sections(data: ReorderRequest, session: DB, user: User = Depends(can_edit)):
    sections = await CmsService(session, user.tenant_id).reorder_sections(data.ids)
    return ok([section_read(s) for s in sections], message="Sections reordered")


@router.get("/sections/{section_id}", response_model=ApiResponse[SectionRead], summary="Section")
async def get_section(section_id: UUID, session: DB, user: User = Depends(can_view)):
    return ok(
        section_read(await CmsService(session, user.tenant_id).get_section(section_id)),
        message="Section",
    )


@router.patch(
    "/sections/{section_id}", response_model=ApiResponse[SectionRead], summary="Edit a section"
)
async def update_section(
    section_id: UUID, data: SectionUpdate, session: DB, user: User = Depends(can_edit)
):
    _require_publish_to_activate(user, data.is_active)
    section = await CmsService(session, user.tenant_id).update_section(section_id, data, user)
    return ok(section_read(section), message="Section updated")


@router.delete(
    "/sections/{section_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a section"
)
async def delete_section(section_id: UUID, session: DB, user: User = Depends(can_edit)):
    await CmsService(session, user.tenant_id).delete_section(section_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------- pages


@router.get("/pages", response_model=ApiResponse[list[PageSummary]], summary="Static pages")
async def list_pages(
    params: Annotated[ContentQuery, Query()], session: DB, user: User = Depends(can_view)
):
    rows, total = await CmsService(session, user.tenant_id).list_pages(
        params, params.status, params.search
    )
    return paginated(
        [page_summary(p) for p in rows], total_items=total, params=params, message="Pages"
    )


@router.post(
    "/pages",
    response_model=ApiResponse[PageRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create a page (as a draft)",
)
async def create_page(data: PageCreate, session: DB, user: User = Depends(can_edit)):
    page = await CmsService(session, user.tenant_id).create_page(data, user)
    return ok(page_read(page), message="Page created")


@router.get("/pages/{page_id}", response_model=ApiResponse[PageRead], summary="Page (preview)")
async def get_page(page_id: UUID, session: DB, user: User = Depends(can_view)):
    return ok(
        page_read(await CmsService(session, user.tenant_id).get_page(page_id)), message="Page"
    )


@router.patch("/pages/{page_id}", response_model=ApiResponse[PageRead], summary="Edit a page")
async def update_page(page_id: UUID, data: PageUpdate, session: DB, user: User = Depends(can_edit)):
    page = await CmsService(session, user.tenant_id).update_page(page_id, data, user)
    return ok(page_read(page), message="Page updated")


@router.post(
    "/pages/{page_id}/publish",
    response_model=ApiResponse[PageRead],
    summary="Publish now or schedule",
)
async def publish_page(
    page_id: UUID, data: PublishRequest, session: DB, user: User = Depends(can_publish)
):
    page = await CmsService(session, user.tenant_id).publish(
        ContentPage, page_id, "Page", user, data.publish_at
    )
    return ok(page_read(page), message="Page published")


@router.post(
    "/pages/{page_id}/unpublish", response_model=ApiResponse[PageRead], summary="Unpublish"
)
async def unpublish_page(page_id: UUID, session: DB, user: User = Depends(can_publish)):
    page = await CmsService(session, user.tenant_id).unpublish(ContentPage, page_id, "Page", user)
    return ok(page_read(page), message="Page unpublished")


@router.delete("/pages/{page_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete page")
async def delete_page(page_id: UUID, session: DB, user: User = Depends(can_edit)):
    await CmsService(session, user.tenant_id).delete_page(page_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# -------------------------------------------------------------------- FAQs


@router.get(
    "/faq-categories", response_model=ApiResponse[list[FaqCategoryRead]], summary="FAQ categories"
)
async def list_faq_categories(session: DB, user: User = Depends(can_view)):
    rows = await CmsService(session, user.tenant_id).list_faq_categories()
    return ok([FaqCategoryRead.model_validate(c) for c in rows], message="FAQ categories")


@router.post(
    "/faq-categories",
    response_model=ApiResponse[FaqCategoryRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create an FAQ category",
)
async def create_faq_category(data: FaqCategoryWrite, session: DB, user: User = Depends(can_edit)):
    category = await CmsService(session, user.tenant_id).create_faq_category(data, user)
    return ok(FaqCategoryRead.model_validate(category), message="FAQ category created")


@router.put(
    "/faq-categories/order",
    response_model=ApiResponse[list[FaqCategoryRead]],
    summary="Reorder FAQ categories",
)
async def reorder_faq_categories(data: ReorderRequest, session: DB, user: User = Depends(can_edit)):
    rows = await CmsService(session, user.tenant_id).reorder_faq_categories(data.ids)
    return ok([FaqCategoryRead.model_validate(c) for c in rows], message="Reordered")


@router.patch(
    "/faq-categories/{category_id}",
    response_model=ApiResponse[FaqCategoryRead],
    summary="Rename or (de)activate an FAQ category",
)
async def update_faq_category(
    category_id: UUID, data: FaqCategoryUpdate, session: DB, user: User = Depends(can_edit)
):
    category = await CmsService(session, user.tenant_id).update_faq_category(
        category_id, data, user
    )
    return ok(FaqCategoryRead.model_validate(category), message="FAQ category updated")


@router.delete(
    "/faq-categories/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an FAQ category and its questions",
)
async def delete_faq_category(category_id: UUID, session: DB, user: User = Depends(can_edit)):
    await CmsService(session, user.tenant_id).delete_faq_category(category_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/faqs", response_model=ApiResponse[list[FaqRead]], summary="FAQs")
async def list_faqs(
    session: DB, category_id: UUID | None = Query(default=None), user: User = Depends(can_view)
):
    rows = await CmsService(session, user.tenant_id).list_faqs(category_id)
    return ok([faq_read(f) for f in rows], message="FAQs")


@router.post(
    "/faqs",
    response_model=ApiResponse[FaqRead],
    status_code=status.HTTP_201_CREATED,
    summary="Add a question (as a draft)",
)
async def create_faq(data: FaqCreate, session: DB, user: User = Depends(can_edit)):
    faq = await CmsService(session, user.tenant_id).create_faq(data, user)
    return ok(faq_read(faq), message="FAQ created")


@router.put(
    "/faq-categories/{category_id}/faqs/order",
    response_model=ApiResponse[list[FaqRead]],
    summary="Reorder questions in a category",
)
async def reorder_faqs(
    category_id: UUID, data: ReorderRequest, session: DB, user: User = Depends(can_edit)
):
    rows = await CmsService(session, user.tenant_id).reorder_faqs(category_id, data.ids)
    return ok([faq_read(f) for f in rows], message="Reordered")


@router.patch("/faqs/{faq_id}", response_model=ApiResponse[FaqRead], summary="Edit a question")
async def update_faq(faq_id: UUID, data: FaqUpdate, session: DB, user: User = Depends(can_edit)):
    faq = await CmsService(session, user.tenant_id).update_faq(faq_id, data, user)
    return ok(faq_read(faq), message="FAQ updated")


@router.post("/faqs/{faq_id}/publish", response_model=ApiResponse[FaqRead], summary="Publish")
async def publish_faq(
    faq_id: UUID, data: PublishRequest, session: DB, user: User = Depends(can_publish)
):
    faq = await CmsService(session, user.tenant_id).publish(
        Faq, faq_id, "FAQ", user, data.publish_at
    )
    return ok(faq_read(faq), message="FAQ published")


@router.post("/faqs/{faq_id}/unpublish", response_model=ApiResponse[FaqRead], summary="Unpublish")
async def unpublish_faq(faq_id: UUID, session: DB, user: User = Depends(can_publish)):
    faq = await CmsService(session, user.tenant_id).unpublish(Faq, faq_id, "FAQ", user)
    return ok(faq_read(faq), message="FAQ unpublished")


@router.delete("/faqs/{faq_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete")
async def delete_faq(faq_id: UUID, session: DB, user: User = Depends(can_edit)):
    await CmsService(session, user.tenant_id).delete_faq(faq_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# -------------------------------------------------------------- navigation


@router.get(
    "/navigation", response_model=ApiResponse[list[NavigationRead]], summary="Menus as trees"
)
async def list_navigation(
    session: DB, menu: MenuLocation | None = Query(default=None), user: User = Depends(can_view)
):
    rows = await CmsService(session, user.tenant_id).list_navigation(menu.value if menu else None)
    return ok(navigation_tree(rows), message="Navigation")


@router.post(
    "/navigation",
    response_model=ApiResponse[NavigationRead],
    status_code=status.HTTP_201_CREATED,
    summary="Add a menu item",
)
async def create_navigation(data: NavigationCreate, session: DB, user: User = Depends(can_edit)):
    _require_publish_to_activate(user, data.is_active)
    item = await CmsService(session, user.tenant_id).create_navigation(data, user)
    return ok(navigation_read(item), message="Menu item created")


@router.put(
    "/navigation/{menu}/order",
    response_model=ApiResponse[list[NavigationRead]],
    summary="Reorder a menu",
)
async def reorder_navigation(
    menu: MenuLocation, data: ReorderRequest, session: DB, user: User = Depends(can_edit)
):
    rows = await CmsService(session, user.tenant_id).reorder_navigation(menu.value, data.ids)
    return ok(navigation_tree(rows), message="Menu reordered")


@router.patch(
    "/navigation/{item_id}", response_model=ApiResponse[NavigationRead], summary="Edit menu item"
)
async def update_navigation(
    item_id: UUID, data: NavigationUpdate, session: DB, user: User = Depends(can_edit)
):
    _require_publish_to_activate(user, data.is_active)
    item = await CmsService(session, user.tenant_id).update_navigation(item_id, data, user)
    return ok(navigation_read(item), message="Menu item updated")


@router.delete(
    "/navigation/{item_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove menu item"
)
async def delete_navigation(item_id: UUID, session: DB, user: User = Depends(can_edit)):
    await CmsService(session, user.tenant_id).delete_navigation(item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# -------------------------------------------------------------------- blog


@router.get("/blog", response_model=ApiResponse[list[BlogSummary]], summary="Articles")
async def list_posts(
    params: Annotated[BlogQuery, Query()], session: DB, user: User = Depends(can_view)
):
    rows, total = await CmsService(session, user.tenant_id).list_posts(
        params, params.status, params.search, params.tag, params.category
    )
    return paginated(
        [blog_summary(p) for p in rows], total_items=total, params=params, message="Articles"
    )


@router.post(
    "/blog",
    response_model=ApiResponse[BlogRead],
    status_code=status.HTTP_201_CREATED,
    summary="Write an article (as a draft)",
)
async def create_post(data: BlogCreate, session: DB, user: User = Depends(can_edit)):
    post = await CmsService(session, user.tenant_id).create_post(data, user)
    return ok(blog_read(post), message="Article created")


@router.get("/blog/{post_id}", response_model=ApiResponse[BlogRead], summary="Article (preview)")
async def get_post(post_id: UUID, session: DB, user: User = Depends(can_view)):
    return ok(
        blog_read(await CmsService(session, user.tenant_id).get_post(post_id)), message="Article"
    )


@router.patch("/blog/{post_id}", response_model=ApiResponse[BlogRead], summary="Edit an article")
async def update_post(post_id: UUID, data: BlogUpdate, session: DB, user: User = Depends(can_edit)):
    post = await CmsService(session, user.tenant_id).update_post(post_id, data, user)
    return ok(blog_read(post), message="Article updated")


@router.post(
    "/blog/{post_id}/publish", response_model=ApiResponse[BlogRead], summary="Publish or schedule"
)
async def publish_post(
    post_id: UUID, data: PublishRequest, session: DB, user: User = Depends(can_publish)
):
    post = await CmsService(session, user.tenant_id).publish(
        BlogPost, post_id, "Article", user, data.publish_at
    )
    return ok(blog_read(post), message="Article published")


@router.post("/blog/{post_id}/unpublish", response_model=ApiResponse[BlogRead], summary="Unpublish")
async def unpublish_post(post_id: UUID, session: DB, user: User = Depends(can_publish)):
    post = await CmsService(session, user.tenant_id).unpublish(BlogPost, post_id, "Article", user)
    return ok(blog_read(post), message="Article unpublished")


@router.delete("/blog/{post_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete")
async def delete_post(post_id: UUID, session: DB, user: User = Depends(can_edit)):
    await CmsService(session, user.tenant_id).delete_post(post_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


storefront_router = APIRouter(prefix="/storefront/cms", tags=["Storefront-CMS"])


@storefront_router.get(
    "/site",
    response_model=ApiResponse[StorefrontSite],
    summary="Logo, contact, socials",
)
async def site_settings(
    tenant: CurrentTenant, session: AsyncSession = Depends(get_db)
) -> ApiResponse[StorefrontSite]:
    site = await CmsService(session, tenant.id).get_site()
    if site is None:
        return ok(StorefrontSite(), message="Site settings")
    values = {field: getattr(site, field) for field in StorefrontSite.model_fields}
    values["social_links"] = site.social_links or {}
    return ok(StorefrontSite(**values), message="Site settings")


@storefront_router.get(
    "/home",
    response_model=ApiResponse[list[StorefrontSection]],
    summary="Live homepage sections in display order, with their products",
)
async def homepage(
    tenant: CurrentTenant, session: AsyncSession = Depends(get_db)
) -> ApiResponse[list[StorefrontSection]]:
    service = CmsService(session, tenant.id)
    sections = []
    for section in await service.live_sections():
        settings = section.settings or {}
        sections.append(
            StorefrontSection(
                id=section.id,
                section_type=section.section_type,
                title=section.title,
                subtitle=section.subtitle,
                position=section.position,
                ends_at=section.ends_at,
                countdown_ends_at=settings.get("countdown_ends_at"),
                items=[BannerItem(**item) for item in section.items or []],
                products=[storefront_summary(p) for p in await service.section_products(section)],
            )
        )
    return ok(sections, message="Homepage")


@storefront_router.get(
    "/pages/{slug}",
    response_model=ApiResponse[StorefrontPage],
    summary="A published page",
)
async def page(
    slug: str, tenant: CurrentTenant, session: AsyncSession = Depends(get_db)
) -> ApiResponse[StorefrontPage]:
    return ok(storefront_page(await CmsService(session, tenant.id).live_page(slug)), message="Page")


@storefront_router.get(
    "/faqs",
    response_model=ApiResponse[list[StorefrontFaqCategory]],
    summary="Published FAQs grouped by category",
)
async def faqs(
    tenant: CurrentTenant, session: AsyncSession = Depends(get_db)
) -> ApiResponse[list[StorefrontFaqCategory]]:
    groups = await CmsService(session, tenant.id).live_faqs()
    return ok(
        [
            StorefrontFaqCategory(
                id=category.id,
                name=category.name,
                faqs=[StorefrontFaq(id=f.id, question=f.question, answer=f.answer) for f in items],
            )
            for category, items in groups
        ],
        message="FAQs",
    )


@storefront_router.get(
    "/navigation",
    response_model=ApiResponse[list[NavigationRead]],
    summary="A menu's active items as a tree",
)
async def navigation(
    tenant: CurrentTenant,
    menu: MenuLocation = Query(default=MenuLocation.HEADER),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[list[NavigationRead]]:
    items = await CmsService(session, tenant.id).list_navigation(menu.value)
    return ok(navigation_tree(items, active_only=True), message="Navigation")


@storefront_router.get(
    "/blog", response_model=ApiResponse[list[StorefrontBlogSummary]], summary="Published articles"
)
async def blog(
    tenant: CurrentTenant,
    params: Annotated[StorefrontBlogQuery, Query()],
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[list[StorefrontBlogSummary]]:
    rows, total = await CmsService(session, tenant.id).live_posts(
        params, params.tag, params.category
    )
    return paginated(
        [storefront_post_summary(p) for p in rows],
        total_items=total,
        params=params,
        message="Articles",
    )


@storefront_router.get(
    "/blog/{slug}", response_model=ApiResponse[StorefrontBlogPost], summary="A published article"
)
async def blog_post(
    slug: str, tenant: CurrentTenant, session: AsyncSession = Depends(get_db)
) -> ApiResponse[StorefrontBlogPost]:
    post = await CmsService(session, tenant.id).live_post(slug)
    return ok(storefront_post(post), message="Article")
