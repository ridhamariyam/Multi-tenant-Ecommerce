"""Marketing consent, campaigns to segments, unsubscribe, abandoned-cart reminders."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from sqlalchemy import select, update

from app.cart.models import Cart
from app.marketing.service import queue_cart_reminders, unsubscribe_token
from app.notifications.models import OutboxEmail
from app.stores.models import Store
from app.users.models import User
from tests.conftest import headers_for
from tests.orders.conftest import CART, CHECKOUT, address_payload

CAMPAIGNS = "/api/v1/admin/marketing/campaigns"


async def _guest(client, variant_id, phone, email, opt_in):
    cart = (await client.post(f"{CART}/guest")).json()["data"]
    headers = {"X-Cart-Token": cart["guest_token"]}
    await client.post(f"{CART}/items", json={"variant_id": variant_id, "quantity": 1}, headers=headers)
    response = await client.post(
        f"{CHECKOUT}/guest",
        json={"contact": {"name": "Shopper", "phone": phone, "email": email, "marketing_opt_in": opt_in},
              "address": address_payload()},
        headers=headers,
    )  # fmt: skip
    assert response.status_code == 201, response.text


async def _store(session, tenant):
    session.add(Store(tenant_id=tenant.id, name="Zeen", subdomain="zeen", published=True, published_at=datetime.now(timezone.utc)))
    await session.commit()


async def test_only_opted_in_customers_get_a_campaign_and_can_leave(client, session, tenant, admin_headers, variant):
    await _store(session, tenant)
    await _guest(client, variant["id"], "9833330011", "yes@example.com", True)
    await _guest(client, variant["id"], "9833330012", "no@example.com", False)

    summary = (await client.get("/api/v1/admin/marketing/summary", headers=admin_headers)).json()["data"]
    created = await client.post(
        CAMPAIGNS, json={"name": "Drop", "subject": "New drop", "body": "Hello\n\nNew pieces.", "segment": {"kind": "ALL"}},
        headers=admin_headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["data"]["audience"] == 1
    sent = await client.post(f"{CAMPAIGNS}/{created.json()['data']['id']}/send", headers=admin_headers)
    again = await client.post(f"{CAMPAIGNS}/{created.json()['data']['id']}/send", headers=admin_headers)

    assert summary == {"customers": 2, "subscribed": 1}
    assert sent.json()["data"]["recipients"] == 1 and again.status_code == 409
    emails = (await session.scalars(select(OutboxEmail).where(OutboxEmail.kind == "campaign"))).all()
    assert [e.to_address for e in emails] == ["yes@example.com"]
    link = next(line for line in emails[0].text_body.splitlines() if "unsubscribe?" in line).split(": ", 1)[1]
    q = parse_qs(urlsplit(link).query)

    bad = await client.post("/api/v1/storefront/unsubscribe", json={"u": q["u"][0], "t": "0" * 32})
    good = await client.post("/api/v1/storefront/unsubscribe", json={"u": q["u"][0], "t": q["t"][0]})
    assert bad.status_code == 400 and good.status_code == 200
    user = await session.scalar(select(User).where(User.id == UUID(q["u"][0])))
    await session.refresh(user)
    assert user.marketing_opt_in is False


async def test_segments_by_orders(client, session, tenant, admin_headers, variant, make_user):
    await _guest(client, variant["id"], "9833330021", "buyer@example.com", True)
    lurker = await make_user(tenant=tenant, phone="+919833330022", email="lurker@example.com")
    lurker.marketing_opt_in = True
    await session.commit()

    async def size(segment):
        return (await client.post("/api/v1/admin/marketing/audience", json=segment, headers=admin_headers)).json()["data"]["count"]

    assert await size({"kind": "ALL"}) == 2
    assert await size({"kind": "ORDERED_WITHIN", "days": 30}) == 1
    assert await size({"kind": "NO_ORDERS"}) == 1


async def test_staff_cannot_send_campaigns(client, staff_headers):
    response = await client.post(CAMPAIGNS, json={"name": "x", "subject": "y", "body": "z"}, headers=staff_headers)
    assert response.status_code == 403


async def test_customers_set_consent_on_their_profile(client, customer, customer_auth):
    response = await client.patch("/api/v1/auth/me", json={"marketing_opt_in": True}, headers=customer_auth)
    assert response.status_code == 200 and response.json()["data"]["marketing_opt_in"] is True


async def test_an_abandoned_cart_gets_one_reminder_if_opted_in(client, session, tenant, make_user, variant):
    await _store(session, tenant)
    keen = await make_user(tenant=tenant, phone="+919833330031", email="keen@example.com")
    shy = await make_user(tenant=tenant, phone="+919833330032", email="shy@example.com")
    keen.marketing_opt_in = True
    await session.commit()
    for user in (keen, shy):
        r = await client.post(f"{CART}/items", json={"variant_id": variant["id"], "quantity": 1}, headers=headers_for(user))
        assert r.status_code == 201, r.text
    await session.execute(update(Cart).values(last_activity_at=datetime.now(timezone.utc) - timedelta(hours=3)))
    await session.commit()

    assert await queue_cart_reminders(session) == 1
    assert await queue_cart_reminders(session) == 0
    (email,) = (await session.scalars(select(OutboxEmail).where(OutboxEmail.kind == "cart-reminder"))).all()
    assert email.to_address == "keen@example.com" and "/cart" in email.text_body
    assert unsubscribe_token(tenant.id, keen.id) in email.text_body
