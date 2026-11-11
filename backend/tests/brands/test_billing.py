"""Plans, limits, and paying for a plan with Razorpay Subscriptions (faked)."""

from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.subscriptions import billing
from app.subscriptions.models import BrandSubscription
from tests.brands.conftest import create_product

BILLING = "/api/v1/brand/billing"
DOMAINS = "/api/v1/brand/domains"
ADMIN = "/api/v1/platform/admin"
KEY_SECRET = "platform-key-secret"
WEBHOOK_SECRET = "billing-webhook-secret"


@pytest.fixture
def razorpay_billing(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "razorpay_key_id", "rzp_test_Platform1")
    monkeypatch.setattr(settings, "razorpay_key_secret", KEY_SECRET)
    monkeypatch.setattr(settings, "razorpay_billing_webhook_secret", WEBHOOK_SECRET)
    calls: list[tuple[str, str, dict | None]] = []
    subs: dict[str, dict] = {}

    async def fake_call(method, path, body=None):
        calls.append((method, path, body))
        if path == "/plans":
            return {"id": f"plan_{body['notes']['plan_code']}"}
        if method == "POST" and path == "/subscriptions":
            sub_id = f"sub_{len(subs) + 1}"
            subs[sub_id] = {"id": sub_id, "notes": body["notes"], "start_at": body.get("start_at"), "short_url": "https://rzp.io/x"}
            return subs[sub_id]
        if method == "GET" and path.startswith("/subscriptions/"):
            return subs[path.split("/")[2]]
        if path.endswith("/cancel"):
            return {"id": path.split("/")[2], "status": "cancelled"}
        raise AssertionError(path)

    monkeypatch.setattr(billing, "_call", fake_call)
    return calls


def _signed(payment_id: str, sub_id: str) -> dict:
    sig = hmac.new(KEY_SECRET.encode(), f"{payment_id}|{sub_id}".encode(), hashlib.sha256).hexdigest()
    return {"razorpay_payment_id": payment_id, "razorpay_subscription_id": sub_id, "razorpay_signature": sig}


async def _webhook(platform, event: str, sub_id: str, **entity):
    body = json.dumps({"event": event, "payload": {"subscription": {"entity": {"id": sub_id, **entity}}}}).encode()
    sig = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return await platform.post(
        "/api/v1/billing/razorpay/webhook", content=body,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": sig},
    )


async def test_a_new_brand_is_on_free_with_its_limits(platform, make_merchant, make_brand):
    brand = await make_brand(await make_merchant("free@brands.example.com"), "Free Brand", plan="FREE")

    data = (await platform.get(BILLING, headers=brand.headers)).json()["data"]
    domain = await platform.post(DOMAINS, json={"domain": "shop.free.example"}, headers=brand.headers)

    assert data["plan"]["code"] == "FREE" and data["plan"]["product_limit"] == 25
    assert [p["code"] for p in data["plans"]] == ["FREE", "STARTER", "GROWTH"]
    assert data["usage"] == {"products": 0, "staff": 1}
    assert domain.status_code == 403 and domain.json()["error"]["code"] == "FEATURE_NOT_IN_PLAN"


async def test_the_product_limit_is_enforced(platform, session, make_merchant, make_brand):
    from app.subscriptions.models import SubscriptionPlan

    brand = await make_brand(await make_merchant("tiny@brands.example.com"), "Tiny Brand", plan="FREE")
    free = await session.scalar(select(SubscriptionPlan).where(SubscriptionPlan.code == "FREE"))
    free.product_limit = 1
    await session.commit()

    await create_product(platform, brand, "First")
    category = (await platform.get("/api/v1/catalogue/categories", headers=brand.headers)).json()["data"][0]
    second = await platform.post(
        "/api/v1/catalogue/products",
        json={"category_id": category["id"], "name": "Second", "status": "DRAFT",
              "images": [{"url": "https://cdn.example.com/p.jpg", "is_primary": True}]},
        headers=brand.headers,
    )  # fmt: skip

    assert second.status_code == 403
    assert second.json()["error"]["code"] == "PLAN_LIMIT_REACHED"


async def test_the_team_limit_is_enforced(platform, make_merchant, make_brand):
    owner = await make_merchant("solo@brands.example.com")
    brand = await make_brand(owner, "Solo Brand", plan="FREE")
    await make_merchant("helper@brands.example.com")

    response = await platform.post(
        f"/api/v1/brands/{brand.id}/members", json={"email": "helper@brands.example.com", "role": "ORDER_MANAGER"},
        headers=owner.headers,
    )

    assert response.status_code == 403 and response.json()["error"]["code"] == "PLAN_LIMIT_REACHED"


async def test_upgrading_starts_a_trial_then_webhooks_keep_it_current(
    platform, session, make_merchant, make_brand, razorpay_billing
):
    brand = await make_brand(await make_merchant("grow@brands.example.com"), "Grow Brand", plan="FREE")

    started = (await platform.post(f"{BILLING}/checkout", json={"plan_code": "STARTER"}, headers=brand.headers)).json()["data"]
    assert started["trial_days"] == 14 and started["key_id"] == "rzp_test_Platform1"
    create = next(c for c in razorpay_billing if c[1] == "/subscriptions")
    assert create[2]["notes"]["tenant_id"] == str(brand.id) and create[2]["start_at"] > time.time() + 13 * 86400

    forged = {**_signed("pay_1", started["subscription_id"]), "razorpay_signature": "0" * 64}
    assert (await platform.post(f"{BILLING}/confirm", json=forged, headers=brand.headers)).status_code == 400
    confirmed = await platform.post(f"{BILLING}/confirm", json=_signed("pay_1", started["subscription_id"]), headers=brand.headers)

    data = confirmed.json()["data"]
    assert confirmed.status_code == 200, confirmed.text
    assert data["plan"]["code"] == "STARTER" and data["subscription"]["status"] == "TRIALING"
    assert (await platform.post(DOMAINS, json={"domain": "shop.grow.example"}, headers=brand.headers)).status_code == 201

    # First charge after the trial.
    now = int(time.time())
    assert (await _webhook(platform, "subscription.charged", started["subscription_id"], current_start=now, current_end=now + 30 * 86400)).json()["data"]["result"] == "applied"
    sub = await session.scalar(select(BrandSubscription).where(BrandSubscription.tenant_id == brand.id))
    await session.refresh(sub)
    assert sub.status == "ACTIVE"

    # A failed renewal: paid limits stay during the grace period.
    await _webhook(platform, "subscription.halted", started["subscription_id"])
    data = (await platform.get(BILLING, headers=brand.headers)).json()["data"]
    assert data["subscription"]["status"] == "PAST_DUE" and data["effective_plan"]["code"] == "STARTER"

    # Cancelled for good: back to Free.
    await _webhook(platform, "subscription.cancelled", started["subscription_id"])
    data = (await platform.get(BILLING, headers=brand.headers)).json()["data"]
    assert data["plan"]["code"] == "FREE" and data["subscription"]["billing_provider"] == "manual"


async def test_the_trial_is_given_once(platform, make_merchant, make_brand, razorpay_billing):
    brand = await make_brand(await make_merchant("again@brands.example.com"), "Again Brand", plan="FREE")
    first = (await platform.post(f"{BILLING}/checkout", json={"plan_code": "STARTER"}, headers=brand.headers)).json()["data"]
    await platform.post(f"{BILLING}/confirm", json=_signed("pay_1", first["subscription_id"]), headers=brand.headers)

    second = (await platform.post(f"{BILLING}/checkout", json={"plan_code": "GROWTH"}, headers=brand.headers)).json()["data"]
    await platform.post(f"{BILLING}/confirm", json=_signed("pay_2", second["subscription_id"]), headers=brand.headers)

    assert second["trial_days"] == 0
    assert ("POST", f"/subscriptions/{first['subscription_id']}/cancel", {"cancel_at_cycle_end": 0}) in razorpay_billing


async def test_a_subscription_cannot_be_confirmed_by_another_brand(platform, make_merchant, make_brand, razorpay_billing):
    a = await make_brand(await make_merchant("a1@brands.example.com"), "A One", plan="FREE")
    b = await make_brand(await make_merchant("b1@brands.example.com"), "B One", plan="FREE")
    started = (await platform.post(f"{BILLING}/checkout", json={"plan_code": "STARTER"}, headers=a.headers)).json()["data"]

    response = await platform.post(f"{BILLING}/confirm", json=_signed("pay_1", started["subscription_id"]), headers=b.headers)

    assert response.status_code == 400


async def test_a_forged_billing_webhook_is_refused(platform, razorpay_billing):
    body = b'{"event":"subscription.cancelled"}'
    response = await platform.post(
        "/api/v1/billing/razorpay/webhook", content=body,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": "bad"},
    )
    assert response.status_code == 401


async def test_operators_edit_prices_and_assign_plans(platform, session, make_merchant, make_brand):
    admin = await make_merchant("ops@cliq.example.com", platform_admin=True)
    brand = await make_brand(await make_merchant("vip@brands.example.com"), "VIP Brand", plan="FREE")
    plans = (await platform.get(f"{ADMIN}/plans", headers=admin.headers)).json()["data"]
    starter = next(p for p in plans if p["code"] == "STARTER")

    saved = await platform.put(
        f"{ADMIN}/plans/STARTER", json={**starter, "monthly_price": 149900}, headers=admin.headers
    )
    assigned = await platform.put(f"{ADMIN}/brands/{brand.id}/plan", json={"plan_code": "GROWTH"}, headers=admin.headers)
    owner_try = await platform.put(f"{ADMIN}/plans/STARTER", json=starter, headers=brand.owner.headers)

    assert saved.json()["data"]["monthly_price"] == 149900
    assert assigned.status_code == 200
    assert (await platform.get(BILLING, headers=brand.headers)).json()["data"]["plan"]["code"] == "GROWTH"
    assert owner_try.status_code == 403
