"""Merchants reset a forgotten password by an emailed, single-use link."""

from __future__ import annotations

import re
from urllib.parse import unquote

from sqlalchemy import select

from app.notifications.models import OutboxEmail
from tests.brands.conftest import PASSWORD

AUTH = "/api/v1/platform/auth"
NEW_PASSWORD = "a-brand-new-passphrase"


async def _link_token(session) -> str:
    sent = (await session.scalars(select(OutboxEmail).where(OutboxEmail.kind == "merchant-password-reset"))).all()
    assert len(sent) == 1
    match = re.search(r"reset-password\?token=(\S+)", sent[0].text_body)
    assert match
    return unquote(match.group(1))


async def test_a_reset_link_is_emailed_and_works_once(platform, session, make_merchant):
    owner = await make_merchant("owner@alpha.example")
    login = await platform.post(f"{AUTH}/login", json={"email": "owner@alpha.example", "password": PASSWORD})
    old_refresh = login.json()["data"]["refresh_token"]

    asked = await platform.post(f"{AUTH}/password/forgot", json={"email": "Owner@Alpha.example"})
    token = await _link_token(session)
    email = await session.scalar(select(OutboxEmail))
    assert asked.status_code == 200
    assert email.to_address == "owner@alpha.example" and email.tenant_id is None
    assert token not in str(email.dedupe_key)  # only a hash is kept anywhere else

    reset = await platform.post(f"{AUTH}/password/reset", json={"token": token, "password": NEW_PASSWORD})
    again = await platform.post(f"{AUTH}/password/reset", json={"token": token, "password": "another-passphrase-1"})

    assert reset.status_code == 200, reset.text
    assert again.status_code == 400
    old = await platform.post(f"{AUTH}/login", json={"email": "owner@alpha.example", "password": PASSWORD})
    new = await platform.post(f"{AUTH}/login", json={"email": "owner@alpha.example", "password": NEW_PASSWORD})
    assert old.status_code == 401 and new.status_code == 200
    # Sessions from before the reset are over.
    assert (await platform.post(f"{AUTH}/refresh", json={"refresh_token": old_refresh})).status_code == 401
    assert owner.account.email == "owner@alpha.example"


async def test_an_unknown_email_gets_the_same_answer_and_no_email(platform, session):
    response = await platform.post(f"{AUTH}/password/forgot", json={"email": "nobody@nowhere.example"})

    assert response.status_code == 200
    assert "If an account uses that email" in response.json()["message"]
    assert (await session.scalars(select(OutboxEmail))).all() == []


async def test_a_made_up_token_is_refused(platform):
    response = await platform.post(f"{AUTH}/password/reset", json={"token": "x" * 43, "password": NEW_PASSWORD})
    assert response.status_code == 400
    assert response.json()["error"]["details"][0]["field"] == "token"
