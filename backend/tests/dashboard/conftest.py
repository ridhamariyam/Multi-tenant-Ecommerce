"""Fixtures for the admin dashboard tests."""

from __future__ import annotations

import pytest_asyncio

from tests.catalogue.factories import (
    DATA as CATALOGUE_DATA,
)
from tests.catalogue.factories import (
    PRODUCTS,
    make_category,
    make_product,
)
from tests.helpers import load_data, sample

DATA = load_data(__file__)


@pytest_asyncio.fixture(loop_scope="session")
async def category(client, admin_headers) -> dict:
    return await make_category(client, admin_headers)


@pytest_asyncio.fixture(loop_scope="session")
async def product(client, admin_headers, category) -> dict:
    """An ACTIVE product with one image."""
    return await make_product(
        client,
        admin_headers,
        category["id"],
        status="ACTIVE",
    )


@pytest_asyncio.fixture(loop_scope="session")
async def new_variant(client, admin_headers, product):
    """Factory: `await new_variant(initial_quantity=2, low_stock_threshold=5)`."""
    counter = {"n": 0}

    async def _make(**overrides) -> dict:
        counter["n"] += 1
        payload = sample(CATALOGUE_DATA, "stocked_variant", **overrides)

        if "sku" not in overrides:
            payload["sku"] = f"DASH-SKU-{counter['n']}"

        response = await client.post(
            f"{PRODUCTS}/{product['id']}/variants",
            json=payload,
            headers=admin_headers,
        )
        assert response.status_code == 201, response.text
        return response.json()["data"]

    return _make


@pytest_asyncio.fixture(loop_scope="session")
async def variant(new_variant) -> dict:
    """An ACTIVE variant with 10 in stock."""
    return await new_variant()