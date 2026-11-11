"""Fixtures for the catalogue tests; payloads come from data.json."""

from __future__ import annotations

import pytest_asyncio

from tests.catalogue.factories import DATA, PRODUCTS, make_category, make_product
from tests.helpers import sample


@pytest_asyncio.fixture(loop_scope="session")
async def category(client, admin_headers) -> dict:
    return await make_category(client, admin_headers)


@pytest_asyncio.fixture(loop_scope="session")
async def product(client, admin_headers, category) -> dict:
    """An ACTIVE product with one image."""
    return await make_product(
        client, admin_headers, category["id"], status="ACTIVE"
    )


@pytest_asyncio.fixture(loop_scope="session")
async def new_variant(client, admin_headers, product):
    """Factory for stocked variants: `await new_variant(initial_quantity=3)`."""
    counter = {"n": 0}

    async def _make(**overrides) -> dict:
        counter["n"] += 1
        payload = sample(DATA, "stocked_variant", **overrides)
        payload.setdefault("sku", f"SKU-{counter['n']}")
        if "sku" not in overrides:
            payload["sku"] = f"SKU-{counter['n']}"

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
async def product_with_images(client, admin_headers, category):
    """Factory: `product, images = await product_with_images(3)`, images in sort order."""

    async def _make(count: int = 3) -> tuple[dict, list[dict]]:
        product = await make_product(
            client,
            admin_headers,
            category["id"],
            images=[
                {"url": f"https://cdn.example.com/{index}.jpg", "sort_order": index}
                for index in range(count)
            ],
        )
        listed = await client.get(
            f"{PRODUCTS}/{product['id']}/images", headers=admin_headers
        )
        return product, listed.json()["data"]

    return _make


@pytest_asyncio.fixture(loop_scope="session")
async def publish(client, admin_headers, category):
    """Factory for an ACTIVE, stocked product in an ACTIVE category."""
    counter = {"n": 0}

    async def _publish(**overrides) -> dict:
        counter["n"] += 1
        variant_defaults = sample(DATA, "storefront_variant")
        price = overrides.pop("price", DATA["storefront_defaults"]["price"])
        quantity = overrides.pop("quantity", DATA["storefront_defaults"]["quantity"])
        options = overrides.pop("options", variant_defaults["options"])
        in_category = overrides.pop("category", category)

        product = await make_product(
            client,
            admin_headers,
            in_category["id"],
            status="ACTIVE",
            **sample(DATA, "storefront_product", **overrides),
        )
        response = await client.post(
            f"{PRODUCTS}/{product['id']}/variants",
            json={
                "sku": f"PUB-{counter['n']}",
                "name": variant_defaults["name"],
                "price": price,
                "status": "ACTIVE",
                "initial_quantity": quantity,
                "options": options,
            },
            headers=admin_headers,
        )
        assert response.status_code == 201, response.text
        return product

    return _publish
