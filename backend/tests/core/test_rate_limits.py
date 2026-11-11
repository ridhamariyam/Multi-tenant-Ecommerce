"""Throttling past the auth endpoints: checkout, coupons, reviews and search."""

from __future__ import annotations

from app.core.config import get_settings
from tests.conftest import headers_for

SEARCH = "/api/v1/storefront/search-products"
COUPON_APPLY = "/api/v1/coupons/apply"


async def test_search_is_throttled_per_client(client, tenant):
    settings = get_settings()
    limit = settings.search_rate_limit_attempts

    for _ in range(limit):
        allowed = await client.get(SEARCH, params={"q": "shoe"})
        assert allowed.status_code == 200, allowed.text

    blocked = await client.get(SEARCH, params={"q": "shoe"})
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "RATE_LIMITED"
    assert blocked.headers["Retry-After"]


async def test_coupon_apply_is_throttled(client, customer_headers, tenant):
    """Guessing codes has to cost something."""
    settings = get_settings()

    for _ in range(settings.coupon_apply_rate_limit_attempts):
        await client.post(
            COUPON_APPLY,
            json={"code": "GUESS"},
            headers=customer_headers,
        )

    blocked = await client.post(
        COUPON_APPLY,
        json={"code": "GUESS"},
        headers=customer_headers,
    )
    assert blocked.status_code == 429


async def test_review_creation_is_throttled(client, customer_headers, tenant):
    settings = get_settings()
    payload = {"product_id": "00000000-0000-0000-0000-000000000001", "rating": 5}

    for _ in range(settings.review_rate_limit_attempts):
        await client.post("/api/v1/reviews", json=payload, headers=customer_headers)

    blocked = await client.post(
        "/api/v1/reviews", json=payload, headers=customer_headers
    )
    assert blocked.status_code == 429


async def test_the_limit_is_per_shopper_not_global(
    client, customer_headers, make_user, tenant
):
    settings = get_settings()

    for _ in range(settings.coupon_apply_rate_limit_attempts + 1):
        await client.post(
            COUPON_APPLY,
            json={"code": "GUESS"},
            headers=customer_headers,
        )

    # A second shopper is untouched by the first one's spending spree.
    other = await make_user(tenant=tenant, phone="+919000778899")
    response = await client.post(
        COUPON_APPLY,
        json={"code": "GUESS"},
        headers=headers_for(other),
    )
    assert response.status_code != 429
    assert response.status_code == 409, response.text
    assert response.json()["message"] == "Your cart is empty"
