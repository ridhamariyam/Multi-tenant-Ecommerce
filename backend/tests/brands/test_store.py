"""Store settings, publication, platform subdomains and custom domains."""

from __future__ import annotations

from tests.brands.conftest import create_product

STORE = "/api/v1/brand/store"
STOREFRONT_PRODUCTS = "/api/v1/storefront/products"


def at(host: str) -> dict[str, str]:
    return {"Host": host}


async def test_the_owner_configures_the_store(platform, brand_a):
    response = await platform.put(
        STORE,
        json={"name": "Alpha Store", "primary_color": "#112233", "theme": "minimal"},
        headers=brand_a.headers,
    )
    assert response.status_code == 200, response.text
    store = response.json()["data"]
    assert store["primary_color"] == "#112233" and store["theme"] == "minimal"
    assert store["url"] == f"http://{brand_a.subdomain}.localhost:3000"


async def test_store_settings_are_validated(platform, brand_a, brand_b):
    bad_colour = await platform.put(STORE, json={"primary_color": "red"}, headers=brand_a.headers)
    assert bad_colour.status_code == 422
    taken = await platform.put(STORE, json={"subdomain": brand_b.subdomain}, headers=brand_a.headers)
    assert taken.status_code == 409
    reserved = await platform.put(STORE, json={"subdomain": "api"}, headers=brand_a.headers)
    assert reserved.status_code == 400


async def test_an_unpublished_store_is_not_served(platform, brand_a):
    await create_product(platform, brand_a, "Alpha Tee")
    response = await platform.get(STOREFRONT_PRODUCTS, headers=at(f"{brand_a.subdomain}.localhost"))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "UNKNOWN_STOREFRONT"


async def test_each_subdomain_serves_only_its_own_published_catalogue(platform, brand_a, brand_b):
    mine = await create_product(platform, brand_a, "Alpha Hoodie")
    theirs = await create_product(platform, brand_b, "Beta Hoodie")
    for brand in (brand_a, brand_b):
        published = await platform.post(STORE + "/publish", json={"published": True}, headers=brand.headers)
        assert published.status_code == 200 and published.json()["data"]["published"] is True

    a_names = {
        p["name"]
        for p in (await platform.get(STOREFRONT_PRODUCTS, headers=at(f"{brand_a.subdomain}.localhost"))).json()["data"]
    }
    b_names = {
        p["name"]
        for p in (await platform.get(STOREFRONT_PRODUCTS, headers=at(f"{brand_b.subdomain}.localhost"))).json()["data"]
    }
    assert mine["name"] in a_names and theirs["name"] not in a_names
    assert theirs["name"] in b_names and mine["name"] not in b_names


async def test_unpublishing_takes_the_store_offline(platform, brand_a):
    await platform.post(STORE + "/publish", json={"published": True}, headers=brand_a.headers)
    host = at(f"{brand_a.subdomain}.localhost")
    assert (await platform.get(STOREFRONT_PRODUCTS, headers=host)).status_code == 200
    await platform.post(STORE + "/publish", json={"published": False}, headers=brand_a.headers)
    assert (await platform.get(STOREFRONT_PRODUCTS, headers=host)).status_code == 404


async def test_a_custom_domain_serves_only_after_verification(platform, make_merchant, brand_a):
    await platform.post(STORE + "/publish", json={"published": True}, headers=brand_a.headers)
    added = await platform.post(
        "/api/v1/brand/domains", json={"domain": "Shop.Alpha-Brand.com"}, headers=brand_a.headers
    )
    assert added.status_code == 201, added.text
    domain = added.json()["data"]
    assert domain["domain"] == "shop.alpha-brand.com"
    assert domain["verified_at"] is None and domain["verification_record"].startswith("cliq-verify=")

    host = at("shop.alpha-brand.com")
    assert (await platform.get(STOREFRONT_PRODUCTS, headers=host)).status_code == 404

    # Brand owners cannot verify their own domain; a platform admin does.
    assert (
        await platform.post(
            f"/api/v1/platform/admin/domains/{domain['id']}/verify", headers=brand_a.owner.headers
        )
    ).status_code == 403
    admin = await make_merchant("ops@platform.example.com", platform_admin=True)
    verified = await platform.post(
        f"/api/v1/platform/admin/domains/{domain['id']}/verify", headers=admin.headers
    )
    assert verified.status_code == 200
    assert (await platform.get(STOREFRONT_PRODUCTS, headers=host)).status_code == 200


async def test_a_domain_belongs_to_one_brand(platform, brand_a, brand_b):
    payload = {"domain": "only-one.example.com"}
    assert (await platform.post("/api/v1/brand/domains", json=payload, headers=brand_a.headers)).status_code == 201
    second = await platform.post("/api/v1/brand/domains", json=payload, headers=brand_b.headers)
    assert second.status_code == 409
    platform_address = await platform.post(
        "/api/v1/brand/domains", json={"domain": "sneaky.localhost"}, headers=brand_b.headers
    )
    assert platform_address.status_code in (400, 422)


async def test_a_brand_cannot_remove_another_brands_domain(platform, brand_a, brand_b):
    added = await platform.post(
        "/api/v1/brand/domains", json={"domain": "alpha-only.example.com"}, headers=brand_a.headers
    )
    response = await platform.delete(
        f"/api/v1/brand/domains/{added.json()['data']['id']}", headers=brand_b.headers
    )
    assert response.status_code == 404


async def test_suspension_closes_the_store_and_the_brand_api(platform, make_merchant, brand_a):
    await platform.post(STORE + "/publish", json={"published": True}, headers=brand_a.headers)
    admin = await make_merchant("ops2@platform.example.com", platform_admin=True)

    suspended = await platform.post(
        f"/api/v1/platform/admin/brands/{brand_a.id}/suspend",
        json={"reason": "Chargebacks"},
        headers=admin.headers,
    )
    assert suspended.status_code == 200
    assert suspended.json()["data"]["brand"]["status"] == "SUSPENDED"

    assert (
        await platform.get(STOREFRONT_PRODUCTS, headers=at(f"{brand_a.subdomain}.localhost"))
    ).status_code == 404
    blocked = await platform.get("/api/v1/catalogue/products", headers=brand_a.headers)
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "BRAND_SUSPENDED"

    await platform.post(f"/api/v1/platform/admin/brands/{brand_a.id}/activate", headers=admin.headers)
    assert (await platform.get("/api/v1/catalogue/products", headers=brand_a.headers)).status_code == 200


async def test_platform_admin_routes_need_a_platform_admin(platform, brand_a):
    assert (
        await platform.get("/api/v1/platform/admin/brands", headers=brand_a.owner.headers)
    ).status_code == 403
    assert (await platform.get("/api/v1/platform/admin/brands", headers=brand_a.headers)).status_code == 401


async def test_the_legacy_per_store_admin_login_still_manages_its_store(
    client, tenant, admin_headers, session
):
    """Admins of stores that predate memberships keep working, by host as before."""
    from app.stores.models import Store

    session.add(Store(tenant_id=tenant.id, name="Legacy", subdomain="legacy", published=False))
    await session.commit()
    response = await client.get(STORE, headers=admin_headers)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["subdomain"] == "legacy"
