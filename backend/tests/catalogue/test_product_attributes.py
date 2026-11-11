"""Fabric, occasion, sleeve and neckline: stored on products and filterable."""

from __future__ import annotations

import pytest

from tests.catalogue.factories import PRODUCTS, STOREFRONT, make_product

ATTRIBUTES = {
    "fabric": "Cotton",
    "occasion": "Festive",
    "sleeve": "Full Sleeve",
    "neckline": "V-Neck",
}


async def test_a_product_stores_its_attributes(client, admin_headers, category):
    product = await make_product(
        client, admin_headers, category["id"], name="Festive Kurta", **ATTRIBUTES
    )

    response = await client.get(f"{PRODUCTS}/{product['id']}", headers=admin_headers)

    body = response.json()["data"]
    for field, value in ATTRIBUTES.items():
        assert body[field] == value


async def test_attributes_are_optional(product):
    for field in ATTRIBUTES:
        assert product[field] is None


async def test_attributes_are_trimmed_and_blank_means_unset(
    client, admin_headers, category
):
    product = await make_product(
        client, admin_headers, category["id"], fabric="  Linen  ", sleeve="   "
    )

    assert product["fabric"] == "Linen"
    assert product["sleeve"] is None


async def test_an_overlong_attribute_is_rejected(client, admin_headers, category):
    response = await client.post(
        PRODUCTS,
        json={
            "category_id": category["id"],
            "name": "Too Long",
            "fabric": "x" * 101,
            "images": [{"url": "https://cdn.example.com/a.jpg"}],
        },
        headers=admin_headers,
    )

    assert response.status_code == 422


async def test_attributes_can_be_updated_and_cleared(client, admin_headers, category):
    product = await make_product(client, admin_headers, category["id"], **ATTRIBUTES)

    response = await client.patch(
        f"{PRODUCTS}/{product['id']}",
        json={"occasion": "Casual", "neckline": None},
        headers=admin_headers,
    )

    body = response.json()["data"]
    assert response.status_code == 200
    assert body["occasion"] == "Casual"
    assert body["neckline"] is None
    assert body["fabric"] == ATTRIBUTES["fabric"]


@pytest.mark.parametrize("field", list(ATTRIBUTES))
async def test_admin_listing_filters_by_each_attribute(
    client, admin_headers, category, field
):
    match = await make_product(client, admin_headers, category["id"], **ATTRIBUTES)
    await make_product(client, admin_headers, category["id"], **{field: "Something Else"})
    await make_product(client, admin_headers, category["id"])

    response = await client.get(
        PRODUCTS, params={field: ATTRIBUTES[field]}, headers=admin_headers
    )

    assert [p["id"] for p in response.json()["data"]] == [match["id"]]


async def test_attribute_filters_ignore_case(client, admin_headers, category):
    match = await make_product(client, admin_headers, category["id"], fabric="Silk")

    response = await client.get(PRODUCTS, params={"fabric": "sILK"}, headers=admin_headers)

    assert [p["id"] for p in response.json()["data"]] == [match["id"]]


async def test_attribute_filters_combine(client, admin_headers, category):
    match = await make_product(client, admin_headers, category["id"], **ATTRIBUTES)
    await make_product(
        client, admin_headers, category["id"], **{**ATTRIBUTES, "sleeve": "Sleeveless"}
    )

    response = await client.get(
        PRODUCTS,
        params={"fabric": "Cotton", "sleeve": "Full Sleeve"},
        headers=admin_headers,
    )

    assert [p["id"] for p in response.json()["data"]] == [match["id"]]


async def test_storefront_listing_filters_and_shows_attributes(client, publish):
    match = await publish(name="Cotton Festive Kurta", **ATTRIBUTES)
    await publish(name="Silk Party Kurta", fabric="Silk", occasion="Party")

    response = await client.get(
        f"{STOREFRONT}/products", params={"fabric": "cotton", "occasion": "festive"}
    )

    rows = response.json()["data"]
    assert [p["id"] for p in rows] == [match["id"]]
    for field, value in ATTRIBUTES.items():
        assert rows[0][field] == value


async def test_storefront_detail_shows_attributes(client, publish):
    product = await publish(name="Detail Kurta", **ATTRIBUTES)

    response = await client.get(f"{STOREFRONT}/products/{product['id']}")

    body = response.json()["data"]
    for field, value in ATTRIBUTES.items():
        assert body[field] == value
