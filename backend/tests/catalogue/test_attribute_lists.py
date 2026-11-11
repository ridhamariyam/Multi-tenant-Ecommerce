"""Managed value lists for fabric, occasion, sleeve and neckline."""

from __future__ import annotations

from tests.catalogue.factories import make_product

ATTRIBUTES = "/api/v1/catalogue/attributes"


async def _add(client, headers, attribute, value, **extra):
    return await client.post(
        ATTRIBUTES, json={"attribute": attribute, "value": value, **extra}, headers=headers
    )


async def test_values_are_added_and_listed_per_attribute(client, admin_headers):
    await _add(client, admin_headers, "fabric", "Cotton")
    await _add(client, admin_headers, "fabric", "Silk")
    await _add(client, admin_headers, "sleeve", "Full sleeve")

    fabrics = (await client.get(ATTRIBUTES, params={"attribute": "fabric"}, headers=admin_headers)).json()["data"]
    everything = (await client.get(ATTRIBUTES, headers=admin_headers)).json()["data"]

    assert [v["value"] for v in fabrics] == ["Cotton", "Silk"]
    assert len(everything) == 3


async def test_duplicates_are_refused_ignoring_case(client, admin_headers):
    await _add(client, admin_headers, "fabric", "Cotton")

    response = await _add(client, admin_headers, "fabric", " cotton ")

    assert response.status_code == 409


async def test_the_same_value_may_exist_for_different_attributes(client, admin_headers):
    first = await _add(client, admin_headers, "occasion", "Wedding")
    second = await _add(client, admin_headers, "fabric", "Wedding")

    assert first.status_code == second.status_code == 201


async def test_unknown_attributes_and_blank_values_are_rejected(client, admin_headers):
    assert (await _add(client, admin_headers, "colour", "Red")).status_code == 422
    assert (await _add(client, admin_headers, "fabric", "   ")).status_code == 422


async def test_switched_off_values_drop_out_of_the_active_list(client, admin_headers):
    value = (await _add(client, admin_headers, "neckline", "Boat neck")).json()["data"]

    await client.patch(f"{ATTRIBUTES}/{value['id']}", json={"is_active": False}, headers=admin_headers)
    active = (await client.get(ATTRIBUTES, params={"attribute": "neckline", "active_only": True}, headers=admin_headers)).json()["data"]
    everything = (await client.get(ATTRIBUTES, params={"attribute": "neckline"}, headers=admin_headers)).json()["data"]

    assert active == []
    assert everything[0]["is_active"] is False


async def test_a_value_in_use_cannot_be_renamed(client, admin_headers, category):
    value = (await _add(client, admin_headers, "fabric", "Cotton")).json()["data"]
    await make_product(client, admin_headers, category["id"], fabric="cotton")

    listed = (await client.get(ATTRIBUTES, params={"attribute": "fabric"}, headers=admin_headers)).json()["data"]
    rename = await client.patch(f"{ATTRIBUTES}/{value['id']}", json={"value": "Organic Cotton"}, headers=admin_headers)
    recase = await client.patch(f"{ATTRIBUTES}/{value['id']}", json={"value": "COTTON"}, headers=admin_headers)

    assert listed[0]["product_count"] == 1
    assert rename.status_code == 409
    assert rename.json()["error"]["code"] == "VALUE_IN_USE"
    assert recase.status_code == 200


async def test_an_unused_value_can_be_renamed(client, admin_headers):
    value = (await _add(client, admin_headers, "occasion", "Partywear")).json()["data"]

    response = await client.patch(f"{ATTRIBUTES}/{value['id']}", json={"value": "Party"}, headers=admin_headers)

    assert response.json()["data"]["value"] == "Party"


async def test_products_may_keep_values_that_are_not_in_the_list(client, admin_headers, category):
    product = await make_product(client, admin_headers, category["id"], fabric="Handloom Khadi")

    assert product["fabric"] == "Handloom Khadi"


async def test_staff_can_view_but_only_managers_can_change(client, staff_headers):
    assert (await client.get(ATTRIBUTES, headers=staff_headers)).status_code == 200
    assert (await _add(client, staff_headers, "fabric", "Linen")).status_code == 403


async def test_lists_are_per_store(client, other_client, admin_headers, other_admin_headers):
    value = (await _add(client, admin_headers, "fabric", "Cotton")).json()["data"]

    listed = (await other_client.get(ATTRIBUTES, headers=other_admin_headers)).json()["data"]
    edit = await other_client.patch(f"{ATTRIBUTES}/{value['id']}", json={"is_active": False}, headers=other_admin_headers)

    assert listed == []
    assert edit.status_code == 404
