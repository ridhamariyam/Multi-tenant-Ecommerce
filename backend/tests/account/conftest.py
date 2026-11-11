"""Fixtures for account erasure: one shopper with something to erase."""

from __future__ import annotations

import pytest
import pytest_asyncio

from tests.catalogue.factories import PRODUCTS, make_category, make_product
from tests.conftest import headers_for
from tests.helpers import load_data, sample

DATA = load_data(__file__)

ME = DATA["routes"]["me"]
CART = DATA["routes"]["cart"]
WISHLIST = DATA["routes"]["wishlist"]
ADDRESSES = DATA["routes"]["addresses"]
CHECKOUT = DATA["routes"]["checkout"]
SEARCH = DATA["routes"]["search"]


@pytest_asyncio.fixture(loop_scope="session")
async def shopper(make_user, tenant):
    return await make_user(
        tenant=tenant, phone="+919812340077", email="erase@zeen.com", name="Erasable"
    )


@pytest.fixture
def shopper_auth(shopper) -> dict[str, str]:
    return headers_for(shopper)


@pytest_asyncio.fixture(loop_scope="session")
async def variant(client, admin_headers, tax_ready) -> dict:
    category = await make_category(client, admin_headers, name="Erasure Category")
    product = await make_product(
        client, admin_headers, category["id"], name="Erasure Tee", status="ACTIVE"
    )

    response = await client.post(
        f"{PRODUCTS}/{product['id']}/variants",
        json=sample(DATA, "variant"),
        headers=admin_headers,
    )
    assert response.status_code == 201, response.text

    created = response.json()["data"]
    created["product_id"] = product["id"]
    return created


@pytest_asyncio.fixture(loop_scope="session")
async def stocked_account(client, shopper_auth, variant):
    """A cart, a wishlist entry, an address and a search, all belonging to the shopper."""
    added = await client.post(
        f"{CART}/items",
        json={"variant_id": variant["id"], "quantity": 1},
        headers=shopper_auth,
    )
    assert added.status_code == 201, added.text

    wished = await client.post(
        f"{WISHLIST}/items", json={"variant_id": variant["id"]}, headers=shopper_auth
    )
    assert wished.status_code in {200, 201}, wished.text

    saved = await client.post(
        ADDRESSES, json=sample(DATA, "address"), headers=shopper_auth
    )
    assert saved.status_code == 201, saved.text

    await client.get(SEARCH, params={"q": "Erasure"}, headers=shopper_auth)
    return saved.json()["data"]
