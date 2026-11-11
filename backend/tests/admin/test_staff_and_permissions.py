"""Individual staff accounts, roles and permission enforcement."""

from __future__ import annotations

from tests.admin.conftest import API, CATEGORIES, STAFF

NEW_STAFF = {
    "name": "Packing Person",
    "email": "packer@zeen.com",
    "phone": "9811122233",
    "password": "Str0ngPass!",
    "role": "STAFF",
    "permissions": ["orders.view", "orders.manage"],
}


async def _create(client, headers, **overrides):
    return await client.post(STAFF, json={**NEW_STAFF, **overrides}, headers=headers)


async def test_an_admin_creates_a_staff_login(client, admin_headers):
    response = await _create(client, admin_headers)

    body = response.json()["data"]
    assert response.status_code == 201
    assert body["role"] == "STAFF"
    assert body["permissions"] == ["orders.manage", "orders.view"]
    assert body["effective_permissions"] == ["orders.manage", "orders.view"]
    assert body["phone"] == "+919811122233"


async def test_the_new_staff_member_can_sign_in_and_sees_their_permissions(client, admin_headers):
    await _create(client, admin_headers)

    login = await client.post(
        f"{API}/staff/auth/login",
        json={"identifier": "packer@zeen.com", "password": NEW_STAFF["password"]},
    )
    token = login.json()["data"]["access_token"]
    me = await client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert login.status_code == 200
    assert me.json()["data"]["permissions"] == ["orders.manage", "orders.view"]


async def test_an_admins_profile_lists_every_permission(client, admin_headers):
    me = await client.get(f"{API}/auth/me", headers=admin_headers)

    assert "staff" not in me.json()["data"]["permissions"]
    assert "cms.publish" in me.json()["data"]["permissions"]


async def test_unknown_permissions_are_rejected(client, admin_headers):
    response = await _create(client, admin_headers, permissions=["orders.view", "god.mode"])

    assert response.status_code == 422


async def test_an_email_in_use_is_refused(client, admin_headers):
    await _create(client, admin_headers)

    response = await _create(client, admin_headers, phone="9811122299")

    assert response.status_code == 409


async def test_staff_cannot_manage_staff(client, staff_headers, staff_with):
    legacy = await client.get(STAFF, headers=staff_headers)
    granted = await client.get(STAFF, headers=await staff_with("orders.view"))

    assert legacy.status_code == 403
    assert granted.status_code == 403


async def test_permissions_open_and_close_endpoints(client, staff_with):
    catalogue = await staff_with("catalogue.manage")
    orders_only = await staff_with("orders.view")

    allowed = await client.post(CATEGORIES, json={"name": "By Staff"}, headers=catalogue)
    refused = await client.post(CATEGORIES, json={"name": "Nope"}, headers=orders_only)
    read_refused = await client.get(CATEGORIES, headers=orders_only)

    assert allowed.status_code == 201
    assert refused.status_code == 403
    assert read_refused.status_code == 403


async def test_legacy_staff_keep_their_old_read_only_access(client, staff_headers):
    read = await client.get(CATEGORIES, headers=staff_headers)
    write = await client.post(CATEGORIES, json={"name": "Legacy"}, headers=staff_headers)
    new_area = await client.get(f"{API}/admin/customers", headers=staff_headers)

    assert read.status_code == 200
    assert write.status_code == 403
    assert new_area.status_code == 403


async def test_permissions_can_be_changed(client, admin_headers):
    created = (await _create(client, admin_headers)).json()["data"]

    response = await client.patch(
        f"{STAFF}/{created['id']}",
        json={"permissions": ["reports.view"], "name": "Accounts"},
        headers=admin_headers,
    )

    assert response.json()["data"]["permissions"] == ["reports.view"]
    assert response.json()["data"]["name"] == "Accounts"


async def test_a_deactivated_account_can_no_longer_sign_in(client, admin_headers):
    created = (await _create(client, admin_headers)).json()["data"]

    await client.patch(
        f"{STAFF}/{created['id']}", json={"status": "INACTIVE"}, headers=admin_headers
    )
    login = await client.post(
        f"{API}/staff/auth/login",
        json={"identifier": "packer@zeen.com", "password": NEW_STAFF["password"]},
    )

    assert login.status_code == 401


async def test_an_admin_cannot_lock_themselves_out(client, admin_headers):
    me = (await client.get(f"{API}/auth/me", headers=admin_headers)).json()["data"]

    response = await client.patch(
        f"{STAFF}/{me['id']}", json={"status": "INACTIVE"}, headers=admin_headers
    )

    assert response.status_code == 400


async def test_a_password_reset_works(client, admin_headers):
    created = (await _create(client, admin_headers)).json()["data"]

    await client.post(
        f"{STAFF}/{created['id']}/password", json={"password": "N3wPassword!"}, headers=admin_headers
    )
    old = await client.post(
        f"{API}/staff/auth/login",
        json={"identifier": "packer@zeen.com", "password": NEW_STAFF["password"]},
    )
    new = await client.post(
        f"{API}/staff/auth/login",
        json={"identifier": "packer@zeen.com", "password": "N3wPassword!"},
    )

    assert old.status_code == 401
    assert new.status_code == 200


async def test_staff_lists_are_per_tenant(client, other_client, admin_headers, other_admin_headers):
    created = (await _create(client, admin_headers)).json()["data"]

    listed = await other_client.get(STAFF, headers=other_admin_headers)
    fetched = await other_client.get(f"{STAFF}/{created['id']}", headers=other_admin_headers)

    assert created["id"] not in [s["id"] for s in listed.json()["data"]]
    assert fetched.status_code == 404


async def test_the_permission_catalogue_is_listed(client, admin_headers):
    response = await client.get(f"{STAFF}/permissions", headers=admin_headers)

    keys = [p["key"] for p in response.json()["data"]]
    assert "orders.manage" in keys and "cms.publish" in keys


async def test_customers_never_reach_staff_admin(client, customer_headers):
    response = await client.get(STAFF, headers=customer_headers)

    assert response.status_code == 403

