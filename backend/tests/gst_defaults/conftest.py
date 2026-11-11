"""Fixtures for checkout on the system GST defaults.

Unlike the other checkout suites these do not use `tax_ready`: nothing is
signed off, so every rate comes from the seeded system rules (or the store's
own settings, set through the admin API).
"""

from __future__ import annotations

import itertools

import pytest
import pytest_asyncio

from tests.catalogue.factories import PRODUCTS, make_category, make_product
from tests.conftest import headers_for
from tests.helpers import load_data, sample

DATA = load_data(__file__)

GST = DATA["routes"]["gst"]
CHECKOUT = DATA["routes"]["checkout"]
ADDRESSES = DATA["routes"]["addresses"]
CART = DATA["routes"]["cart"]
STOREFRONT_TAX = DATA["routes"]["storefront_tax"]

_skus = itertools.count(1)


def gst_payload(**overrides) -> dict:
    return sample(DATA, "gst", **overrides)


@pytest_asyncio.fixture(loop_scope="session")
async def customer(make_user, tenant):
    return await make_user(tenant=tenant, phone=DATA["customers"]["buyer"])


@pytest.fixture
def customer_auth(customer) -> dict[str, str]:
    return headers_for(customer)


@pytest_asyncio.fixture(loop_scope="session")
async def set_gst(client, admin_headers):
    """Factory: `await set_gst(state="Kerala", prices_include_gst=True)`."""

    async def _set(**overrides):
        response = await client.put(GST, json=gst_payload(**overrides), headers=admin_headers)
        assert response.status_code == 200, response.text
        return response.json()["data"]

    return _set


@pytest_asyncio.fixture(loop_scope="session")
async def category(client, admin_headers) -> dict:
    return await make_category(client, admin_headers, name="Kurtas")


@pytest_asyncio.fixture(loop_scope="session")
async def new_variant(client, admin_headers, category):
    """Factory: `await new_variant("2000.00", hsn_code="6204")` -> the variant."""

    async def _make(price: str, **product_fields) -> dict:
        n = next(_skus)
        product = await make_product(
            client, admin_headers, category["id"], name=f"Kurta {n}", status="ACTIVE",
            **product_fields,
        )
        response = await client.post(
            f"{PRODUCTS}/{product['id']}/variants",
            json=sample(DATA, "variant", sku=f"GST-KURTA-{n}", price=price),
            headers=admin_headers,
        )
        assert response.status_code == 201, response.text
        return response.json()["data"]

    return _make


@pytest_asyncio.fixture(loop_scope="session")
async def add_to_cart(client, customer_auth):
    async def _add(variant: dict, quantity: int = 1):
        response = await client.post(
            f"{CART}/items",
            json={"variant_id": variant["id"], "quantity": quantity},
            headers=customer_auth,
        )
        assert response.status_code == 201, response.text

    return _add


@pytest_asyncio.fixture(loop_scope="session")
async def make_address(client, customer_auth):
    async def _make(**overrides) -> dict:
        response = await client.post(
            ADDRESSES, json=sample(DATA, "address", **overrides), headers=customer_auth
        )
        assert response.status_code == 201, response.text
        return response.json()["data"]

    return _make


@pytest_asyncio.fixture(loop_scope="session")
async def preview(client, customer_auth):
    async def _preview(address_id: str | None = None) -> dict:
        body = {"address_id": address_id} if address_id else None
        response = await client.post(f"{CHECKOUT}/preview", json=body, headers=customer_auth)
        assert response.status_code == 200, response.text
        return response.json()["data"]

    return _preview


@pytest_asyncio.fixture(loop_scope="session")
async def place_order(client, customer_auth):
    async def _place(address_id: str) -> dict:
        response = await client.post(
            CHECKOUT, json={"address_id": address_id}, headers=customer_auth
        )
        assert response.status_code == 201, response.text
        return response.json()["data"]

    return _place
