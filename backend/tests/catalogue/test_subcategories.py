"""Sub-categories: building the tree, keeping it sound, and listing by it."""

from __future__ import annotations

from tests.catalogue.factories import (
    CATEGORIES,
    PRODUCTS,
    STOREFRONT,
    make_category,
    make_product,
)

UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"


async def test_a_category_is_top_level_by_default(category):
    assert category["parent_id"] is None


async def test_a_sub_category_records_its_parent(client, admin_headers, category):
    child = await make_category(
        client, admin_headers, name="Maxi Dresses", parent_id=category["id"]
    )

    response = await client.get(f"{CATEGORIES}/{child['id']}", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["data"]["parent_id"] == category["id"]


async def test_sub_categories_can_nest_several_levels(client, admin_headers, category):
    child = await make_category(
        client, admin_headers, name="Party Dresses", parent_id=category["id"]
    )
    grandchild = await make_category(
        client, admin_headers, name="Sequin Dresses", parent_id=child["id"]
    )

    assert grandchild["parent_id"] == child["id"]


async def test_an_unknown_parent_is_rejected(client, admin_headers):
    response = await client.post(
        CATEGORIES,
        json={"name": "Orphan", "parent_id": UNKNOWN_ID},
        headers=admin_headers,
    )

    assert response.status_code == 404


async def test_an_archived_parent_cannot_take_sub_categories(client, admin_headers):
    retired = await make_category(client, admin_headers, name="Retired")
    await client.delete(f"{CATEGORIES}/{retired['id']}", headers=admin_headers)

    response = await client.post(
        CATEGORIES,
        json={"name": "Late Child", "parent_id": retired["id"]},
        headers=admin_headers,
    )

    assert response.status_code == 409


async def test_another_tenants_category_cannot_be_a_parent(
    other_client, other_admin_headers, category
):
    response = await other_client.post(
        CATEGORIES,
        json={"name": "Intruder", "parent_id": category["id"]},
        headers=other_admin_headers,
    )

    assert response.status_code == 404


async def test_a_category_can_be_moved_under_another(client, admin_headers, category):
    loose = await make_category(client, admin_headers, name="Kurtas")

    response = await client.patch(
        f"{CATEGORIES}/{loose['id']}",
        json={"parent_id": category["id"]},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["data"]["parent_id"] == category["id"]


async def test_a_sub_category_can_be_moved_back_to_the_top(
    client, admin_headers, category
):
    child = await make_category(
        client, admin_headers, name="Midi Dresses", parent_id=category["id"]
    )

    response = await client.patch(
        f"{CATEGORIES}/{child['id']}", json={"parent_id": None}, headers=admin_headers
    )

    assert response.status_code == 200
    assert response.json()["data"]["parent_id"] is None


async def test_a_category_cannot_be_its_own_parent(client, admin_headers, category):
    response = await client.patch(
        f"{CATEGORIES}/{category['id']}",
        json={"parent_id": category["id"]},
        headers=admin_headers,
    )

    assert response.status_code == 409


async def test_a_category_cannot_move_under_its_own_descendant(
    client, admin_headers, category
):
    child = await make_category(
        client, admin_headers, name="Gowns", parent_id=category["id"]
    )
    grandchild = await make_category(
        client, admin_headers, name="Ball Gowns", parent_id=child["id"]
    )

    response = await client.patch(
        f"{CATEGORIES}/{category['id']}",
        json={"parent_id": grandchild["id"]},
        headers=admin_headers,
    )

    assert response.status_code == 409


async def test_a_category_with_live_sub_categories_cannot_be_archived(
    client, admin_headers, category
):
    await make_category(client, admin_headers, name="Wrap Dresses", parent_id=category["id"])

    response = await client.delete(f"{CATEGORIES}/{category['id']}", headers=admin_headers)

    assert response.status_code == 409


async def test_a_parent_can_be_archived_once_its_children_are(
    client, admin_headers, category
):
    child = await make_category(
        client, admin_headers, name="Shift Dresses", parent_id=category["id"]
    )
    await client.delete(f"{CATEGORIES}/{child['id']}", headers=admin_headers)

    response = await client.delete(f"{CATEGORIES}/{category['id']}", headers=admin_headers)

    assert response.status_code == 204


async def test_admin_listing_can_show_only_the_children_of_a_category(
    client, admin_headers, category
):
    child = await make_category(
        client, admin_headers, name="Bodycon Dresses", parent_id=category["id"]
    )
    await make_category(client, admin_headers, name="Unrelated")

    response = await client.get(
        CATEGORIES, params={"parent_id": category["id"]}, headers=admin_headers
    )

    assert [c["id"] for c in response.json()["data"]] == [child["id"]]


async def test_admin_listing_can_show_only_top_level_categories(
    client, admin_headers, category
):
    await make_category(client, admin_headers, name="Slip Dresses", parent_id=category["id"])

    response = await client.get(CATEGORIES, params={"top_level": True}, headers=admin_headers)

    assert [c["id"] for c in response.json()["data"]] == [category["id"]]


async def test_storefront_exposes_the_tree(client, admin_headers, category):
    child = await make_category(
        client, admin_headers, name="Sundresses", parent_id=category["id"]
    )

    listed = await client.get(f"{STOREFRONT}/categories", params={"parent_id": category["id"]})
    detail = await client.get(f"{STOREFRONT}/categories/{child['id']}")

    assert [c["id"] for c in listed.json()["data"]] == [child["id"]]
    assert detail.json()["data"]["parent_id"] == category["id"]


async def test_filtering_by_a_category_includes_its_sub_categories(
    client, admin_headers, category
):
    child = await make_category(
        client, admin_headers, name="Evening Dresses", parent_id=category["id"]
    )
    grandchild = await make_category(
        client, admin_headers, name="Cocktail Dresses", parent_id=child["id"]
    )
    in_parent = await make_product(client, admin_headers, category["id"], name="Parent Dress")
    in_grandchild = await make_product(
        client, admin_headers, grandchild["id"], name="Grandchild Dress"
    )
    elsewhere = await make_category(client, admin_headers, name="Shoes")
    await make_product(client, admin_headers, elsewhere["id"], name="Loafer")

    parent_listing = await client.get(
        PRODUCTS, params={"category_id": category["id"]}, headers=admin_headers
    )
    child_listing = await client.get(
        PRODUCTS, params={"category_id": child["id"]}, headers=admin_headers
    )

    assert {p["id"] for p in parent_listing.json()["data"]} == {
        in_parent["id"],
        in_grandchild["id"],
    }
    assert [p["id"] for p in child_listing.json()["data"]] == [in_grandchild["id"]]


async def test_storefront_category_filter_includes_sub_categories(
    client, admin_headers, category, publish
):
    child = await make_category(
        client, admin_headers, name="Beach Dresses", parent_id=category["id"]
    )
    product = await publish(name="Beach Dress", category=child)

    response = await client.get(
        f"{STOREFRONT}/products", params={"category_id": category["id"]}
    )

    assert product["id"] in {p["id"] for p in response.json()["data"]}
