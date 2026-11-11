from __future__ import annotations

from app.cms.models import BlogPost, ContentPage, Faq, HomeSection, NavigationItem
from app.cms.schemas import (
    BannerItem,
    BlogRead,
    BlogSummary,
    FaqRead,
    NavigationRead,
    PageRead,
    PageSummary,
    SectionRead,
    SectionSettings,
    StorefrontBlogPost,
    StorefrontBlogSummary,
    StorefrontPage,
)
from app.cms.service import href_for, is_live, section_is_live


def _published(item) -> dict:
    return {
        "status": item.status,
        "published_at": item.published_at,
        "is_live": is_live(item),
        "created_by_id": item.created_by_id,
        "updated_by_id": item.updated_by_id,
        "published_by_id": item.published_by_id,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def section_read(section: HomeSection) -> SectionRead:
    return SectionRead(
        id=section.id,
        section_type=section.section_type,
        title=section.title,
        subtitle=section.subtitle,
        is_active=section.is_active,
        position=section.position,
        starts_at=section.starts_at,
        ends_at=section.ends_at,
        is_live=section_is_live(section),
        items=[BannerItem(**item) for item in section.items or []],
        settings=SectionSettings(**(section.settings or {})),
        created_by_id=section.created_by_id,
        updated_by_id=section.updated_by_id,
        created_at=section.created_at,
        updated_at=section.updated_at,
    )


def page_read(page: ContentPage) -> PageRead:
    return PageRead(
        id=page.id,
        slug=page.slug,
        title=page.title,
        page_type=page.page_type,
        body=page.body,
        seo_title=page.seo_title,
        seo_description=page.seo_description,
        **_published(page),
    )


def page_summary(page: ContentPage) -> PageSummary:
    return PageSummary(
        id=page.id,
        slug=page.slug,
        title=page.title,
        page_type=page.page_type,
        status=page.status,
        published_at=page.published_at,
        is_live=is_live(page),
        updated_at=page.updated_at,
    )


def storefront_page(page: ContentPage) -> StorefrontPage:
    return StorefrontPage(
        slug=page.slug,
        title=page.title,
        page_type=page.page_type,
        body=page.body,
        seo_title=page.seo_title,
        seo_description=page.seo_description,
        published_at=page.published_at,
        updated_at=page.updated_at,
    )


def faq_read(faq: Faq) -> FaqRead:
    return FaqRead(
        id=faq.id,
        category_id=faq.category_id,
        question=faq.question,
        answer=faq.answer,
        position=faq.position,
        **_published(faq),
    )


def navigation_read(item: NavigationItem) -> NavigationRead:
    return NavigationRead(
        id=item.id,
        menu=item.menu,
        label=item.label,
        link_type=item.link_type,
        target=item.target,
        href=href_for(item.link_type, item.target),
        parent_id=item.parent_id,
        position=item.position,
        is_active=item.is_active,
        open_in_new_tab=item.open_in_new_tab,
    )


def navigation_tree(items: list[NavigationItem], *, active_only: bool = False):
    """Top-level items with their children nested, in display order."""
    nodes: dict = {}
    for item in items:
        if active_only and not item.is_active:
            continue
        nodes[item.id] = navigation_read(item)
    roots = []
    for node in sorted(nodes.values(), key=lambda n: (n.menu, n.position)):
        if node.parent_id is None:
            roots.append(node)
        elif node.parent_id in nodes:
            nodes[node.parent_id].children.append(node)
    return roots


def blog_read(post: BlogPost) -> BlogRead:
    return BlogRead(
        id=post.id,
        slug=post.slug,
        title=post.title,
        excerpt=post.excerpt,
        content=post.content,
        featured_image_url=post.featured_image_url,
        author_name=post.author_name,
        category=post.category,
        tags=post.tags or [],
        seo_title=post.seo_title,
        seo_description=post.seo_description,
        **_published(post),
    )


def blog_summary(post: BlogPost) -> BlogSummary:
    return BlogSummary(
        id=post.id,
        slug=post.slug,
        title=post.title,
        excerpt=post.excerpt,
        featured_image_url=post.featured_image_url,
        author_name=post.author_name,
        category=post.category,
        tags=post.tags or [],
        status=post.status,
        published_at=post.published_at,
        is_live=is_live(post),
    )


def storefront_post_summary(post: BlogPost) -> StorefrontBlogSummary:
    return StorefrontBlogSummary(
        slug=post.slug,
        title=post.title,
        excerpt=post.excerpt,
        featured_image_url=post.featured_image_url,
        author_name=post.author_name,
        category=post.category,
        tags=post.tags or [],
        published_at=post.published_at,
    )


def storefront_post(post: BlogPost) -> StorefrontBlogPost:
    return StorefrontBlogPost(
        **storefront_post_summary(post).model_dump(),
        content=post.content,
        seo_title=post.seo_title,
        seo_description=post.seo_description,
    )
