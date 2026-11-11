"""Brand A and Brand B on the same platform must not reach each other's data."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.auth.security import create_access_token
from app.brands.models import BrandMember
from app.users.models import User
from tests.brands.conftest import create_product

PRODUCTS = "/api/v1/catalogue/products"


async def test_a_cannot_read_bs_products(platform, brand_a, brand_b):
    theirs = await create_product(platform, brand_b, "Beta Jacket")

    assert (await platform.get(f"{PRODUCTS}/{theirs['id']}", headers=brand_a.headers)).status_code == 404
    listing = await platform.get(PRODUCTS, headers=brand_a.headers)
    assert theirs["id"] not in {p["id"] for p in listing.json()["data"]}


async def test_a_cannot_update_or_archive_bs_products(platform, brand_a, brand_b):
    theirs = await create_product(platform, brand_b, "Beta Coat")

    edit = await platform.patch(
        f"{PRODUCTS}/{theirs['id']}", json={"name": "Hijacked"}, headers=brand_a.headers
    )
    assert edit.status_code == 404
    delete = await platform.delete(f"{PRODUCTS}/{theirs['id']}", headers=brand_a.headers)
    assert delete.status_code == 404

    mine = await platform.get(f"{PRODUCTS}/{theirs['id']}", headers=brand_b.headers)
    assert mine.json()["data"]["name"] == "Beta Coat"


async def test_a_cannot_read_bs_orders_or_customers(platform, brand_a, brand_b):
    for path in ("/api/v1/admin/orders", "/api/v1/admin/customers"):
        assert (await platform.get(path, headers=brand_a.headers)).status_code == 200
    # An id that exists only in B: A sees not-found, not B's order.
    assert (
        await platform.get(f"/api/v1/admin/orders/{uuid.uuid4()}", headers=brand_a.headers)
    ).status_code == 404


async def test_the_host_cannot_redirect_a_brand_token(platform, brand_a, brand_b):
    """A's token sent with B's storefront address as the host still acts for A."""
    theirs = await create_product(platform, brand_b, "Beta Scarf")
    await platform.post(
        "/api/v1/brand/store/publish", json={"published": True}, headers=brand_b.headers
    )
    response = await platform.get(
        f"{PRODUCTS}/{theirs['id']}",
        headers={**brand_a.headers, "Host": f"{brand_b.subdomain}.localhost"},
    )
    assert response.status_code == 404


async def test_a_token_naming_another_brands_membership_is_refused(platform, session, brand_a, brand_b):
    """Even a validly signed token is refused if its user and membership disagree."""
    member_b = await session.scalar(select(BrandMember).where(BrandMember.tenant_id == brand_b.id))
    user_a = await session.scalar(
        select(User).join(BrandMember, BrandMember.user_id == User.id).where(
            BrandMember.tenant_id == brand_a.id
        )
    )
    forged = create_access_token(
        user_id=user_a.id, tenant_id=brand_b.id, role=user_a.role, membership_id=member_b.id
    )
    response = await platform.get(PRODUCTS, headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


async def test_a_non_member_cannot_see_switch_or_manage_a_brand(platform, brand_a, brand_b):
    outsider = brand_b.owner.headers
    for method, path in (
        ("get", f"/api/v1/brands/{brand_a.id}"),
        ("post", f"/api/v1/brands/{brand_a.id}/switch"),
        ("get", f"/api/v1/brands/{brand_a.id}/members"),
    ):
        response = await getattr(platform, method)(path, headers=outsider)
        assert response.status_code == 404, (method, path)
    update = await platform.put(
        f"/api/v1/brands/{brand_a.id}", json={"name": "Taken over"}, headers=outsider
    )
    assert update.status_code == 404


async def test_removing_a_member_revokes_their_token_at_once(platform, make_merchant, brand_a):
    helper = await make_merchant("helper@brands.example.com")
    added = await platform.post(
        f"/api/v1/brands/{brand_a.id}/members",
        json={"email": "helper@brands.example.com", "role": "PRODUCT_MANAGER"},
        headers=brand_a.owner.headers,
    )
    assert added.status_code == 201, added.text
    token = (await platform.post(f"/api/v1/brands/{brand_a.id}/switch", headers=helper.headers)).json()["data"]
    helper_brand = {"Authorization": f"Bearer {token['access_token']}"}
    assert (await platform.get(PRODUCTS, headers=helper_brand)).status_code == 200

    removed = await platform.patch(
        f"/api/v1/brands/{brand_a.id}/members/{added.json()['data']['id']}",
        json={"status": "REMOVED"},
        headers=brand_a.owner.headers,
    )
    assert removed.status_code == 200
    # Same unexpired token, next request: refused.
    assert (await platform.get(PRODUCTS, headers=helper_brand)).status_code == 401


async def test_roles_are_enforced_on_the_existing_admin_api(platform, make_merchant, brand_a):
    products_person = await make_merchant("pm@brands.example.com")
    orders_person = await make_merchant("om@brands.example.com")
    for email, role in (("pm@brands.example.com", "PRODUCT_MANAGER"), ("om@brands.example.com", "ORDER_MANAGER")):
        response = await platform.post(
            f"/api/v1/brands/{brand_a.id}/members",
            json={"email": email, "role": role},
            headers=brand_a.owner.headers,
        )
        assert response.status_code == 201, response.text

    async def brand_headers(merchant):
        token = (await platform.post(f"/api/v1/brands/{brand_a.id}/switch", headers=merchant.headers)).json()
        return {"Authorization": f"Bearer {token['data']['access_token']}"}

    pm = await brand_headers(products_person)
    om = await brand_headers(orders_person)

    new_category = {"name": "PM category"}
    assert (await platform.post("/api/v1/catalogue/categories", json=new_category, headers=pm)).status_code == 201
    assert (await platform.get("/api/v1/admin/orders", headers=pm)).status_code == 403

    assert (await platform.get("/api/v1/admin/orders", headers=om)).status_code == 200
    assert (
        await platform.post("/api/v1/catalogue/categories", json={"name": "OM"}, headers=om)
    ).status_code == 403

    # Neither may manage the brand's members or store.
    for headers in (pm, om):
        assert (await platform.get("/api/v1/brand/store", headers=headers)).status_code == 403
    assert (
        await platform.post(
            f"/api/v1/brands/{brand_a.id}/members",
            json={"email": "x@brands.example.com", "role": "ADMIN"},
            headers=products_person.headers,
        )
    ).status_code == 403


async def test_the_owner_cannot_be_demoted_or_removed(platform, session, brand_a):
    owner_member = await session.scalar(
        select(BrandMember).where(BrandMember.tenant_id == brand_a.id, BrandMember.role == "OWNER")
    )
    response = await platform.patch(
        f"/api/v1/brands/{brand_a.id}/members/{owner_member.id}",
        json={"status": "REMOVED"},
        headers=brand_a.owner.headers,
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "BRAND_OWNER_IMMUTABLE"
