"""GET /storefront/resolve: the host decides the brand, and only that brand."""

from __future__ import annotations

RESOLVE = "/api/v1/storefront/resolve"
STORE = "/api/v1/brand/store"


def at(host: str, **extra) -> dict[str, str]:
    return {"Host": host, **extra}


async def _publish(platform, brand, **settings):
    if settings:
        assert (await platform.put(STORE, json=settings, headers=brand.headers)).status_code == 200
    response = await platform.post(f"{STORE}/publish", json={"published": True}, headers=brand.headers)
    assert response.status_code == 200, response.text


async def test_each_subdomain_resolves_to_its_own_brand(platform, brand_a, brand_b):
    await _publish(platform, brand_a, primary_color="#112233", theme="minimal")
    await _publish(platform, brand_b, primary_color="#445566")

    a = await platform.get(RESOLVE, headers=at(f"{brand_a.subdomain}.localhost"))
    b = await platform.get(RESOLVE, headers=at(f"{brand_b.subdomain}.localhost:3000"))

    assert a.status_code == 200 and b.status_code == 200
    assert a.json()["data"]["brand"]["name"] == "Brand Alpha"
    assert a.json()["data"]["store"]["primary_color"] == "#112233"
    assert a.json()["data"]["store"]["theme"] == "minimal"
    assert a.json()["data"]["preview"] is False
    assert b.json()["data"]["brand"]["name"] == "Brand Beta"
    assert b.json()["data"]["store"]["subdomain"] == brand_b.subdomain
    assert a.headers["cache-control"] == "public, max-age=60"


async def test_resolve_exposes_no_private_brand_fields(platform, brand_a):
    await _publish(platform, brand_a)

    data = (await platform.get(RESOLVE, headers=at(f"{brand_a.subdomain}.localhost"))).json()["data"]

    assert set(data["brand"]) == {"name", "slug", "description", "logo_url", "currency"}
    assert "id" not in data["store"] and "published_at" not in data["store"]


async def test_unknown_and_unpublished_hosts_do_not_resolve(platform, brand_a):
    unknown = await platform.get(RESOLVE, headers=at("nobody.localhost"))
    unpublished = await platform.get(RESOLVE, headers=at(f"{brand_a.subdomain}.localhost"))

    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "UNKNOWN_STOREFRONT"
    assert unpublished.status_code == 404


async def test_staff_preview_an_unpublished_store(platform, brand_a):
    response = await platform.get(
        RESOLVE, headers=at(f"{brand_a.subdomain}.localhost", **brand_a.headers)
    )

    assert response.status_code == 200
    assert response.json()["data"]["preview"] is True
    assert response.headers["cache-control"] == "private, no-store"


async def test_another_brands_token_cannot_preview(platform, brand_a, brand_b):
    """B's token names B: the response is B's own store, never A's unpublished one."""
    response = await platform.get(
        RESOLVE, headers=at(f"{brand_a.subdomain}.localhost", **brand_b.headers)
    )

    assert response.status_code == 200
    assert response.json()["data"]["brand"]["name"] == "Brand Beta"


async def test_resolve_says_whether_the_brand_takes_online_payment(platform, brand_a):
    await _publish(platform, brand_a)

    data = (await platform.get(RESOLVE, headers=at(f"{brand_a.subdomain}.localhost"))).json()["data"]

    # A new brand has not connected its own Razorpay account yet.
    assert data["payments"] == {"online": False, "razorpay_key_id": None}
