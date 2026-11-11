"""Catalogue CRUD: categories, products and variants."""

from __future__ import annotations

import pytest

from tests.catalogue.factories import (
    CATEGORIES,
    IMAGE,
    PRODUCTS,
    VARIANTS,
    make_category,
    make_product,
    make_variant,
)

UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"


async def test_a_category_can_be_created(category):
    assert category["name"] == "Dresses"
    assert category["status"] == "ACTIVE"


async def test_a_category_can_be_retrieved(client, admin_headers, category):
    response = await client.get(
        f"{CATEGORIES}/{category['id']}", headers=admin_headers
    )

    assert response.status_code == 200
    assert response.json()["data"]["id"] == category["id"]


async def test_a_category_can_be_updated(client, admin_headers, category):
    response = await client.patch(
        f"{CATEGORIES}/{category['id']}",
        json={"name": "Gowns", "status": "DRAFT"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["name"] == "Gowns"
    assert body["status"] == "DRAFT"


async def test_an_empty_patch_is_rejected(client, admin_headers, category):
    response = await client.patch(
        f"{CATEGORIES}/{category['id']}", json={}, headers=admin_headers
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_an_unknown_field_is_rejected(client, admin_headers):
    response = await client.post(
        CATEGORIES,
        json={"name": "Coats", "unknown_field": "some value"},
        headers=admin_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == "unknown_field"


async def test_an_unknown_query_parameter_is_rejected(client, admin_headers):
    response = await client.get(f"{CATEGORIES}?limit=5", headers=admin_headers)

    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == "limit"


async def test_a_non_integer_page_size_is_rejected(client, admin_headers):
    response = await client.get(f"{CATEGORIES}?page_size=hy", headers=admin_headers)

    assert response.status_code == 422


async def test_a_page_size_out_of_range_is_rejected(client, admin_headers):
    response = await client.get(f"{CATEGORIES}?page_size=-5", headers=admin_headers)

    assert response.status_code == 422


async def test_deleting_a_category_twice_is_a_404(client, admin_headers, category):
    await client.delete(f"{CATEGORIES}/{category['id']}", headers=admin_headers)

    response = await client.delete(
        f"{CATEGORIES}/{category['id']}", headers=admin_headers
    )

    assert response.status_code == 404


async def test_deleting_a_category_archives_it(client, admin_headers, category):
    """Archived products keep a foreign key to their category, so the row stays."""
    response = await client.delete(
        f"{CATEGORIES}/{category['id']}", headers=admin_headers
    )

    assert response.status_code == 204
    after = await client.get(f"{CATEGORIES}/{category['id']}", headers=admin_headers)
    assert after.json()["data"]["status"] == "ARCHIVED"


async def test_a_category_with_live_products_cannot_be_deleted(
    client, admin_headers, category, product
):
    response = await client.delete(
        f"{CATEGORIES}/{category['id']}", headers=admin_headers
    )

    assert response.status_code == 409
    assert "products" in response.json()["message"].lower()


async def test_a_category_of_archived_products_can_be_deleted(
    client, admin_headers, category, product
):
    await client.delete(f"{PRODUCTS}/{product['id']}", headers=admin_headers)

    response = await client.delete(
        f"{CATEGORIES}/{category['id']}", headers=admin_headers
    )

    assert response.status_code == 204


async def test_an_unknown_category_is_a_404(client, admin_headers, tenant):
    response = await client.get(f"{CATEGORIES}/{UNKNOWN_ID}", headers=admin_headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CATEGORY_NOT_FOUND"


@pytest.mark.parametrize("payload", [{"name": ""}, {"name": "   "}])
async def test_an_invalid_category_update_is_rejected(
    client, admin_headers, category, payload
):
    response = await client.patch(
        f"{CATEGORIES}/{category['id']}", json=payload, headers=admin_headers
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "payload", [{"name": ""}, {"name": "   "}, {"name": "x" * 200}, {}]
)
async def test_an_invalid_category_payload_is_rejected(
    client, admin_headers, tenant, payload
):
    response = await client.post(CATEGORIES, json=payload, headers=admin_headers)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_a_product_can_be_created(product, category):
    assert product["category_id"] == category["id"]
    assert product["status"] == "ACTIVE"


async def test_a_product_can_be_retrieved(client, admin_headers, product):
    response = await client.get(f"{PRODUCTS}/{product['id']}", headers=admin_headers)

    assert response.status_code == 200


async def test_a_product_needs_an_existing_category(client, admin_headers, tenant):
    response = await client.post(
        PRODUCTS,
        json={"category_id": UNKNOWN_ID, "name": "Orphan", "images": [IMAGE]},
        headers=admin_headers,
    )

    assert response.status_code == 404
    assert response.json()["message"] == "Category not found"


async def test_a_product_can_change_status_and_category(
    client, admin_headers, product
):
    other = await make_category(client, admin_headers, name="Skirts")

    response = await client.patch(
        f"{PRODUCTS}/{product['id']}",
        json={"status": "DRAFT", "category_id": other["id"]},
        headers=admin_headers,
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["status"] == "DRAFT"
    assert body["category_id"] == other["id"]


async def test_a_product_cannot_move_to_an_unknown_category(
    client, admin_headers, product
):
    response = await client.patch(
        f"{PRODUCTS}/{product['id']}",
        json={"category_id": UNKNOWN_ID},
        headers=admin_headers,
    )

    assert response.status_code == 404


async def test_an_invalid_status_is_rejected(client, admin_headers, category):
    response = await client.post(
        PRODUCTS,
        json={
            "category_id": category["id"],
            "name": "Bad",
            "images": [IMAGE],
            "status": "ON_FIRE",
        },
        headers=admin_headers,
    )

    assert response.status_code == 422


async def test_products_can_be_filtered_by_category(client, admin_headers, product):
    skirts = await make_category(client, admin_headers, name="Skirts")
    await make_product(client, admin_headers, skirts["id"], name="Midi")

    response = await client.get(
        PRODUCTS, params={"category_id": skirts["id"]}, headers=admin_headers
    )

    body = response.json()
    assert body["meta"]["total_items"] == 1
    assert body["data"][0]["name"] == "Midi"


async def test_deleting_a_product_archives_it_and_its_variants(
    client, admin_headers, product, variant
):
    response = await client.delete(f"{PRODUCTS}/{product['id']}", headers=admin_headers)

    assert response.status_code == 204
    after = await client.get(f"{VARIANTS}/{variant['id']}", headers=admin_headers)
    assert after.json()["data"]["status"] == "ARCHIVED"


async def test_deleting_a_product_twice_is_a_404(client, admin_headers, product):
    await client.delete(f"{PRODUCTS}/{product['id']}", headers=admin_headers)

    response = await client.delete(f"{PRODUCTS}/{product['id']}", headers=admin_headers)

    assert response.status_code == 404


async def test_a_product_cannot_be_created_without_images(
    client, admin_headers, category
):
    response = await client.post(
        PRODUCTS,
        json={"category_id": category["id"], "name": "No Artwork"},
        headers=admin_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_a_product_cannot_be_created_with_an_empty_image_list(
    client, admin_headers, category
):
    response = await client.post(
        PRODUCTS,
        json={"category_id": category["id"], "name": "No Artwork", "images": []},
        headers=admin_headers,
    )

    assert response.status_code == 422


async def test_images_are_stored_with_the_product(client, admin_headers, category):
    response = await client.post(
        PRODUCTS,
        json={
            "category_id": category["id"],
            "name": "Two Images",
            "images": [
                {"url": "https://cdn.example.com/a.jpg", "sort_order": 0},
                {"url": "https://cdn.example.com/b.jpg", "sort_order": 1},
            ],
        },
        headers=admin_headers,
    )

    assert response.status_code == 201
    images = response.json()["data"]["images"]
    assert [image["url"] for image in images] == [
        "https://cdn.example.com/a.jpg",
        "https://cdn.example.com/b.jpg",
    ]
    assert [image["is_primary"] for image in images] == [True, False]


async def test_only_one_image_may_be_marked_primary(client, admin_headers, category):
    response = await client.post(
        PRODUCTS,
        json={
            "category_id": category["id"],
            "name": "Two Primaries",
            "images": [
                {"url": "https://cdn.example.com/a.jpg", "is_primary": True},
                {"url": "https://cdn.example.com/b.jpg", "is_primary": True},
            ],
        },
        headers=admin_headers,
    )

    assert response.status_code == 422


async def test_a_variant_can_be_created(client, admin_headers, product):
    created = await make_variant(client, admin_headers, product["id"])

    assert created["product_id"] == product["id"]
    assert created["sku"] == "DRESS-S-BLK"


async def test_a_sku_is_uppercased_before_it_is_stored(
    client, admin_headers, product
):
    created = await make_variant(
        client, admin_headers, product["id"], sku="dress-m-blk"
    )

    assert created["sku"] == "DRESS-M-BLK"


async def test_sku_uniqueness_ignores_case(client, admin_headers, product):
    await make_variant(client, admin_headers, product["id"], sku="DRESS-S-BLK")

    response = await client.post(
        f"{PRODUCTS}/{product['id']}/variants",
        json={"sku": "dress-s-blk", "name": "Same", "price": "10.00"},
        headers=admin_headers,
    )

    assert response.status_code == 409


async def test_a_sku_is_unique_across_the_whole_tenant(
    client, admin_headers, category, product
):
    await make_variant(client, admin_headers, product["id"], sku="SHARED-1")
    other = await make_product(client, admin_headers, category["id"], name="Other")

    response = await client.post(
        f"{PRODUCTS}/{other['id']}/variants",
        json={"sku": "SHARED-1", "name": "Clash", "price": "10.00"},
        headers=admin_headers,
    )

    assert response.status_code == 409


async def test_a_variant_needs_an_existing_product(client, admin_headers, tenant):
    response = await client.post(
        f"{PRODUCTS}/{UNKNOWN_ID}/variants",
        json={"sku": "ORPHAN-1", "name": "Orphan", "price": "10.00"},
        headers=admin_headers,
    )

    assert response.status_code == 404


@pytest.mark.parametrize("price", ["-1.00", "-0.01"])
async def test_a_negative_price_is_rejected(client, admin_headers, product, price):
    response = await client.post(
        f"{PRODUCTS}/{product['id']}/variants",
        json={"sku": "NEG-1", "name": "Negative", "price": price},
        headers=admin_headers,
    )

    assert response.status_code == 422


async def test_a_price_may_be_zero(client, admin_headers, product):
    created = await make_variant(client, admin_headers, product["id"], price="0.00")

    assert created["price"] == "0.00"


async def test_too_many_decimal_places_is_rejected(client, admin_headers, product):
    response = await client.post(
        f"{PRODUCTS}/{product['id']}/variants",
        json={"sku": "DEC-1", "name": "Fractional", "price": "10.999"},
        headers=admin_headers,
    )

    assert response.status_code == 422


async def test_a_variant_can_be_updated(client, admin_headers, variant):
    response = await client.patch(
        f"{VARIANTS}/{variant['id']}",
        json={"price": "59.50", "status": "ACTIVE"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["price"] == "59.50"
    assert body["status"] == "ACTIVE"


async def test_deleting_a_variant_archives_it(client, admin_headers, variant):
    response = await client.delete(f"{VARIANTS}/{variant['id']}", headers=admin_headers)

    assert response.status_code == 204
    after = await client.get(f"{VARIANTS}/{variant['id']}", headers=admin_headers)
    assert after.json()["data"]["status"] == "ARCHIVED"


async def test_deleting_a_variant_twice_is_a_404(client, admin_headers, variant):
    await client.delete(f"{VARIANTS}/{variant['id']}", headers=admin_headers)

    response = await client.delete(f"{VARIANTS}/{variant['id']}", headers=admin_headers)

    assert response.status_code == 404


async def test_an_archived_product_cannot_take_new_variants(
    client, admin_headers, product
):
    await client.delete(f"{PRODUCTS}/{product['id']}", headers=admin_headers)

    response = await client.post(
        f"{PRODUCTS}/{product['id']}/variants",
        json={"sku": "LATE-1", "name": "Too Late", "price": "10.00"},
        headers=admin_headers,
    )

    assert response.status_code == 409


async def test_categories_are_paginated(client, admin_headers, tenant):
    for index in range(5):
        await make_category(client, admin_headers, name=f"C{index}")

    response = await client.get(
        CATEGORIES, params={"page": 2, "page_size": 2}, headers=admin_headers
    )

    body = response.json()
    assert body["meta"]["total_items"] == 5
    assert len(body["data"]) == 2


async def test_products_are_paginated(client, admin_headers, category):
    for index in range(5):
        await make_product(client, admin_headers, category["id"], name=f"P{index}")

    response = await client.get(
        PRODUCTS, params={"page": 2, "page_size": 2}, headers=admin_headers
    )

    body = response.json()
    assert body["meta"]["total_items"] == 5
    assert len(body["data"]) == 2


async def test_variants_are_paginated(client, admin_headers, product, new_variant):
    for _ in range(3):
        await new_variant()

    response = await client.get(
        f"{PRODUCTS}/{product['id']}/variants",
        params={"page": 1, "page_size": 2},
        headers=admin_headers,
    )

    body = response.json()
    assert body["meta"]["total_items"] == 3
    assert len(body["data"]) == 2


async def test_the_page_size_ceiling_is_enforced(client, admin_headers, tenant):
    response = await client.get(
        CATEGORIES, params={"page_size": 1000}, headers=admin_headers
    )

    assert response.status_code == 422


async def test_a_filtered_total_reflects_the_filter(client, admin_headers, product):
    skirts = await make_category(client, admin_headers, name="Skirts")
    await make_product(client, admin_headers, skirts["id"], name="Midi")

    response = await client.get(
        PRODUCTS, params={"category_id": skirts["id"]}, headers=admin_headers
    )

    assert response.json()["meta"]["total_items"] == 1
