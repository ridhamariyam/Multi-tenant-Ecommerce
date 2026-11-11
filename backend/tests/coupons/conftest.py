"""Fixtures for the coupons tests.

Tests build coupons directly via CouponRepository and drive requests through
the shared root fixtures; `cart_worth` fills a customer's cart, since coupons
are always priced against the live cart.
"""

from __future__ import annotations

from uuid import uuid4

import pytest_asyncio
from httpx import AsyncClient

from tests.catalogue.factories import make_category, make_product, make_variant


@pytest_asyncio.fixture(loop_scope="session")
async def cart_worth(client: AsyncClient, admin_headers: dict, tax_ready):
    """Factory: put one item priced at `subtotal` in a customer's cart."""

    async def _fill(headers: dict, subtotal: str) -> None:
        category = await make_category(client, admin_headers, name=f"Coupon {uuid4().hex[:8]}")
        product = await make_product(client, admin_headers, category["id"], status="ACTIVE")
        variant = await make_variant(
            client,
            admin_headers,
            product["id"],
            sku=f"CPN-{uuid4().hex[:8].upper()}",
            price=subtotal,
            status="ACTIVE",
            initial_quantity=5,
        )
        added = await client.post(
            "/api/v1/cart/items",
            json={"variant_id": variant["id"], "quantity": 1},
            headers=headers,
        )
        assert added.status_code == 201, added.text

    return _fill
