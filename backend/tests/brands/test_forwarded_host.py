"""The storefront server calls the API on a shopper's behalf and names the
domain they visited in X-Forwarded-Host. With TRUST_FORWARDED_HOST on, that
picks the brand; it never widens what a request may see."""

from __future__ import annotations

import pytest

from app.core.config import get_settings
from tests.brands.conftest import create_product

RESOLVE = "/api/v1/storefront/resolve"
STOREFRONT_PRODUCTS = "/api/v1/storefront/products"
STORE = "/api/v1/brand/store"

# What the storefront container calls the API by: not a brand domain.
API_HOST = "api.internal"


def via_storefront(visited: str, **extra) -> dict[str, str]:
    return {"Host": API_HOST, "X-Forwarded-Host": visited, **extra}


async def _publish(platform, brand) -> None:
    response = await platform.post(f"{STORE}/publish", json={"published": True}, headers=brand.headers)
    assert response.status_code == 200, response.text


@pytest.fixture
def trusted(monkeypatch):
    monkeypatch.setattr(get_settings(), "trust_forwarded_host", True)


async def test_the_forwarded_host_picks_each_brand(trusted, platform, brand_a, brand_b):
    await _publish(platform, brand_a)
    await _publish(platform, brand_b)

    a = await platform.get(RESOLVE, headers=via_storefront(f"{brand_a.subdomain}.localhost:3000"))
    b = await platform.get(RESOLVE, headers=via_storefront(f"{brand_b.subdomain}.localhost"))

    assert a.json()["data"]["brand"]["name"] == "Brand Alpha"
    assert b.json()["data"]["brand"]["name"] == "Brand Beta"


async def test_each_storefront_lists_only_its_own_products(trusted, platform, brand_a, brand_b):
    await _publish(platform, brand_a)
    await _publish(platform, brand_b)
    await create_product(platform, brand_a, "Alpha Jacket")
    await create_product(platform, brand_b, "Beta Boots")

    a = await platform.get(STOREFRONT_PRODUCTS, headers=via_storefront(f"{brand_a.subdomain}.localhost"))
    b = await platform.get(STOREFRONT_PRODUCTS, headers=via_storefront(f"{brand_b.subdomain}.localhost"))

    assert [p["name"] for p in a.json()["data"]] == ["Alpha Jacket"]
    assert [p["name"] for p in b.json()["data"]] == ["Beta Boots"]


async def test_without_trust_the_header_is_ignored(monkeypatch, platform, brand_a):
    monkeypatch.setattr(get_settings(), "trust_forwarded_host", False)
    await _publish(platform, brand_a)

    response = await platform.get(RESOLVE, headers=via_storefront(f"{brand_a.subdomain}.localhost"))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "UNKNOWN_STOREFRONT"


async def test_forwarding_does_not_reveal_an_unpublished_store(trusted, platform, brand_a):
    response = await platform.get(RESOLVE, headers=via_storefront(f"{brand_a.subdomain}.localhost"))

    assert response.status_code == 404


async def test_a_brand_token_still_wins_over_the_forwarded_host(trusted, platform, brand_a, brand_b):
    await _publish(platform, brand_b)
    await create_product(platform, brand_a, "Alpha Jacket")

    # Brand A's staff token, sent with Brand B's domain: still Brand A's admin data only.
    response = await platform.get(
        "/api/v1/catalogue/products",
        headers=via_storefront(f"{brand_b.subdomain}.localhost", **brand_a.headers),
    )

    assert response.status_code == 200
    assert [p["name"] for p in response.json()["data"]] == ["Alpha Jacket"]
