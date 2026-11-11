"""SEO-friendly product URLs."""

from __future__ import annotations

from tests.catalogue.factories import CATEGORIES, PRODUCTS, STOREFRONT, make_product


async def test_a_slug_is_made_from_the_name(client, admin_headers, category):
    product = await make_product(client, admin_headers, category["id"], name="Café Señora – Silk Kurta!")

    assert product["slug"] == "cafe-senora-silk-kurta"


async def test_duplicate_names_get_numbered_slugs(client, admin_headers, category):
    first = await make_product(client, admin_headers, category["id"], name="Cotton Kurta")
    second = await make_product(client, admin_headers, category["id"], name="Cotton Kurta")
    third = await make_product(client, admin_headers, category["id"], name="cotton  kurta")

    assert [first["slug"], second["slug"], third["slug"]] == [
        "cotton-kurta",
        "cotton-kurta-2",
        "cotton-kurta-3",
    ]


async def test_a_name_without_letters_still_gets_a_slug(client, admin_headers, category):
    product = await make_product(client, admin_headers, category["id"], name="★★★")

    assert product["slug"] == "product"


async def test_a_chosen_slug_is_kept_and_must_be_free(client, admin_headers, category):
    chosen = await make_product(client, admin_headers, category["id"], slug="festive-edit")
    clash = await client.post(
        PRODUCTS,
        json={"category_id": category["id"], "name": "Other", "slug": "festive-edit",
              "images": [{"url": "https://cdn.example.com/x.jpg"}]},
        headers=admin_headers,
    )

    assert chosen["slug"] == "festive-edit"
    assert clash.status_code == 409
    assert clash.json()["error"]["code"] == "SLUG_TAKEN"


async def test_unsafe_slugs_are_rejected(client, admin_headers, category):
    response = await client.post(
        PRODUCTS,
        json={"category_id": category["id"], "name": "X", "slug": "Bad Slug/../",
              "images": [{"url": "https://cdn.example.com/x.jpg"}]},
        headers=admin_headers,
    )

    assert response.status_code == 422


async def test_renaming_keeps_the_slug_and_the_slug_can_be_changed(client, admin_headers, category):
    product = await make_product(client, admin_headers, category["id"], name="Old Name")
    other = await make_product(client, admin_headers, category["id"], name="Taken")

    renamed = await client.patch(f"{PRODUCTS}/{product['id']}", json={"name": "New Name"}, headers=admin_headers)
    reslugged = await client.patch(f"{PRODUCTS}/{product['id']}", json={"slug": "new-name"}, headers=admin_headers)
    clash = await client.patch(f"{PRODUCTS}/{product['id']}", json={"slug": other["slug"]}, headers=admin_headers)
    same = await client.patch(f"{PRODUCTS}/{product['id']}", json={"slug": "new-name"}, headers=admin_headers)

    assert renamed.json()["data"]["slug"] == "old-name"
    assert reslugged.json()["data"]["slug"] == "new-name"
    assert clash.status_code == 409
    assert same.status_code == 200


async def test_the_storefront_finds_live_products_by_slug(client, admin_headers, category):
    live = await make_product(client, admin_headers, category["id"], name="Live Kurta", status="ACTIVE")
    draft = await make_product(client, admin_headers, category["id"], name="Draft Kurta")

    found = await client.get(f"{STOREFRONT}/products/by-slug/{live['slug']}")
    hidden = await client.get(f"{STOREFRONT}/products/by-slug/{draft['slug']}")
    by_id = await client.get(f"{STOREFRONT}/products/{live['id']}")
    listing = await client.get(f"{STOREFRONT}/products")

    assert found.json()["data"]["id"] == live["id"]
    assert hidden.status_code == 404
    assert by_id.json()["data"]["slug"] == "live-kurta"
    assert listing.json()["data"][0]["slug"] == "live-kurta"


async def test_slugs_are_per_store(client, other_client, admin_headers, other_admin_headers, category):
    ours = await make_product(client, admin_headers, category["id"], name="Same Name", status="ACTIVE")
    other_category = (
        await other_client.post(CATEGORIES, json={"name": "Acme"}, headers=other_admin_headers)
    ).json()["data"]
    theirs = await make_product(other_client, other_admin_headers, other_category["id"], name="Same Name")

    from_other_store = await other_client.get(f"{STOREFRONT}/products/by-slug/{ours['slug']}")

    assert ours["slug"] == theirs["slug"] == "same-name"
    assert from_other_store.status_code == 404
