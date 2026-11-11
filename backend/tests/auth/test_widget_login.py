"""The customer sign-in endpoint: one flow that both registers and logs in."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from app.auth.constants import UserRole, UserStatus
from app.auth.models import RefreshToken
from app.auth.security import hash_refresh_token
from app.users.models import User
from tests.conftest import widget_login

NEW_PHONE = "+919812340001"


async def test_a_new_number_becomes_a_verified_customer(client, session, tenant, msg91):
    response = await widget_login(client, msg91.token_for(NEW_PHONE))

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["message"] == "Login successful"

    tokens = body["data"]
    assert tokens["token_type"] == "bearer"
    assert tokens["access_token"] and tokens["refresh_token"]
    assert tokens["expires_in"] > 0

    created = await session.scalar(select(User).where(User.phone == NEW_PHONE))
    assert created.role == UserRole.CUSTOMER.value
    assert created.status == UserStatus.ACTIVE.value
    # MSG91 confirmed possession of the number; that is what verified means.
    assert created.is_verified is True
    # No password is set, and the schema's password_matches_role check would
    # reject a customer that had one.
    assert created.password_hash is None


async def test_an_existing_customer_is_logged_in_not_duplicated(
    client, session, tenant, user, msg91
):
    first = await widget_login(client, msg91.token_for(user.phone))
    second = await widget_login(client, msg91.token_for(user.phone))

    assert first.status_code == 200
    assert second.status_code == 200

    rows = (
        (await session.execute(select(User).where(User.phone == user.phone)))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].id == user.id


async def test_the_session_belongs_to_the_verified_number(client, tenant, msg91):
    tokens = (await widget_login(client, msg91.token_for(NEW_PHONE))).json()["data"]

    me = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert me.status_code == 200
    assert me.json()["data"]["phone"] == NEW_PHONE


async def test_a_token_msg91_never_verified_is_refused(client, session, tenant, msg91):
    response = await widget_login(client, "forged-token")

    assert response.status_code == 401
    assert await session.scalar(select(User)) is None


async def test_a_phone_number_cannot_be_supplied_alongside_the_token(client, tenant, msg91):
    """The payload has no phone field, so asserting an identity is rejected."""
    response = await client.post(
        "/api/v1/auth/widget/login",
        json={"access_token": msg91.token_for(NEW_PHONE), "phone": "+919999999999"},
    )

    assert response.status_code == 422


async def test_an_empty_token_is_rejected_before_msg91_is_asked(client, tenant, msg91):
    assert (await widget_login(client, "")).status_code == 422


async def test_staff_cannot_sign_in_through_the_customer_flow(
    client, tenant, make_user, msg91
):
    """Staff hold passwords and have their own route; this one must not let them past."""
    staff = await make_user(
        tenant=tenant, email="staff@zeen.com", role=UserRole.STAFF.value
    )

    response = await widget_login(client, msg91.token_for(staff.phone))

    assert response.status_code == 401


async def test_a_deactivated_customer_cannot_sign_back_in(
    client, tenant, make_user, msg91
):
    blocked = await make_user(tenant=tenant, status=UserStatus.INACTIVE.value)

    response = await widget_login(client, msg91.token_for(blocked.phone))

    assert response.status_code == 401


async def test_signing_out_revokes_the_session_and_signing_in_again_works(
    client, tenant, msg91
):
    tokens = (await widget_login(client, msg91.token_for(NEW_PHONE))).json()["data"]

    out = await client.post(
        "/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]}
    )
    assert out.status_code == 204

    reused = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert reused.status_code == 401

    again = await widget_login(client, msg91.token_for(NEW_PHONE))
    assert again.status_code == 200


async def test_the_existing_refresh_rotation_still_holds(client, session, tenant, msg91):
    tokens = (await widget_login(client, msg91.token_for(NEW_PHONE))).json()["data"]

    rotated = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert rotated.status_code == 200
    fresh = rotated.json()["data"]
    assert fresh["refresh_token"] != tokens["refresh_token"]

    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == hash_refresh_token(tokens["refresh_token"]))
        .values(replaced_at=datetime.now(timezone.utc) - timedelta(hours=1))
    )
    await session.commit()

    replayed = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert replayed.status_code == 401
    after_replay = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": fresh["refresh_token"]}
    )
    assert after_replay.status_code == 401
