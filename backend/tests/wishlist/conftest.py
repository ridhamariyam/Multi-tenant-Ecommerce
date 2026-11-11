from __future__ import annotations

import pytest
import pytest_asyncio

from tests.catalogue.factories import PRODUCTS, make_category, make_product
from tests.conftest import headers_for
from tests.helpers import load_data, sample

DATA = load_data(__file__)

WISHLIST = DATA["routes"]["wishlist"]
CUSTOMERS = DATA["customers"]


@pytest_asyncio.fixture(loop_scope="session")
async def customer(make_user, tenant):
    return await make_user(tenant=tenant, phone=CUSTOMERS["owner"])


@pytest.fixture
def customer_auth(customer) -> dict[str, str]:
    return headers_for(customer)


@pytest_asyncio.fixture(loop_scope="session")
async def new_variant(client, admin_headers):
    counter = {"n": 0}
    category = await make_category(client, admin_headers)

    async def _make(**overrides) -> dict:
        counter["n"] += 1

        product_id = overrides.pop("product_id", None)
        if not product_id:
            product = await make_product(
                client,
                admin_headers,
                category["id"],
                name=f"T-Shirt {counter['n']}",
                status=overrides.pop("product_status", "ACTIVE"),
            )
            product_id = product["id"]

        payload = sample(DATA, "variant", **overrides)
        payload["sku"] = f"WISHLIST-SKU-{counter['n']}"

        response = await client.post(
            f"{PRODUCTS}/{product_id}/variants", json=payload, headers=admin_headers
        )
        assert response.status_code == 201, response.text
        return response.json()["data"]

    return _make


@pytest_asyncio.fixture(loop_scope="session")
async def variant(new_variant) -> dict:
    return await new_variant()


@pytest_asyncio.fixture(loop_scope="session")
async def add_to_wishlist(client):
    async def _add(headers, variant_id: str):
        return await client.post(
            f"{WISHLIST}/items",
            json={"variant_id": variant_id},
            headers=headers,
        )

    return _add
