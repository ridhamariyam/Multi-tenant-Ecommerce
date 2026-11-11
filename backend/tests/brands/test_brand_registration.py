from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select

from app.auth.constants import UserRole
from app.brands.models import BrandMember
from app.pricing.models import GstSettings, ShippingSettings, TaxSettings
from app.stores.models import Store
from app.tenants.models import Tenant
from app.users.models import User

REGISTER = "/api/v1/brands/register"


async def test_registration_creates_the_brand_its_owner_store_and_settings(
    platform, make_merchant, session
):
    owner = await make_merchant("founder@brands.example.com")
    response = await platform.post(
        REGISTER,
        json={"name": "Nova Label", "description": "Knitwear", "contact_email": "Hi@Nova.example.com"},
        headers=owner.headers,
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    brand_id = UUID(data["brand"]["id"])

    assert data["brand"]["slug"] == "nova-label"
    assert data["brand"]["contact_email"] == "hi@nova.example.com"
    assert data["brand"]["owner_account_id"] == str(owner.account.id)
    assert data["store"]["subdomain"] == "nova-label"
    assert data["store"]["published"] is False
    assert data["token"]["role"] == "OWNER"

    membership = await session.scalar(select(BrandMember).where(BrandMember.tenant_id == brand_id))
    assert membership.role == "OWNER" and membership.account_id == owner.account.id
    user = await session.get(User, membership.user_id)
    assert user.tenant_id == brand_id and user.role == UserRole.ADMIN.value
    assert user.email == "founder@brands.example.com" and user.phone is None
    for model in (ShippingSettings, TaxSettings, GstSettings):
        assert await session.scalar(select(model).where(model.tenant_id == brand_id)) is not None


async def test_the_new_brand_token_opens_the_existing_admin_api(platform, brand_a):
    """No new admin endpoints: the brand token works on the ones that exist."""
    staff = await platform.get("/api/v1/admin/staff", headers=brand_a.headers)
    assert staff.status_code == 200, staff.text


async def test_a_taken_handle_or_reserved_address_is_refused(platform, make_merchant, brand_a):
    other = await make_merchant("copycat@brands.example.com")
    taken = await platform.post(
        REGISTER, json={"name": "Copy", "slug": "brand-alpha"}, headers=other.headers
    )
    assert taken.status_code == 409
    reserved = await platform.post(
        REGISTER, json={"name": "Sneaky", "subdomain": "admin"}, headers=other.headers
    )
    assert reserved.status_code == 400
    assert reserved.json()["error"]["code"] == "STORE_SUBDOMAIN_RESERVED"


async def test_a_name_whose_handle_is_taken_gets_a_free_one(platform, make_merchant, brand_a):
    other = await make_merchant("second-alpha@brands.example.com")
    response = await platform.post(REGISTER, json={"name": "Brand Alpha"}, headers=other.headers)
    assert response.status_code == 201, response.text
    assert response.json()["data"]["brand"]["slug"] == "brand-alpha-2"


async def test_a_failed_registration_leaves_nothing_behind(platform, make_merchant, session, brand_a):
    other = await make_merchant("rollback@brands.example.com")
    before = await session.scalar(select(func.count()).select_from(Tenant))
    response = await platform.post(
        REGISTER, json={"name": "Clash", "subdomain": brand_a.subdomain}, headers=other.headers
    )
    assert response.status_code == 409
    assert await session.scalar(select(func.count()).select_from(Tenant)) == before
    assert await session.scalar(
        select(func.count()).select_from(Store).where(Store.name == "Clash")
    ) == 0


async def test_one_account_can_own_several_brands_and_switch(platform, make_merchant, make_brand):
    owner = await make_merchant("serial@brands.example.com")
    first = await make_brand(owner, "First Label")
    second = await make_brand(owner, "Second Label")

    mine = (await platform.get("/api/v1/brands/me", headers=owner.headers)).json()["data"]
    assert {m["brand"]["id"] for m in mine} == {str(first.id), str(second.id)}

    switched = await platform.post(f"/api/v1/brands/{second.id}/switch", headers=owner.headers)
    assert switched.status_code == 200
    token = switched.json()["data"]
    assert token["brand_id"] == str(second.id)

    # The switched token acts for the second brand only.
    await platform.post(
        "/api/v1/catalogue/categories",
        json={"name": "Only in second"},
        headers={"Authorization": f"Bearer {token['access_token']}"},
    )
    firsts = await platform.get("/api/v1/catalogue/categories", headers=first.headers)
    assert "Only in second" not in {c["name"] for c in firsts.json()["data"]}


async def test_registration_needs_a_platform_session(platform):
    assert (await platform.post(REGISTER, json={"name": "Anon"})).status_code == 401


async def test_owner_updates_the_brand_profile(platform, brand_a):
    response = await platform.put(
        f"/api/v1/brands/{brand_a.id}",
        json={"name": "Brand Alpha Studio", "description": "New line"},
        headers=brand_a.owner.headers,
    )
    assert response.status_code == 200
    assert response.json()["data"]["name"] == "Brand Alpha Studio"
