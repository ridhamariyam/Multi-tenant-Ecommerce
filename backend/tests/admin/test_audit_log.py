"""The admin activity log: who did what, to which record, when."""

from __future__ import annotations

from tests.admin.conftest import API, AUDIT, CATEGORIES, STAFF
from tests.conftest import admin_login


async def test_an_admin_change_is_recorded(client, admin_headers):
    await client.post(CATEGORIES, json={"name": "Audited"}, headers=admin_headers)

    logs = (await client.get(AUDIT, headers=admin_headers)).json()["data"]

    entry = logs[0]
    assert entry["action"] == "create_category"
    assert entry["entity_type"] == "category"
    assert entry["changes"]["body"]["name"] == "Audited"
    assert entry["actor_role"] == "ADMIN"
    assert entry["created_at"]


async def test_the_record_points_at_the_entity(client, admin_headers):
    category = (
        await client.post(CATEGORIES, json={"name": "Before"}, headers=admin_headers)
    ).json()["data"]
    await client.patch(
        f"{CATEGORIES}/{category['id']}", json={"name": "After"}, headers=admin_headers
    )

    logs = (
        await client.get(AUDIT, params={"entity_id": category["id"]}, headers=admin_headers)
    ).json()["data"]

    assert [log["action"] for log in logs] == ["update_category"]
    assert logs[0]["entity_type"] == "category"


async def test_refused_and_invalid_requests_are_not_logged(client, admin_headers, staff_headers):
    await client.post(CATEGORIES, json={"name": "Nope"}, headers=staff_headers)
    await client.post(CATEGORIES, json={}, headers=admin_headers)

    logs = (await client.get(AUDIT, headers=admin_headers)).json()["data"]

    assert logs == []


async def test_reads_are_not_logged(client, admin_headers):
    await client.get(CATEGORIES, headers=admin_headers)

    assert (await client.get(AUDIT, headers=admin_headers)).json()["data"] == []


async def test_passwords_never_reach_the_log(client, admin_headers):
    await client.post(
        STAFF,
        json={
            "name": "Secret",
            "email": "secret@zeen.com",
            "phone": "9811100000",
            "password": "TopSecret123",
            "permissions": [],
        },
        headers=admin_headers,
    )

    logs = (await client.get(AUDIT, headers=admin_headers)).json()["data"]

    assert logs[0]["action"] == "staff.created"
    assert "TopSecret123" not in str(logs)


async def test_viewing_the_log_needs_permission(client, staff_headers, staff_with):
    legacy = await client.get(AUDIT, headers=staff_headers)
    granted = await client.get(AUDIT, headers=await staff_with("audit.view"))

    assert legacy.status_code == 403
    assert granted.status_code == 200


async def test_the_log_is_per_tenant(client, other_client, admin_headers, other_admin_headers):
    await client.post(CATEGORIES, json={"name": "Zeen only"}, headers=admin_headers)

    logs = (await other_client.get(AUDIT, headers=other_admin_headers)).json()["data"]

    assert logs == []


async def test_the_log_filters_by_action_prefix(client, admin_headers):
    await client.post(CATEGORIES, json={"name": "One"}, headers=admin_headers)
    await client.put(
        f"{API}/admin/tax", json={"tax_percentage": "5.00"}, headers=admin_headers
    )

    logs = (
        await client.get(AUDIT, params={"action": "update_tax"}, headers=admin_headers)
    ).json()["data"]

    assert [log["action"] for log in logs] == ["update_tax_settings"]


# ------------------------------------------------------------ sign-ins


async def test_a_successful_admin_sign_in_is_logged(client, make_user, tenant, admin_headers):
    admin = await make_user(tenant=tenant, email="boss@zeen.com", role="ADMIN", name="Boss")

    await admin_login(client, "boss@zeen.com")
    logs = (await client.get(AUDIT, params={"action": "auth.login"}, headers=admin_headers)).json()["data"]

    entry = next(log for log in logs if log["actor_id"] == str(admin.id))
    assert entry["action"] == "auth.login"
    assert entry["actor_role"] == "ADMIN"
    assert entry["summary"] == "Signed in (admin)"


async def test_a_wrong_password_is_logged_against_the_account(client, make_user, tenant, admin_headers):
    staff = await make_user(tenant=tenant, email="packer@zeen.com", role="STAFF")

    response = await client.post(
        "/api/v1/staff/auth/login", json={"identifier": "packer@zeen.com", "password": "wrong-password"}
    )
    logs = (await client.get(AUDIT, params={"action": "auth.login_failed"}, headers=admin_headers)).json()["data"]

    assert response.status_code == 401
    assert logs[0]["actor_id"] == str(staff.id)
    assert logs[0]["summary"] == "Failed staff sign-in"
    assert "wrong-password" not in str(logs[0])


async def test_an_unknown_account_is_logged_without_what_was_typed(client, admin_headers):
    await admin_login(client, "maybe-a-password@x.com", "whatever-123")
    logs = (await client.get(AUDIT, params={"action": "auth.login_failed"}, headers=admin_headers)).json()["data"]

    assert logs[0]["actor_id"] is None
    assert logs[0]["summary"] == "Failed admin sign-in (unknown account)"
    assert "maybe-a-password" not in str(logs[0])
    assert "whatever-123" not in str(logs[0])


async def test_sign_ins_are_logged_in_their_own_store(client, other_client, make_user, other_tenant, admin_headers):
    await make_user(tenant=other_tenant, email="acme-boss@acme.com", role="ADMIN")

    await admin_login(other_client, "acme-boss@acme.com")
    ours = (await client.get(AUDIT, params={"action": "auth.login"}, headers=admin_headers)).json()["data"]

    assert all("acme" not in (log["actor_name"] or "") for log in ours)
