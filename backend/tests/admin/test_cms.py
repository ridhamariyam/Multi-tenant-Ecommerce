"""CMS: homepage sections, pages, FAQs, navigation, blog, media, publishing."""

from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from PIL import Image

from app.core.config import get_settings
from tests.admin.conftest import CMS, STOREFRONT_CMS
from tests.catalogue.factories import make_category, make_product


def _iso(delta: timedelta) -> str:
    return (datetime.now(timezone.utc) + delta).isoformat()


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (30, 30), (10, 120, 200)).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def _clean_uploads():
    yield
    root = Path(get_settings().storage_local_path)
    for path in root.rglob("*"):
        if path.is_file():
            path.unlink()


async def _live_product(client, admin_headers, category, name):
    product = await make_product(client, admin_headers, category["id"], name=name, status="ACTIVE")
    return product


# ------------------------------------------------------------------ sections


async def test_an_active_banner_shows_on_the_storefront_home(client, admin_headers):
    created = await client.post(
        f"{CMS}/sections",
        json={
            "section_type": "HERO_BANNER",
            "title": "Festive Edit",
            "is_active": True,
            "items": [
                {"image_url": "/media/hero.jpg", "heading": "New in", "link_url": "/sale"}
            ],
        },
        headers=admin_headers,
    )

    home = await client.get(f"{STOREFRONT_CMS}/home")

    assert created.status_code == 201
    sections = home.json()["data"]
    assert [s["title"] for s in sections] == ["Festive Edit"]
    assert sections[0]["items"][0]["link_url"] == "/sale"


async def test_inactive_and_out_of_window_sections_are_hidden(client, admin_headers):
    for payload in (
        {"section_type": "PROMO_STRIP", "title": "Off", "is_active": False},
        {"section_type": "PROMO_STRIP", "title": "Later", "is_active": True,
         "starts_at": _iso(timedelta(days=1))},
        {"section_type": "PROMO_STRIP", "title": "Over", "is_active": True,
         "ends_at": _iso(-timedelta(hours=1))},
    ):
        assert (await client.post(f"{CMS}/sections", json=payload, headers=admin_headers)).status_code == 201

    home = await client.get(f"{STOREFRONT_CMS}/home")

    assert home.json()["data"] == []


async def test_sections_follow_their_display_order(client, admin_headers):
    first = (await client.post(f"{CMS}/sections", json={"section_type": "PROMO_STRIP", "title": "A", "is_active": True}, headers=admin_headers)).json()["data"]
    second = (await client.post(f"{CMS}/sections", json={"section_type": "PROMO_STRIP", "title": "B", "is_active": True}, headers=admin_headers)).json()["data"]

    await client.put(f"{CMS}/sections/order", json={"ids": [second["id"], first["id"]]}, headers=admin_headers)
    home = await client.get(f"{STOREFRONT_CMS}/home")

    assert [s["title"] for s in home.json()["data"]] == ["B", "A"]


async def test_a_new_arrivals_shelf_lists_live_products(client, admin_headers):
    category = await make_category(client, admin_headers, name="Shelf Cat")
    older = await _live_product(client, admin_headers, category, "Older")
    newer = await _live_product(client, admin_headers, category, "Newer")
    await make_product(client, admin_headers, category["id"], name="Draft")
    await client.post(
        f"{CMS}/sections",
        json={"section_type": "NEW_ARRIVALS", "title": "New", "is_active": True, "settings": {"limit": 5}},
        headers=admin_headers,
    )

    home = await client.get(f"{STOREFRONT_CMS}/home")

    ids = [p["id"] for p in home.json()["data"][0]["products"]]
    assert ids == [newer["id"], older["id"]]


async def test_a_featured_shelf_keeps_hand_picked_order(client, admin_headers):
    category = await make_category(client, admin_headers, name="Pick Cat")
    one = await _live_product(client, admin_headers, category, "One")
    two = await _live_product(client, admin_headers, category, "Two")
    await client.post(
        f"{CMS}/sections",
        json={"section_type": "FEATURED_PRODUCTS", "title": "Picks", "is_active": True,
              "settings": {"product_ids": [two["id"], one["id"]]}},
        headers=admin_headers,
    )

    home = await client.get(f"{STOREFRONT_CMS}/home")

    assert [p["id"] for p in home.json()["data"][0]["products"]] == [two["id"], one["id"]]


async def test_a_section_cannot_point_at_an_unknown_product(client, admin_headers):
    response = await client.post(
        f"{CMS}/sections",
        json={"section_type": "SEASONAL", "settings": {"product_ids": ["00000000-0000-0000-0000-000000000000"]}},
        headers=admin_headers,
    )

    assert response.status_code == 404


async def test_banner_links_must_be_safe(client, admin_headers):
    response = await client.post(
        f"{CMS}/sections",
        json={"section_type": "HERO_BANNER", "items": [{"link_url": "javascript:alert(1)"}]},
        headers=admin_headers,
    )

    assert response.status_code == 422


# --------------------------------------------------------------------- pages


async def test_a_draft_page_is_private_until_published(client, admin_headers):
    page = (
        await client.post(
            f"{CMS}/pages",
            json={"title": "Shipping Policy", "page_type": "SHIPPING_POLICY", "body": "# Ships in 3 days"},
            headers=admin_headers,
        )
    ).json()["data"]

    before = await client.get(f"{STOREFRONT_CMS}/pages/shipping-policy")
    await client.post(f"{CMS}/pages/{page['id']}/publish", json={}, headers=admin_headers)
    after = await client.get(f"{STOREFRONT_CMS}/pages/shipping-policy")

    assert page["slug"] == "shipping-policy"
    assert page["status"] == "DRAFT"
    assert before.status_code == 404
    assert after.status_code == 200
    assert after.json()["data"]["body"] == "# Ships in 3 days"


async def test_a_scheduled_page_waits_for_its_time(client, admin_headers):
    page = (await client.post(f"{CMS}/pages", json={"title": "Later"}, headers=admin_headers)).json()["data"]

    published = await client.post(
        f"{CMS}/pages/{page['id']}/publish", json={"publish_at": _iso(timedelta(days=1))}, headers=admin_headers
    )
    public = await client.get(f"{STOREFRONT_CMS}/pages/later")

    assert published.json()["data"]["status"] == "PUBLISHED"
    assert published.json()["data"]["is_live"] is False
    assert public.status_code == 404


async def test_unpublishing_hides_a_page(client, admin_headers):
    page = (await client.post(f"{CMS}/pages", json={"title": "About Us", "page_type": "ABOUT"}, headers=admin_headers)).json()["data"]
    await client.post(f"{CMS}/pages/{page['id']}/publish", json={}, headers=admin_headers)

    await client.post(f"{CMS}/pages/{page['id']}/unpublish", headers=admin_headers)

    assert (await client.get(f"{STOREFRONT_CMS}/pages/about-us")).status_code == 404


async def test_page_slugs_are_unique(client, admin_headers):
    await client.post(f"{CMS}/pages", json={"title": "Terms", "slug": "terms"}, headers=admin_headers)

    response = await client.post(f"{CMS}/pages", json={"title": "Terms 2", "slug": "terms"}, headers=admin_headers)

    assert response.status_code == 409


# ---------------------------------------------------------------------- FAQs


async def test_published_faqs_are_grouped_by_category(client, admin_headers):
    category = (await client.post(f"{CMS}/faq-categories", json={"name": "Orders"}, headers=admin_headers)).json()["data"]
    live = (await client.post(f"{CMS}/faqs", json={"category_id": category["id"], "question": "Where is my order?", "answer": "Track it."}, headers=admin_headers)).json()["data"]
    await client.post(f"{CMS}/faqs", json={"category_id": category["id"], "question": "Draft?", "answer": "Hidden"}, headers=admin_headers)
    await client.post(f"{CMS}/faqs/{live['id']}/publish", json={}, headers=admin_headers)

    response = await client.get(f"{STOREFRONT_CMS}/faqs")

    groups = response.json()["data"]
    assert [g["name"] for g in groups] == ["Orders"]
    assert [f["question"] for f in groups[0]["faqs"]] == ["Where is my order?"]


async def test_an_inactive_faq_category_is_hidden(client, admin_headers):
    category = (await client.post(f"{CMS}/faq-categories", json={"name": "Old", "is_active": False}, headers=admin_headers)).json()["data"]
    faq = (await client.post(f"{CMS}/faqs", json={"category_id": category["id"], "question": "Q", "answer": "A"}, headers=admin_headers)).json()["data"]
    await client.post(f"{CMS}/faqs/{faq['id']}/publish", json={}, headers=admin_headers)

    assert (await client.get(f"{STOREFRONT_CMS}/faqs")).json()["data"] == []


# ---------------------------------------------------------------- navigation


async def test_navigation_links_resolve_and_nest(client, admin_headers):
    category = await make_category(client, admin_headers, name="Churidars")
    parent = (await client.post(f"{CMS}/navigation", json={"menu": "HEADER", "label": "Shop", "link_type": "CATEGORY", "target": category["id"]}, headers=admin_headers)).json()["data"]
    await client.post(f"{CMS}/navigation", json={"menu": "HEADER", "label": "Sale", "link_type": "URL", "target": "/sale", "parent_id": parent["id"]}, headers=admin_headers)
    await client.post(f"{CMS}/navigation", json={"menu": "HEADER", "label": "Hidden", "link_type": "HOME", "is_active": False}, headers=admin_headers)

    menu = (await client.get(f"{STOREFRONT_CMS}/navigation", params={"menu": "HEADER"})).json()["data"]

    assert [m["label"] for m in menu] == ["Shop"]
    assert menu[0]["href"] == f"/categories/{category['id']}"
    assert [c["href"] for c in menu[0]["children"]] == ["/sale"]


async def test_a_link_to_a_missing_page_is_rejected(client, admin_headers):
    response = await client.post(
        f"{CMS}/navigation", json={"menu": "FOOTER", "label": "Gone", "link_type": "PAGE", "target": "no-such-page"}, headers=admin_headers
    )

    assert response.status_code == 404


async def test_menus_nest_only_one_level(client, admin_headers):
    top = (await client.post(f"{CMS}/navigation", json={"menu": "FOOTER", "label": "Top", "link_type": "HOME"}, headers=admin_headers)).json()["data"]
    child = (await client.post(f"{CMS}/navigation", json={"menu": "FOOTER", "label": "Child", "link_type": "FAQ", "parent_id": top["id"]}, headers=admin_headers)).json()["data"]

    response = await client.post(
        f"{CMS}/navigation", json={"menu": "FOOTER", "label": "Grandchild", "link_type": "HOME", "parent_id": child["id"]}, headers=admin_headers
    )

    assert response.status_code == 400


# ---------------------------------------------------------------------- blog


async def test_a_published_article_is_listed_and_readable(client, admin_headers):
    post = (await client.post(f"{CMS}/blog", json={"title": "Choosing Cotton", "content": "Breathable.", "tags": ["fabric"]}, headers=admin_headers)).json()["data"]
    await client.post(f"{CMS}/blog", json={"title": "Draft Post"}, headers=admin_headers)
    await client.post(f"{CMS}/blog/{post['id']}/publish", json={}, headers=admin_headers)

    listing = (await client.get(f"{STOREFRONT_CMS}/blog", params={"tag": "fabric"})).json()["data"]
    article = await client.get(f"{STOREFRONT_CMS}/blog/choosing-cotton")
    draft = await client.get(f"{STOREFRONT_CMS}/blog/draft-post")

    assert [p["slug"] for p in listing] == ["choosing-cotton"]
    assert article.json()["data"]["content"] == "Breathable."
    assert draft.status_code == 404


# --------------------------------------------------------------------- media


async def test_media_is_uploaded_and_listed(client, admin_headers):
    response = await client.post(
        f"{CMS}/media", files={"file": ("hero.png", _png(), "image/png")}, data={"alt_text": "Hero"}, headers=admin_headers
    )
    listed = await client.get(f"{CMS}/media", headers=admin_headers)

    media = response.json()["data"]
    assert response.status_code == 201
    assert media["url"].startswith(get_settings().storage_public_base_url)
    assert listed.json()["data"][0]["id"] == media["id"]


async def test_non_images_are_rejected(client, admin_headers):
    response = await client.post(
        f"{CMS}/media", files={"file": ("x.pdf", b"%PDF-1.4", "application/pdf")}, headers=admin_headers
    )

    assert response.status_code == 400


async def test_media_in_use_cannot_be_deleted(client, admin_headers):
    media = (await client.post(f"{CMS}/media", files={"file": ("b.png", _png(), "image/png")}, headers=admin_headers)).json()["data"]
    await client.post(
        f"{CMS}/sections",
        json={"section_type": "HERO_BANNER", "items": [{"image_url": media["url"]}]},
        headers=admin_headers,
    )

    response = await client.delete(f"{CMS}/media/{media['id']}", headers=admin_headers)

    assert response.status_code == 409


# --------------------------------------------------------------- permissions


async def test_editors_cannot_publish_without_permission(client, staff_with):
    editor = await staff_with("cms.view", "cms.manage")
    page = (await client.post(f"{CMS}/pages", json={"title": "Editor Page"}, headers=editor)).json()["data"]

    publish = await client.post(f"{CMS}/pages/{page['id']}/publish", json={}, headers=editor)
    activate = await client.post(
        f"{CMS}/sections", json={"section_type": "PROMO_STRIP", "is_active": True}, headers=editor
    )

    assert publish.status_code == 403
    assert activate.status_code == 403


async def test_a_publisher_can_publish(client, staff_with):
    publisher = await staff_with("cms.view", "cms.manage", "cms.publish")
    page = (await client.post(f"{CMS}/pages", json={"title": "Pub Page"}, headers=publisher)).json()["data"]

    response = await client.post(f"{CMS}/pages/{page['id']}/publish", json={}, headers=publisher)

    assert response.status_code == 200
    assert response.json()["data"]["published_by_id"] is not None


async def test_legacy_staff_and_customers_cannot_use_the_cms(client, staff_headers, customer_headers):
    assert (await client.get(f"{CMS}/pages", headers=staff_headers)).status_code == 403
    assert (await client.get(f"{CMS}/pages", headers=customer_headers)).status_code == 403


async def test_cms_changes_are_in_the_activity_log(client, admin_headers):
    page = (await client.post(f"{CMS}/pages", json={"title": "Logged"}, headers=admin_headers)).json()["data"]
    await client.post(f"{CMS}/pages/{page['id']}/publish", json={}, headers=admin_headers)

    logs = (await client.get("/api/v1/admin/audit-logs", params={"entity_id": page["id"]}, headers=admin_headers)).json()["data"]

    assert [log["action"] for log in logs] == ["publish_page"]


async def test_content_is_isolated_per_tenant(client, other_client, admin_headers, other_tenant):
    page = (await client.post(f"{CMS}/pages", json={"title": "Zeen Only"}, headers=admin_headers)).json()["data"]
    await client.post(f"{CMS}/pages/{page['id']}/publish", json={}, headers=admin_headers)
    await client.post(f"{CMS}/sections", json={"section_type": "PROMO_STRIP", "title": "Zeen", "is_active": True}, headers=admin_headers)

    other_page = await other_client.get(f"{STOREFRONT_CMS}/pages/zeen-only")
    other_home = await other_client.get(f"{STOREFRONT_CMS}/home")

    assert other_page.status_code == 404
    assert other_home.json()["data"] == []


async def test_another_tenants_admin_cannot_edit_our_content(client, other_client, admin_headers, other_admin_headers):
    page = (await client.post(f"{CMS}/pages", json={"title": "Mine"}, headers=admin_headers)).json()["data"]

    response = await other_client.patch(f"{CMS}/pages/{page['id']}", json={"title": "Stolen"}, headers=other_admin_headers)

    assert response.status_code == 404


# ------------------------------------------------------- hero image required


async def test_a_hero_banner_needs_an_image(client, admin_headers):
    no_slides = await client.post(f"{CMS}/sections", json={"section_type": "HERO_BANNER"}, headers=admin_headers)
    no_image = await client.post(
        f"{CMS}/sections",
        json={"section_type": "HERO_BANNER", "items": [{"heading": "Sale"}]},
        headers=admin_headers,
    )

    assert no_slides.status_code == 400
    assert no_image.status_code == 400
    assert no_image.json()["error"]["code"] == "IMAGE_REQUIRED"


async def test_an_edit_cannot_remove_the_hero_image(client, admin_headers):
    hero = (
        await client.post(
            f"{CMS}/sections",
            json={"section_type": "HERO_BANNER", "items": [{"image_url": "/media/x/hero.png"}]},
            headers=admin_headers,
        )
    ).json()["data"]

    response = await client.patch(
        f"{CMS}/sections/{hero['id']}", json={"items": [{"heading": "No picture"}]}, headers=admin_headers
    )
    renamed = await client.patch(f"{CMS}/sections/{hero['id']}", json={"title": "Renamed"}, headers=admin_headers)

    assert response.status_code == 400
    assert renamed.status_code == 200


async def test_other_sections_do_not_need_images(client, admin_headers):
    response = await client.post(
        f"{CMS}/sections", json={"section_type": "PROMO_STRIP", "items": [{"heading": "Free shipping"}]}, headers=admin_headers
    )

    assert response.status_code == 201


# ------------------------------------------------------------- site settings

SITE = {
    "logo_url": "/media/x/logo.png",
    "logo_alt": "Zeen",
    "tagline": "Everyday and ethnic wear",
    "contact_email": "hello@zeen.in",
    "contact_phone": "+91 98765 43210",
    "whatsapp_number": "+919876543210",
    "address": "Kochi, Kerala",
    "social_links": {"instagram": "https://instagram.com/zeen", "facebook": ""},
    "copyright_text": "© Zeen",
}


async def test_site_settings_start_empty_and_are_saved(client, admin_headers):
    empty = (await client.get(f"{CMS}/site", headers=admin_headers)).json()["data"]
    saved = await client.put(f"{CMS}/site", json=SITE, headers=admin_headers)
    public = (await client.get(f"{STOREFRONT_CMS}/site")).json()["data"]

    assert empty["logo_url"] is None and empty["social_links"] == {}
    assert saved.status_code == 200
    assert public["tagline"] == "Everyday and ethnic wear"
    assert public["social_links"] == {"instagram": "https://instagram.com/zeen"}  # blanks dropped
    assert public["logo_url"] == "/media/x/logo.png"


async def test_the_storefront_gets_empty_settings_before_any_are_saved(client, tenant):
    response = await client.get(f"{STOREFRONT_CMS}/site")

    assert response.status_code == 200
    assert response.json()["data"]["social_links"] == {}


async def test_site_settings_are_validated(client, admin_headers):
    for bad in (
        {"contact_email": "not-an-email"},
        {"contact_phone": "call me"},
        {"social_links": {"instagram": "http://insecure"}},
        {"social_links": {"myspace": "https://myspace.com/zeen"}},
        {"social_links": {"instagram": "https://instagram.com/" + "z" * 500}},
        {"logo_url": "javascript:alert(1)"},
    ):
        response = await client.put(f"{CMS}/site", json=bad, headers=admin_headers)
        assert response.status_code == 422, bad


async def test_site_settings_need_publish_rights(client, staff_with, staff_headers):
    editor = await staff_with("cms.view", "cms.manage")

    assert (await client.get(f"{CMS}/site", headers=editor)).status_code == 200
    assert (await client.put(f"{CMS}/site", json=SITE, headers=editor)).status_code == 403
    assert (await client.get(f"{CMS}/site", headers=staff_headers)).status_code == 403


async def test_site_settings_are_per_store(client, other_client, admin_headers, other_admin_headers):
    await client.put(f"{CMS}/site", json=SITE, headers=admin_headers)

    theirs = (await other_client.get(f"{STOREFRONT_CMS}/site")).json()["data"]
    their_admin = (await other_client.get(f"{CMS}/site", headers=other_admin_headers)).json()["data"]

    assert theirs["tagline"] is None
    assert their_admin["logo_url"] is None


async def test_the_logo_image_cannot_be_deleted_while_used(client, admin_headers):
    media = (await client.post(f"{CMS}/media", files={"file": ("logo.png", _png(), "image/png")}, headers=admin_headers)).json()["data"]
    await client.put(f"{CMS}/site", json={"logo_url": media["url"]}, headers=admin_headers)

    response = await client.delete(f"{CMS}/media/{media['id']}", headers=admin_headers)

    assert response.status_code == 409
