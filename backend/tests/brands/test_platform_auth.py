from __future__ import annotations

from app.merchants.constants import AccountStatus
from tests.brands.conftest import PASSWORD

REGISTER = "/api/v1/platform/auth/register"
LOGIN = "/api/v1/platform/auth/login"
REFRESH = "/api/v1/platform/auth/refresh"
LOGOUT = "/api/v1/platform/auth/logout"
ME = "/api/v1/platform/auth/me"


async def test_sign_up_returns_a_session_for_the_new_account(platform):
    response = await platform.post(
        REGISTER,
        json={"email": "New.Owner@Brands.example.com", "password": "long-enough-pw", "name": "New Owner"},
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["account"]["email"] == "new.owner@brands.example.com"
    assert data["account"]["is_platform_admin"] is False

    me = await platform.get(ME, headers={"Authorization": f"Bearer {data['access_token']}"})
    assert me.status_code == 200
    assert me.json()["data"]["email"] == "new.owner@brands.example.com"


async def test_an_email_signs_up_once(platform, make_merchant):
    await make_merchant("taken@brands.example.com")
    response = await platform.post(
        REGISTER, json={"email": "taken@brands.example.com", "password": "long-enough-pw", "name": "X"}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "MERCHANT_EMAIL_TAKEN"


async def test_a_short_password_is_refused(platform):
    response = await platform.post(
        REGISTER, json={"email": "short@brands.example.com", "password": "short", "name": "X"}
    )
    assert response.status_code == 422


async def test_login_checks_the_password(platform, make_merchant):
    await make_merchant("login@brands.example.com")
    wrong = await platform.post(LOGIN, json={"email": "login@brands.example.com", "password": "nope"})
    assert wrong.status_code == 401
    unknown = await platform.post(LOGIN, json={"email": "ghost@brands.example.com", "password": PASSWORD})
    assert unknown.status_code == 401
    right = await platform.post(LOGIN, json={"email": "LOGIN@brands.example.com", "password": PASSWORD})
    assert right.status_code == 200, right.text


async def test_a_suspended_account_cannot_sign_in(platform, make_merchant, session):
    merchant = await make_merchant("suspended@brands.example.com")
    merchant.account.status = AccountStatus.SUSPENDED.value
    await session.commit()
    response = await platform.post(LOGIN, json={"email": "suspended@brands.example.com", "password": PASSWORD})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "MERCHANT_ACCOUNT_SUSPENDED"
    assert (await platform.get(ME, headers=merchant.headers)).status_code == 401


async def test_refresh_rotates_and_a_reused_token_revokes_the_family(platform, make_merchant, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "refresh_reuse_grace_seconds", 0)
    await make_merchant("rotate@brands.example.com")
    first = (await platform.post(LOGIN, json={"email": "rotate@brands.example.com", "password": PASSWORD})).json()["data"]

    second = await platform.post(REFRESH, json={"refresh_token": first["refresh_token"]})
    assert second.status_code == 200, second.text
    newest = second.json()["data"]["refresh_token"]
    assert newest != first["refresh_token"]

    # The old token again: refused, and the newest one dies with it.
    assert (await platform.post(REFRESH, json={"refresh_token": first["refresh_token"]})).status_code == 401
    assert (await platform.post(REFRESH, json={"refresh_token": newest})).status_code == 401


async def test_logout_revokes_the_refresh_token(platform, make_merchant):
    await make_merchant("logout@brands.example.com")
    session_data = (
        await platform.post(LOGIN, json={"email": "logout@brands.example.com", "password": PASSWORD})
    ).json()["data"]
    assert (await platform.post(LOGOUT, json={"refresh_token": session_data["refresh_token"]})).status_code == 200
    assert (
        await platform.post(REFRESH, json={"refresh_token": session_data["refresh_token"]})
    ).status_code == 401


async def test_a_platform_session_is_not_a_brand_token(client, tenant, brand_a):
    """The platform session must be exchanged; it never opens a brand's admin API.

    Sent to a registered store's host, so the refusal comes from authentication.
    """
    response = await client.get("/api/v1/admin/staff", headers=brand_a.owner.headers)
    assert response.status_code == 401


async def test_a_brand_token_is_not_a_platform_session(platform, brand_a):
    assert (await platform.get(ME, headers=brand_a.headers)).status_code == 401
