"""Fixtures for the cart tests."""

from __future__ import annotations

import pytest
import pytest_asyncio

from tests.catalogue.factories import PRODUCTS, make_category, make_product
from tests.conftest import headers_for
from tests.helpers import load_data, sample

DATA = load_data(__file__)

CART = DATA["routes"]["cart"]
CUSTOMERS = DATA["customers"]


@pytest_asyncio.fixture(loop_scope="session")
async def customer(make_user, tenant):
    return await make_user(tenant=tenant, phone=CUSTOMERS["owner"])


@pytest.fixture
def customer_auth(customer) -> dict[str, str]:
    return headers_for(customer)


@pytest_asyncio.fixture(loop_scope="session")
async def new_variant(client, admin_headers):
    """Factory: `await new_variant(initial_quantity=3, status="DRAFT")`."""
    counter = {"n": 0}
    category = await make_category(client, admin_headers)

    async def _make(**overrides) -> dict:
        counter["n"] += 1
        product = await make_product(
            client,
            admin_headers,
            category["id"],
            name=f"T-Shirt {counter['n']}",
            status=overrides.pop("product_status", "ACTIVE"),
        )
        payload = sample(DATA, "variant", **overrides)
        payload["sku"] = f"CART-SKU-{counter['n']}"

        response = await client.post(
            f"{PRODUCTS}/{product['id']}/variants", json=payload, headers=admin_headers
        )
        assert response.status_code == 201, response.text
        return response.json()["data"]

    return _make


@pytest_asyncio.fixture(loop_scope="session")
async def variant(new_variant) -> dict:
    """An ACTIVE variant with 10 in stock."""
    return await new_variant()


@pytest_asyncio.fixture(loop_scope="session")
async def add_to_cart(client):
    """Factory: `await add_to_cart(headers, variant_id, quantity=2)`."""

    async def _add(headers, variant_id, quantity: int = 1):
        return await client.post(
            f"{CART}/items",
            json={"variant_id": variant_id, "quantity": quantity},
            headers=headers,
        )

    return _add
