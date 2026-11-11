"""Fixtures for the shipping and tax tests."""

from __future__ import annotations

import pytest
import pytest_asyncio

from tests.catalogue.factories import PRODUCTS, make_category, make_product
from tests.conftest import headers_for
from tests.helpers import load_data, sample

DATA = load_data(__file__)

SHIPPING = DATA["routes"]["shipping"]
TAX = DATA["routes"]["tax"]
CHECKOUT = DATA["routes"]["checkout"]
ORDERS = DATA["routes"]["orders"]
ADMIN_ORDERS = DATA["routes"]["admin_orders"]
ADMIN_PAYMENTS = DATA["routes"]["admin_payments"]
ADDRESSES = DATA["routes"]["addresses"]
CART = DATA["routes"]["cart"]

CUSTOMERS = DATA["customers"]


def shipping_payload(**overrides) -> dict:
    return sample(DATA, "shipping", **overrides)


def tax_payload(**overrides) -> dict:
    return sample(DATA, "tax", **overrides)


@pytest_asyncio.fixture(loop_scope="session")
async def customer(make_user, tenant):
    return await make_user(tenant=tenant, phone=CUSTOMERS["buyer"])


@pytest.fixture
def customer_auth(customer) -> dict[str, str]:
    return headers_for(customer)


@pytest_asyncio.fixture(loop_scope="session")
async def set_shipping(client, admin_headers):
    """Factory: `await set_shipping(shipping_amount="50.00")`."""

    async def _set(**overrides):
        response = await client.put(
            SHIPPING, json=shipping_payload(**overrides), headers=admin_headers
        )
        assert response.status_code == 200, response.text
        return response.json()["data"]

    return _set


@pytest_asyncio.fixture(loop_scope="session")
async def set_tax(client, admin_headers, tax_ready):
    """Factory: `await set_tax(tax_percentage="5.00")`.

    A saved rate is unconfirmed until the CA signs it off, so an active one is
    confirmed too, and the goods are mapped to the same rate: one percentage
    for the whole basket, as these tests price it.
    """

    async def _set(**overrides):
        payload = tax_payload(**overrides)
        response = await client.put(TAX, json=payload, headers=admin_headers)
        assert response.status_code == 200, response.text
        if not payload.get("is_active", True):
            return response.json()["data"]

        response = await client.post(
            f"{TAX}/confirm", json={"ca_confirmed": True}, headers=admin_headers
        )
        assert response.status_code == 200, response.text
        await tax_ready.use_default_rate(payload["tax_percentage"])
        return response.json()["data"]

    return _set


@pytest_asyncio.fixture(loop_scope="session")
async def variant(client, admin_headers, tax_ready) -> dict:
    """An ACTIVE variant priced at 1000.00 with 20 in stock."""
    category = await make_category(client, admin_headers, name="Pricing Test Category")
    product = await make_product(
        client, admin_headers, category["id"], name="Shirt", status="ACTIVE"
    )

    response = await client.post(
        f"{PRODUCTS}/{product['id']}/variants",
        json=sample(DATA, "variant"),
        headers=admin_headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


@pytest_asyncio.fixture(loop_scope="session")
async def address(client, customer_auth) -> dict:
    response = await client.post(
        ADDRESSES, json=sample(DATA, "address"), headers=customer_auth
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


@pytest_asyncio.fixture(loop_scope="session")
async def fill_cart(client, customer_auth, variant):
    """Factory: `await fill_cart(2)` puts 2 x 1000.00 in the basket."""

    async def _fill(quantity: int = 2):
        response = await client.post(
            f"{CART}/items",
            json={"variant_id": variant["id"], "quantity": quantity},
            headers=customer_auth,
        )
        assert response.status_code == 201, response.text
        return response.json()["data"]

    return _fill


@pytest_asyncio.fixture(loop_scope="session")
async def preview(client, customer_auth):
    """Factory: `await preview()` -> the priced basket."""

    async def _preview():
        response = await client.post(f"{CHECKOUT}/preview", headers=customer_auth)
        assert response.status_code == 200, response.text
        return response.json()["data"]

    return _preview


@pytest_asyncio.fixture(loop_scope="session")
async def place_order(client, customer_auth, address):
    """Factory: `await place_order()` -> the placed order."""

    async def _place(**body):
        payload = {"address_id": address["id"], **body}
        response = await client.post(CHECKOUT, json=payload, headers=customer_auth)
        assert response.status_code == 201, response.text
        return response.json()["data"]

    return _place
