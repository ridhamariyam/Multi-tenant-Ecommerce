"""The reverse proxy only gets certificates for hosts CliQ. actually serves."""

from __future__ import annotations

ASK = "/api/v1/internal/tls-allowed"
DOMAINS = "/api/v1/brand/domains"


async def allowed(platform, domain: str) -> bool:
    response = await platform.get(ASK, params={"domain": domain})
    assert response.status_code in (200, 404), response.text
    return response.status_code == 200


async def test_platform_hosts_are_allowed(platform):
    # PLATFORM_ROOT_DOMAIN is "localhost" in tests.
    assert await allowed(platform, "app.localhost")
    assert await allowed(platform, "api.localhost")


async def test_a_brand_subdomain_is_allowed_and_an_unknown_one_is_not(platform, brand_a):
    assert await allowed(platform, f"{brand_a.subdomain}.localhost")
    assert await allowed(platform, f"{brand_a.subdomain.upper()}.localhost:443")
    assert not await allowed(platform, "nobody-here.localhost")
    assert not await allowed(platform, f"deep.{brand_a.subdomain}.localhost")


async def test_custom_domains_only_once_verified(platform, session, brand_a, make_merchant):
    added = (await platform.post(DOMAINS, json={"domain": "shop.alpha.example"}, headers=brand_a.headers)).json()["data"]
    assert not await allowed(platform, "shop.alpha.example")

    admin = await make_merchant("ops@cliq.example.com", platform_admin=True)
    await platform.post(f"/api/v1/platform/admin/domains/{added['id']}/verify", headers=admin.headers)
    assert await allowed(platform, "shop.alpha.example")


async def test_a_suspended_brand_gets_no_new_certificates(platform, brand_a, make_merchant):
    admin = await make_merchant("ops@cliq.example.com", platform_admin=True)
    await platform.post(f"/api/v1/platform/admin/brands/{brand_a.id}/suspend", json={"reason": "x"}, headers=admin.headers)

    assert not await allowed(platform, f"{brand_a.subdomain}.localhost")


async def test_random_names_are_refused(platform):
    for name in ["example.com", "attacker.example", "", "localhost.evil.example"]:
        assert not await allowed(platform, name)
