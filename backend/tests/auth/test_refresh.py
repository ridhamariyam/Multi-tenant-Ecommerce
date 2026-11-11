"""Refresh-token rotation: parallel refreshes stay signed in, replays still revoke."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import update

from app.auth.models import RefreshToken
from app.auth.security import hash_refresh_token
from app.auth.service import AuthService
from app.core.config import get_settings
from tests.conftest import sign_in_customer
from tests.helpers import run_concurrently, succeeded

REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"
PHONE = "+919812349999"


async def _refresh(client, token: str):
    return await client.post(REFRESH, json={"refresh_token": token})


async def _age_rotation(session, token: str, seconds: int) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == hash_refresh_token(token))
        .values(replaced_at=datetime.now(timezone.utc) - timedelta(seconds=seconds))
    )
    await session.commit()


async def test_a_token_reused_moments_after_rotation_still_works(client, tenant, msg91):
    original = (await sign_in_customer(client, msg91, PHONE))["refresh_token"]

    first = await _refresh(client, original)
    second = await _refresh(client, original)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    for pair in (first, second):
        follow_up = await _refresh(client, pair.json()["data"]["refresh_token"])
        assert follow_up.status_code == 200, follow_up.text


async def test_a_token_replayed_after_the_window_revokes_every_session(
    client, session, tenant, msg91
):
    original = (await sign_in_customer(client, msg91, PHONE))["refresh_token"]
    rotated = (await _refresh(client, original)).json()["data"]["refresh_token"]
    await _age_rotation(session, original, get_settings().refresh_reuse_grace_seconds + 1)

    replay = await _refresh(client, original)

    assert replay.status_code == 401
    assert (await _refresh(client, rotated)).status_code == 401


async def test_a_logged_out_token_has_no_grace(client, tenant, msg91):
    pair = await sign_in_customer(client, msg91, PHONE)
    other = await sign_in_customer(client, msg91, PHONE)
    assert (await client.post(LOGOUT, json={"refresh_token": pair["refresh_token"]})).status_code == 204

    replay = await _refresh(client, pair["refresh_token"])

    assert replay.status_code == 401
    assert (await _refresh(client, other["refresh_token"])).status_code == 401


async def test_no_grace_when_it_is_switched_off(client, tenant, msg91, monkeypatch):
    monkeypatch.setattr(get_settings(), "refresh_reuse_grace_seconds", 0)
    original = (await sign_in_customer(client, msg91, PHONE))["refresh_token"]
    rotated = (await _refresh(client, original)).json()["data"]["refresh_token"]

    assert (await _refresh(client, original)).status_code == 401
    assert (await _refresh(client, rotated)).status_code == 401


async def test_revoking_everything_closes_the_grace_window(
    client, session, tenant, msg91
):
    original = (await sign_in_customer(client, msg91, PHONE))["refresh_token"]
    rotated = (await _refresh(client, original)).json()["data"]["refresh_token"]
    await _age_rotation(session, rotated, 10_000)
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == hash_refresh_token(rotated))
        .values(revoked_at=datetime.now(timezone.utc))
    )
    await session.commit()

    assert (await _refresh(client, rotated)).status_code == 401
    assert (await _refresh(client, original)).status_code == 401


async def test_an_expired_token_is_refused(client, session, tenant, msg91):
    original = (await sign_in_customer(client, msg91, PHONE))["refresh_token"]
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == hash_refresh_token(original))
        .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    )
    await session.commit()

    assert (await _refresh(client, original)).status_code == 401


async def test_two_refreshes_at_once_both_succeed(client, engine, tenant, msg91):
    original = (await sign_in_customer(client, msg91, PHONE))["refresh_token"]

    async def refresh(db, _index):
        return await AuthService(db, tenant).refresh_tokens(original)

    results = await run_concurrently(engine, 2, refresh)

    assert len(succeeded(results)) == 2, results
    for pair in results:
        assert (await _refresh(client, pair.refresh_token)).status_code == 200
