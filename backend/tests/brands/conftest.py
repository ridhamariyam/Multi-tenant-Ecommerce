"""Two brands, A and B, created through the real registration API.

Accounts are created directly (the sign-up endpoint is covered on its own in
test_platform_auth.py) so the suites do not spend the per-IP sign-up limit.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from uuid import UUID

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import hash_password
from app.merchants.models import MerchantAccount
from app.merchants.security import create_merchant_token
from tests.conftest import _client_for

PASSWORD = "brand-test-password"
# A host no brand owns: platform and brand-token requests must not need one.
PLATFORM_HOST = "platform.test"


@dataclass
class Merchant:
    account: MerchantAccount

    @property
    def headers(self) -> dict[str, str]:
        token = create_merchant_token(self.account.id, "merchant_access")
        return {"Authorization": f"Bearer {token}"}


@dataclass
class Brand:
    id: UUID
    owner: Merchant
    subdomain: str
    token: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


@pytest_asyncio.fixture(loop_scope="session")
async def platform(session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async for c in _client_for(session, PLATFORM_HOST):
        yield c


@pytest_asyncio.fixture(loop_scope="session")
async def make_merchant(session: AsyncSession):
    async def _make(email: str, *, platform_admin: bool = False) -> Merchant:
        account = MerchantAccount(
            email=email,
            name=email.split("@")[0].title(),
            password_hash=await hash_password(PASSWORD),
            is_platform_admin=platform_admin,
        )
        session.add(account)
        await session.commit()
        return Merchant(account)

    return _make


@pytest_asyncio.fixture(loop_scope="session")
async def make_brand(platform: AsyncClient):
    async def _make(owner: Merchant, name: str, **extra) -> Brand:
        response = await platform.post(
            "/api/v1/brands/register", json={"name": name, **extra}, headers=owner.headers
        )
        assert response.status_code == 201, response.text
        data = response.json()["data"]
        return Brand(
            id=UUID(data["brand"]["id"]),
            owner=owner,
            subdomain=data["store"]["subdomain"],
            token=data["token"]["access_token"],
        )

    return _make


@pytest_asyncio.fixture(loop_scope="session")
async def brand_a(make_merchant, make_brand) -> Brand:
    return await make_brand(await make_merchant("owner-a@brands.example.com"), "Brand Alpha")


@pytest_asyncio.fixture(loop_scope="session")
async def brand_b(make_merchant, make_brand) -> Brand:
    return await make_brand(await make_merchant("owner-b@brands.example.com"), "Brand Beta")


async def create_product(client: AsyncClient, brand: Brand, name: str, *, active: bool = True) -> dict:
    category = await client.post(
        "/api/v1/catalogue/categories", json={"name": f"{name} category"}, headers=brand.headers
    )
    assert category.status_code == 201, category.text
    product = await client.post(
        "/api/v1/catalogue/products",
        json={
            "category_id": category.json()["data"]["id"],
            "name": name,
            "status": "ACTIVE" if active else "DRAFT",
            "images": [{"url": "https://cdn.example.com/product.jpg", "is_primary": True}],
        },
        headers=brand.headers,
    )
    assert product.status_code == 201, product.text
    return product.json()["data"]
