"""Storefront: what the public can see, search and sort."""

from __future__ import annotations

import pytest

from tests.catalogue.factories import (
    CATEGORIES,
    PRODUCTS,
    STOREFRONT,
    make_category,
    make_product,
)


async def test_an_active_product_is_public(client, publish):
    product = await publish(name="Live Shirt")

    response = await client.get(f"{STOREFRONT}/products/{product['id']}")

    assert response.status_code == 200


async def test_a_draft_product_is_not_public(client, admin_headers, category):
    draft = await make_product(client, admin_headers, category["id"], name="Draft")

    response = await client.get(f"{STOREFRONT}/products/{draft['id']}")

    assert response.status_code == 404


async def test_an_archived_product_disappears(client, admin_headers, publish):
    product = await publish(name="Soon Gone")
    await client.delete(f"{PRODUCTS}/{product['id']}", headers=admin_headers)

    response = await client.get(f"{STOREFRONT}/products/{product['id']}")

    assert response.status_code == 404


async def test_archiving_a_category_hides_it(client, admin_headers, publish):
    seasonal = await make_category(client, admin_headers, name="Seasonal")
    product = await publish(name="Seasonal Coat", category=seasonal)
    await client.delete(f"{PRODUCTS}/{product['id']}", headers=admin_headers)
    await client.delete(f"{CATEGORIES}/{seasonal['id']}", headers=admin_headers)

    response = await client.get(f"{STOREFRONT}/categories/{seasonal['id']}")

    assert response.status_code == 404


async def test_the_storefront_needs_no_authentication(client, publish):
    await publish(name="Public Item")

    response = await client.get(f"{STOREFRONT}/products")

    assert response.status_code == 200


async def test_internal_fields_are_never_exposed(client, publish):
    product = await publish(name="Clean Payload")

    response = await client.get(f"{STOREFRONT}/products/{product['id']}")

    body = response.json()["data"]
    for field in ("tenant_id", "status", "created_at", "updated_at"):
        assert field not in body


async def test_product_detail_carries_options_variants_and_stock(client, publish):
    product = await publish(
        name="Option Tee",
        quantity=3,
        options=[{"name": "Color", "value": "Black"}, {"name": "Size", "value": "M"}],
    )

    response = await client.get(f"{STOREFRONT}/products/{product['id']}")

    body = response.json()["data"]
    assert body["category"]["name"]
    assert body["options"] == [
        {"name": "Color", "values": ["Black"]},
        {"name": "Size", "values": ["M"]},
    ]
    assert body["variants"][0]["available_quantity"] == 3
    assert body["in_stock"] is True


async def test_a_product_with_no_stock_reports_out_of_stock(client, publish):
    product = await publish(name="Sold Out", quantity=0)

    response = await client.get(f"{STOREFRONT}/products/{product['id']}")

    assert response.json()["data"]["in_stock"] is False


async def test_the_listing_is_lightweight(client, publish):
    await publish(name="Grid Item")

    response = await client.get(f"{STOREFRONT}/products")

    row = response.json()["data"][0]
    assert "primary_image" in row
    assert "price_from" in row
    assert "variants" not in row
    assert "images" not in row


async def test_featured_products_can_be_filtered(client, publish):
    await publish(name="Plain One", is_featured=False)
    await publish(name="Hero One", is_featured=True)

    response = await client.get(f"{STOREFRONT}/products", params={"featured": "true"})

    body = response.json()
    assert body["meta"]["total_items"] == 1
    assert body["data"][0]["name"] == "Hero One"


async def test_products_can_be_searched_by_name(client, publish):
    await publish(name="Merino Scarf")
    await publish(name="Cotton Cap")

    response = await client.get(f"{STOREFRONT}/products", params={"search": "merino"})

    assert [p["name"] for p in response.json()["data"]] == ["Merino Scarf"]


async def test_products_can_be_searched_by_brand(client, publish):
    await publish(name="Merino Scarf", brand="Zeen")
    await publish(name="Cotton Cap", brand="Northbound")

    response = await client.get(
        f"{STOREFRONT}/products", params={"search": "northbound"}
    )

    assert [p["name"] for p in response.json()["data"]] == ["Cotton Cap"]


async def test_a_search_wildcard_is_not_a_pattern(client, publish):
    await publish(name="Regular Item")

    response = await client.get(f"{STOREFRONT}/products", params={"search": "%"})

    assert response.status_code == 200
    assert response.json()["meta"]["total_items"] == 0


async def test_products_can_be_filtered_by_maximum_price(client, publish):
    await publish(name="Cheap", price="100.00")
    await publish(name="Pricey", price="5000.00")

    response = await client.get(
        f"{STOREFRONT}/products", params={"max_price": "1000"}
    )

    assert [p["name"] for p in response.json()["data"]] == ["Cheap"]


async def test_products_can_be_filtered_by_minimum_price(client, publish):
    await publish(name="Cheap", price="100.00")
    await publish(name="Pricey", price="5000.00")

    response = await client.get(f"{STOREFRONT}/products", params={"min_price": "1000"})

    assert [p["name"] for p in response.json()["data"]] == ["Pricey"]


@pytest.mark.parametrize(
    ("sort", "expected"),
    [
        ("price_low", ["Alpha", "Beta"]),
        ("price_high", ["Beta", "Alpha"]),
        ("name_asc", ["Alpha", "Beta"]),
        ("name_desc", ["Beta", "Alpha"]),
    ],
)
async def test_products_can_be_sorted(client, publish, sort, expected):
    await publish(name="Alpha", price="100.00")
    await publish(name="Beta", price="900.00")

    response = await client.get(f"{STOREFRONT}/products", params={"sort": sort})

    assert [p["name"] for p in response.json()["data"]] == expected


async def test_an_unknown_sort_is_rejected(client, tenant):
    response = await client.get(f"{STOREFRONT}/products", params={"sort": "'; DROP--"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_the_listing_paginates(client, publish):
    for index in range(5):
        await publish(name=f"Item {index}")

    response = await client.get(
        f"{STOREFRONT}/products", params={"page": 2, "page_size": 2, "sort": "name_asc"}
    )

    body = response.json()
    assert body["meta"]["total_items"] == 5
    assert body["meta"]["total_pages"] == 3
    assert [p["name"] for p in body["data"]] == ["Item 2", "Item 3"]


async def test_each_hostname_serves_its_own_tenant(
    client, other_client, other_admin_headers, publish
):
    await publish(name="Zeen Only")
    other_category = await make_category(other_client, other_admin_headers)
    await make_product(
        other_client,
        other_admin_headers,
        other_category["id"],
        name="Acme Only",
        status="ACTIVE",
    )

    response = await client.get(f"{STOREFRONT}/products")

    assert [p["name"] for p in response.json()["data"]] == ["Zeen Only"]


async def test_a_product_id_from_another_tenant_is_not_found(other_client, publish):
    product = await publish(name="Zeen Private")

    response = await other_client.get(f"{STOREFRONT}/products/{product['id']}")

    assert response.status_code == 404


async def test_an_unknown_query_parameter_is_rejected(client, tenant):
    response = await client.get(f"{STOREFRONT}/products?page=1&limit=1000")

    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == "limit"


async def test_a_page_size_above_the_maximum_is_rejected(client, tenant):
    response = await client.get(f"{STOREFRONT}/products?page=1&page_size=1000")

    assert response.status_code == 422
