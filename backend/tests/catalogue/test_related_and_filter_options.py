"""Related products and the filter-dropdown values endpoint."""

from __future__ import annotations

from tests.catalogue.factories import PRODUCTS, STOREFRONT, make_category, make_product


async def test_an_admin_sets_related_products_in_order(client, admin_headers, category):
    main = await make_product(client, admin_headers, category["id"], name="Main")
    first = await make_product(client, admin_headers, category["id"], name="First")
    second = await make_product(client, admin_headers, category["id"], name="Second")

    response = await client.put(
        f"{PRODUCTS}/{main['id']}/related",
        json={"product_ids": [second["id"], first["id"]]},
        headers=admin_headers,
    )
    listed = await client.get(f"{PRODUCTS}/{main['id']}/related", headers=admin_headers)

    assert response.status_code == 200
    assert [p["id"] for p in listed.json()["data"]] == [second["id"], first["id"]]


async def test_a_product_cannot_be_related_to_itself(client, admin_headers, product):
    response = await client.put(
        f"{PRODUCTS}/{product['id']}/related",
        json={"product_ids": [product["id"]]},
        headers=admin_headers,
    )

    assert response.status_code == 400


async def test_an_unknown_related_product_is_rejected(client, admin_headers, product):
    response = await client.put(
        f"{PRODUCTS}/{product['id']}/related",
        json={"product_ids": ["00000000-0000-0000-0000-000000000000"]},
        headers=admin_headers,
    )

    assert response.status_code == 404


async def test_duplicate_related_products_are_rejected(client, admin_headers, category, product):
    other = await make_product(client, admin_headers, category["id"])

    response = await client.put(
        f"{PRODUCTS}/{product['id']}/related",
        json={"product_ids": [other["id"], other["id"]]},
        headers=admin_headers,
    )

    assert response.status_code == 422


async def test_staff_may_read_but_not_set_related(client, staff_headers, product):
    read = await client.get(f"{PRODUCTS}/{product['id']}/related", headers=staff_headers)
    write = await client.put(
        f"{PRODUCTS}/{product['id']}/related", json={"product_ids": []}, headers=staff_headers
    )

    assert read.status_code == 200
    assert write.status_code == 403


async def test_storefront_related_puts_hand_picked_first_then_same_category(
    client, admin_headers, publish
):
    main = await publish(name="Rel Main")
    picked = await publish(name="Rel Picked")
    filler = await publish(name="Rel Filler")
    await client.put(
        f"{PRODUCTS}/{main['id']}/related",
        json={"product_ids": [picked["id"]]},
        headers=admin_headers,
    )

    response = await client.get(f"{STOREFRONT}/products/{main['id']}/related", params={"limit": 2})

    liked = [p["id"] for p in response.json()["data"]["you_may_also_like"]]
    assert liked[0] == picked["id"]
    assert filler["id"] in liked
    assert main["id"] not in liked


async def test_storefront_related_hides_draft_products(client, admin_headers, category, publish):
    main = await publish(name="Rel Visible")
    draft = await make_product(client, admin_headers, category["id"], name="Rel Draft")
    await client.put(
        f"{PRODUCTS}/{main['id']}/related",
        json={"product_ids": [draft["id"]]},
        headers=admin_headers,
    )

    response = await client.get(f"{STOREFRONT}/products/{main['id']}/related")

    ids = [p["id"] for p in response.json()["data"]["you_may_also_like"]]
    assert draft["id"] not in ids


async def test_filter_options_list_values_with_counts(client, admin_headers, publish):
    await publish(name="Opt A", fabric="Cotton", occasion="Casual", sleeve="Full Sleeve")
    await publish(name="Opt B", fabric="Cotton", occasion="Festive", neckline="V-Neck")
    await publish(name="Opt C", fabric="Silk")

    response = await client.get(f"{STOREFRONT}/filter-options")

    data = response.json()["data"]
    assert {"value": "Cotton", "count": 2} in data["fabric"]
    assert {"value": "Silk", "count": 1} in data["fabric"]
    assert [o["value"] for o in data["occasion"]] == ["Casual", "Festive"]
    assert data["sleeve"] == [{"value": "Full Sleeve", "count": 1}]
    assert data["neckline"] == [{"value": "V-Neck", "count": 1}]


async def test_storefront_filter_options_ignore_drafts(client, admin_headers, category):
    await make_product(client, admin_headers, category["id"], fabric="Hidden Linen")

    storefront = await client.get(f"{STOREFRONT}/filter-options")
    admin = await client.get(f"{PRODUCTS}/filter-options", headers=admin_headers)

    assert storefront.json()["data"]["fabric"] == []
    assert admin.json()["data"]["fabric"] == [{"value": "Hidden Linen", "count": 1}]


async def test_filter_options_narrow_to_a_category_subtree(client, admin_headers, publish):
    parent = await make_category(client, admin_headers, name="Opt Parent")
    child = await make_category(client, admin_headers, name="Opt Child", parent_id=parent["id"])
    elsewhere = await make_category(client, admin_headers, name="Opt Elsewhere")
    await publish(name="In Child", fabric="Rayon", category=child)
    await publish(name="Elsewhere", fabric="Georgette", category=elsewhere)

    response = await client.get(
        f"{STOREFRONT}/filter-options", params={"category_id": parent["id"]}
    )

    assert response.json()["data"]["fabric"] == [{"value": "Rayon", "count": 1}]


async def test_filter_options_for_an_unknown_category_is_404(client, tenant):
    response = await client.get(
        f"{STOREFRONT}/filter-options",
        params={"category_id": "00000000-0000-0000-0000-000000000000"},
    )

    assert response.status_code == 404
