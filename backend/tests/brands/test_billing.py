"""Basic/Pro plans, the free Basic trial, pausing, and paying with Razorpay Subscriptions (faked)."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone

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


RESOLVE = "/api/v1/storefront/resolve"


def at(brand) -> dict:
    return {"Host": f"{brand.subdomain}.localhost"}


async def _publish(platform, brand) -> None:
    r = await platform.post("/api/v1/brand/store/publish", json={"published": True}, headers=brand.headers)
    assert r.status_code == 200, r.text


async def _expire_trial(session, brand) -> None:
    sub = await session.scalar(select(BrandSubscription).where(BrandSubscription.tenant_id == brand.id))
    sub.current_period_start = datetime.now(timezone.utc) - timedelta(days=15)
    sub.current_period_end = datetime.now(timezone.utc) - timedelta(minutes=1)
    await session.commit()


async def test_a_new_brand_starts_a_14_day_basic_trial(platform, make_merchant, make_brand):
    brand = await make_brand(await make_merchant("new@brands.example.com"), "New Brand", plan="TRIAL")
    await _publish(platform, brand)

    data = (await platform.get(BILLING, headers=brand.headers)).json()["data"]

    assert data["plan"]["code"] == "BASIC" and data["subscription"]["status"] == "TRIALING"
    assert data["subscription"]["billing_provider"] == "manual"  # no payment details needed
    assert data["trial_days_left"] == 14 and data["paused"] is False
    assert [p["code"] for p in data["plans"]] == ["BASIC", "PRO"]
    basic, pro = data["plans"]
    assert (basic["monthly_price"], basic["monthly_price_with_gst"]) == (499900, 589882)
    assert (pro["monthly_price"], pro["monthly_price_with_gst"]) == (899900, 1061882)
    assert data["gst_percent"] == 18
    assert basic["features"]["ai_studio"] is False and pro["features"]["ai_studio"] is True
    assert (await platform.get(RESOLVE, headers=at(brand))).status_code == 200


async def test_an_unpaid_trial_pauses_the_store_but_not_the_console(platform, session, make_merchant, make_brand):
    brand = await make_brand(await make_merchant("lapse@brands.example.com"), "Lapse Brand", plan="TRIAL")
    await _publish(platform, brand)
    await _expire_trial(session, brand)

    public = await platform.get(RESOLVE, headers=at(brand))
    staff_preview = await platform.get(RESOLVE, headers={**at(brand), **brand.headers})
    data = (await platform.get(BILLING, headers=brand.headers)).json()["data"]
    orders = await platform.get("/api/v1/admin/orders", headers=brand.headers)

    assert public.status_code == 404 and public.json()["error"]["code"] == "UNKNOWN_STOREFRONT"
    assert staff_preview.status_code == 200
    assert data["paused"] is True and data["subscription"]["lapsed"] is True
    assert orders.status_code == 200  # existing orders stay manageable


async def test_the_product_limit_is_enforced(platform, session, make_merchant, make_brand):
    from app.subscriptions.models import SubscriptionPlan

    brand = await make_brand(await make_merchant("tiny@brands.example.com"), "Tiny Brand", plan="TRIAL")
    basic = await session.scalar(select(SubscriptionPlan).where(SubscriptionPlan.code == "BASIC"))
    basic.product_limit = 1
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


async def test_the_team_limit_is_enforced(platform, session, make_merchant, make_brand):
    from app.subscriptions.models import SubscriptionPlan

    owner = await make_merchant("solo@brands.example.com")
    brand = await make_brand(owner, "Solo Brand", plan="TRIAL")
    basic = await session.scalar(select(SubscriptionPlan).where(SubscriptionPlan.code == "BASIC"))
    basic.staff_limit = 1
    await session.commit()
    await make_merchant("helper@brands.example.com")

    response = await platform.post(
        f"/api/v1/brands/{brand.id}/members", json={"email": "helper@brands.example.com", "role": "ORDER_MANAGER"},
        headers=owner.headers,
    )

    assert response.status_code == 403 and response.json()["error"]["code"] == "PLAN_LIMIT_REACHED"


async def test_basic_has_no_ai_studio(session, make_merchant, make_brand):
    from app.core.exceptions import PermissionDeniedError
    from app.subscriptions.service import SubscriptionService

    brand = await make_brand(await make_merchant("noai@brands.example.com"), "No AI", plan="TRIAL")

    with pytest.raises(PermissionDeniedError):
        await SubscriptionService(session, brand.id).require_feature("ai_studio")


async def test_paying_during_the_trial_charges_from_its_end_with_gst(
    platform, session, make_merchant, make_brand, razorpay_billing
):
    brand = await make_brand(await make_merchant("early@brands.example.com"), "Early Brand", plan="TRIAL")
    sub = await session.scalar(select(BrandSubscription).where(BrandSubscription.tenant_id == brand.id))
    trial_end = int(sub.current_period_end.timestamp())

    started = (await platform.post(f"{BILLING}/checkout", json={"plan_code": "BASIC"}, headers=brand.headers)).json()["data"]
    plan_call = next(c for c in razorpay_billing if c[1] == "/plans")
    create = next(c for c in razorpay_billing if c[1] == "/subscriptions")

    assert plan_call[2]["item"]["amount"] == 589882  # ₹4,999 + 18% GST
    assert started["amount"] == 589882 and started["amount_before_gst"] == 499900
    assert create[2]["start_at"] == trial_end and started["trial_days"] in (13, 14)
    assert create[2]["notes"]["tenant_id"] == str(brand.id)

    forged = {**_signed("pay_1", started["subscription_id"]), "razorpay_signature": "0" * 64}
    assert (await platform.post(f"{BILLING}/confirm", json=forged, headers=brand.headers)).status_code == 400
    confirmed = await platform.post(f"{BILLING}/confirm", json=_signed("pay_1", started["subscription_id"]), headers=brand.headers)
    data = confirmed.json()["data"]
    assert confirmed.status_code == 200, confirmed.text
    assert data["subscription"]["status"] == "TRIALING" and data["subscription"]["billing_provider"] == "razorpay"

    # Trial over, Razorpay's first charge not reported yet: still open (grace).
    await _expire_trial(session, brand)
    assert (await platform.get(BILLING, headers=brand.headers)).json()["data"]["paused"] is False

    now = int(time.time())
    assert (await _webhook(platform, "subscription.charged", started["subscription_id"], current_start=now, current_end=now + 30 * 86400)).json()["data"]["result"] == "applied"
    data = (await platform.get(BILLING, headers=brand.headers)).json()["data"]
    assert data["subscription"]["status"] == "ACTIVE" and data["paused"] is False


async def test_paying_after_the_trial_reopens_the_store(platform, session, make_merchant, make_brand, razorpay_billing):
    brand = await make_brand(await make_merchant("late@brands.example.com"), "Late Brand", plan="TRIAL")
    await _publish(platform, brand)
    await _expire_trial(session, brand)
    assert (await platform.get(RESOLVE, headers=at(brand))).status_code == 404

    started = (await platform.post(f"{BILLING}/checkout", json={"plan_code": "PRO"}, headers=brand.headers)).json()["data"]
    create = next(c for c in razorpay_billing if c[1] == "/subscriptions")
    confirmed = await platform.post(f"{BILLING}/confirm", json=_signed("pay_1", started["subscription_id"]), headers=brand.headers)

    assert "start_at" not in create[2] and started["trial_days"] == 0  # charged now
    assert confirmed.json()["data"]["subscription"]["status"] == "ACTIVE"
    assert confirmed.json()["data"]["plan"]["code"] == "PRO"
    assert (await platform.get(RESOLVE, headers=at(brand))).status_code == 200


async def test_failed_renewals_keep_the_store_open_during_grace_then_cancellation_pauses_it(
    platform, session, make_merchant, make_brand, razorpay_billing
):
    brand = await make_brand(await make_merchant("renew@brands.example.com"), "Renew Brand", plan="TRIAL")
    await _publish(platform, brand)
    await _expire_trial(session, brand)
    started = (await platform.post(f"{BILLING}/checkout", json={"plan_code": "BASIC"}, headers=brand.headers)).json()["data"]
    await platform.post(f"{BILLING}/confirm", json=_signed("pay_1", started["subscription_id"]), headers=brand.headers)

    await _webhook(platform, "subscription.halted", started["subscription_id"])
    data = (await platform.get(BILLING, headers=brand.headers)).json()["data"]
    assert data["subscription"]["status"] == "PAST_DUE" and data["paused"] is False

    await _webhook(platform, "subscription.cancelled", started["subscription_id"])
    data = (await platform.get(BILLING, headers=brand.headers)).json()["data"]
    assert data["subscription"]["status"] == "CANCELLED" and data["paused"] is True
    assert data["plan"]["code"] == "BASIC"  # nothing downgraded or deleted
    assert (await platform.get(RESOLVE, headers=at(brand))).status_code == 404


async def test_cancelling_during_the_trial_keeps_the_trial(platform, session, make_merchant, make_brand, razorpay_billing):
    brand = await make_brand(await make_merchant("undo@brands.example.com"), "Undo Brand", plan="TRIAL")
    started = (await platform.post(f"{BILLING}/checkout", json={"plan_code": "BASIC"}, headers=brand.headers)).json()["data"]
    await platform.post(f"{BILLING}/confirm", json=_signed("pay_1", started["subscription_id"]), headers=brand.headers)

    cancelled = await platform.post(f"{BILLING}/cancel", headers=brand.headers)

    data = cancelled.json()["data"]
    assert ("POST", f"/subscriptions/{started['subscription_id']}/cancel", {"cancel_at_cycle_end": 0}) in razorpay_billing
    assert data["subscription"]["status"] == "TRIALING" and data["subscription"]["billing_provider"] == "manual"
    assert data["paused"] is False and data["trial_days_left"] >= 13


async def test_switching_plans_cancels_the_old_subscription(platform, session, make_merchant, make_brand, razorpay_billing):
    brand = await make_brand(await make_merchant("again@brands.example.com"), "Again Brand", plan="TRIAL")
    first = (await platform.post(f"{BILLING}/checkout", json={"plan_code": "BASIC"}, headers=brand.headers)).json()["data"]
    await platform.post(f"{BILLING}/confirm", json=_signed("pay_1", first["subscription_id"]), headers=brand.headers)

    second = (await platform.post(f"{BILLING}/checkout", json={"plan_code": "PRO"}, headers=brand.headers)).json()["data"]
    await platform.post(f"{BILLING}/confirm", json=_signed("pay_2", second["subscription_id"]), headers=brand.headers)

    data = (await platform.get(BILLING, headers=brand.headers)).json()["data"]
    assert data["plan"]["code"] == "PRO"
    assert ("POST", f"/subscriptions/{first['subscription_id']}/cancel", {"cancel_at_cycle_end": 0}) in razorpay_billing


async def test_a_subscription_cannot_be_confirmed_by_another_brand(platform, make_merchant, make_brand, razorpay_billing):
    a = await make_brand(await make_merchant("a1@brands.example.com"), "A One", plan="TRIAL")
    b = await make_brand(await make_merchant("b1@brands.example.com"), "B One", plan="TRIAL")
    started = (await platform.post(f"{BILLING}/checkout", json={"plan_code": "BASIC"}, headers=a.headers)).json()["data"]

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
    brand = await make_brand(await make_merchant("vip@brands.example.com"), "VIP Brand", plan="TRIAL")
    plans = (await platform.get(f"{ADMIN}/plans", headers=admin.headers)).json()["data"]
    basic = next(p for p in plans if p["code"] == "BASIC")

    saved = await platform.put(
        f"{ADMIN}/plans/BASIC", json={**basic, "monthly_price": 549900}, headers=admin.headers
    )
    assigned = await platform.put(f"{ADMIN}/brands/{brand.id}/plan", json={"plan_code": "PRO"}, headers=admin.headers)
    owner_try = await platform.put(f"{ADMIN}/plans/BASIC", json=basic, headers=brand.owner.headers)

    assert saved.json()["data"]["monthly_price"] == 549900
    assert assigned.status_code == 200
    assert (await platform.get(BILLING, headers=brand.headers)).json()["data"]["plan"]["code"] == "PRO"
    assert owner_try.status_code == 403
