"""Storefront search: fabric/occasion/sleeve/neckline filters and sub-categories."""

from __future__ import annotations

import pytest
import pytest_asyncio

from tests.catalogue.factories import make_category, make_product
from tests.helpers import load_data, sample

DATA = load_data(__file__)

SEARCH = DATA["routes"]["search"]
PRODUCTS = DATA["routes"]["products"]

KURTA = {"fabric": "Cotton", "occasion": "Festive", "sleeve": "Full Sleeve", "neckline": "V-Neck"}
DRESS = {"fabric": "Silk", "occasion": "Party", "sleeve": "Sleeveless", "neckline": "Halter"}


async def _live_product(client, headers, category_id, name, sku, **attributes) -> dict:
    """An ACTIVE product with one ACTIVE variant, so search can find it."""
    product = await make_product(
        client, headers, category_id, name=name, status="ACTIVE", **attributes
    )
    variant = sample(DATA, "variant", sku=sku, status="ACTIVE")
    response = await client.post(
        f"{PRODUCTS}/{product['id']}/variants", json=variant, headers=headers
    )
    assert response.status_code == 201, response.text
    return product


@pytest_asyncio.fixture(loop_scope="session")
async def attribute_catalogue(client, admin_headers) -> dict:
    """Ethnic Wear > Kurtas holds a kurta; Ethnic Wear itself holds a dress."""
    ethnic = await make_category(client, admin_headers, name="Ethnic Wear")
    kurtas = await make_category(
        client, admin_headers, name="Kurtas", parent_id=ethnic["id"]
    )
    kurta = await _live_product(
        client, admin_headers, kurtas["id"], "Festive Kurta", "ATTR-KURTA", **KURTA
    )
    dress = await _live_product(
        client, admin_headers, ethnic["id"], "Party Dress", "ATTR-DRESS", **DRESS
    )
    return {"ethnic": ethnic, "kurtas": kurtas, "kurta": kurta, "dress": dress}


@pytest.mark.parametrize("field", list(KURTA))
async def test_search_filters_by_each_attribute(client, attribute_catalogue, field):
    response = await client.get(SEARCH, params={field: KURTA[field].upper()})

    assert response.status_code == 200
    assert [p["id"] for p in response.json()["data"]] == [
        attribute_catalogue["kurta"]["id"]
    ]


async def test_search_results_carry_the_attributes(client, attribute_catalogue):
    response = await client.get(SEARCH, params={"fabric": "Silk"})

    row = response.json()["data"][0]
    for field, value in DRESS.items():
        assert row[field] == value


async def test_search_attribute_filters_combine(client, attribute_catalogue):
    response = await client.get(SEARCH, params={"fabric": "Cotton", "occasion": "Party"})

    assert response.json()["data"] == []


async def test_search_by_parent_category_includes_sub_categories(
    client, attribute_catalogue
):
    response = await client.get(
        SEARCH, params={"category_id": attribute_catalogue["ethnic"]["id"]}
    )

    assert {p["id"] for p in response.json()["data"]} == {
        attribute_catalogue["kurta"]["id"],
        attribute_catalogue["dress"]["id"],
    }


async def test_search_by_sub_category_excludes_the_parents_own_products(
    client, attribute_catalogue
):
    response = await client.get(
        SEARCH, params={"category_id": attribute_catalogue["kurtas"]["id"]}
    )

    assert [p["id"] for p in response.json()["data"]] == [
        attribute_catalogue["kurta"]["id"]
    ]


async def test_an_overlong_attribute_filter_is_rejected(client, tenant):
    response = await client.get(SEARCH, params={"fabric": "x" * 101})

    assert response.status_code == 422
