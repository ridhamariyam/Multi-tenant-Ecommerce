"""F13: billing webhooks are idempotent, ordered and cannot undo a cancellation."""

from __future__ import annotations

import hashlib
import hmac
import json
import time

from sqlalchemy import func, select

from app.ai.models import AiUsageLedger
from app.subscriptions.models import BillingWebhookEvent, BrandSubscription
from tests.brands.test_billing import BILLING, WEBHOOK_SECRET, _signed, razorpay_billing  # noqa: F401

HOOK = "/api/v1/billing/razorpay/webhook"


async def _send(platform, event: str, sub_id: str, *, event_id: str, created_at: int, **entity):
    body = json.dumps(
        {"event": event, "created_at": created_at, "payload": {"subscription": {"entity": {"id": sub_id, **entity}}}}
    ).encode()
    sig = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    response = await platform.post(
        HOOK, content=body,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": sig, "X-Razorpay-Event-Id": event_id},
    )  # fmt: skip
    assert response.status_code == 200, response.text
    return response.json()["data"]["result"]


async def _paid_brand(platform, make_merchant, make_brand, email: str, plan: str = "BASIC"):
    brand = await make_brand(await make_merchant(email), email.split("@")[0], plan="TRIAL")
    started = (await platform.post(f"{BILLING}/checkout", json={"plan_code": plan}, headers=brand.headers)).json()["data"]
    confirmed = await platform.post(f"{BILLING}/confirm", json=_signed("pay_1", started["subscription_id"]), headers=brand.headers)
    assert confirmed.status_code == 200, confirmed.text
    return brand, started["subscription_id"]


async def _sub(session, brand) -> BrandSubscription:
    sub = await session.scalar(select(BrandSubscription).where(BrandSubscription.tenant_id == brand.id))
    await session.refresh(sub)
    return sub


async def _billing(platform, brand) -> dict:
    return (await platform.get(BILLING, headers=brand.headers)).json()["data"]


async def test_a_delayed_charge_after_cancellation_keeps_the_brand_cancelled(
    platform, session, make_merchant, make_brand, razorpay_billing
):
    brand, sub_id = await _paid_brand(platform, make_merchant, make_brand, "late@brands.example.com")
    t = int(time.time())
    month = 30 * 86400

    # 1. An active subscription receives a valid payment.
    assert await _send(platform, "subscription.charged", sub_id, event_id="evt_1", created_at=t,
                       current_start=t, current_end=t + month, status="active") == "applied"  # fmt: skip
    assert (await _sub(session, brand)).status == "ACTIVE"
    # 2. It is cancelled.
    assert await _send(platform, "subscription.cancelled", sub_id, event_id="evt_2", created_at=t + 60, status="cancelled") == "applied"
    # 3. A delayed charge (sent before the cancellation, retried after) arrives.
    late = await _send(platform, "subscription.charged", sub_id, event_id="evt_0", created_at=t - 60,
                       current_start=t, current_end=t + month, status="active")  # fmt: skip
    # 4. The brand stays cancelled (paused until it pays again).
    data = await _billing(platform, brand)
    assert late == "ignored"
    assert data["subscription"]["status"] == "CANCELLED" and data["paused"] is True
    assert data["subscription"]["billing_provider"] == "manual"
    logged = await session.scalar(select(BillingWebhookEvent).where(BillingWebhookEvent.provider_event_id == "evt_0"))
    assert logged.outcome == "ignored" and "ended" in logged.reason


async def test_a_charge_reporting_a_cancelled_subscription_is_rejected(
    platform, session, make_merchant, make_brand, razorpay_billing
):
    """Owner cancels at period end; a charge event whose payload says cancelled cannot reactivate."""
    brand, sub_id = await _paid_brand(platform, make_merchant, make_brand, "endof@brands.example.com")
    t = int(time.time())
    await _send(platform, "subscription.charged", sub_id, event_id="evt_paid", created_at=t,
                current_start=t, current_end=t + 30 * 86400, status="active")  # fmt: skip
    assert (await platform.post(f"{BILLING}/cancel", headers=brand.headers)).status_code == 200
    assert (await _sub(session, brand)).cancel_at_period_end is True

    result = await _send(platform, "subscription.charged", sub_id, event_id="evt_c", created_at=t + 5, status="cancelled")

    assert result == "rejected"
    logged = await session.scalar(select(BillingWebhookEvent).where(BillingWebhookEvent.provider_event_id == "evt_c"))
    assert logged.tenant_id == brand.id and "cancelled" in logged.reason


async def test_duplicate_cancellations_are_no_ops(platform, session, make_merchant, make_brand, razorpay_billing):
    brand, sub_id = await _paid_brand(platform, make_merchant, make_brand, "twice@brands.example.com")
    t = int(time.time())

    first = await _send(platform, "subscription.cancelled", sub_id, event_id="evt_x", created_at=t, status="cancelled")
    retry = await _send(platform, "subscription.cancelled", sub_id, event_id="evt_x", created_at=t, status="cancelled")
    other = await _send(platform, "subscription.cancelled", sub_id, event_id="evt_y", created_at=t + 1, status="cancelled")

    assert (first, retry, other) == ("applied", "duplicate", "ignored")
    count = await session.scalar(select(func.count()).select_from(BillingWebhookEvent).where(BillingWebhookEvent.provider_event_id == "evt_x"))
    assert count == 1
    assert (await _billing(platform, brand))["subscription"]["status"] == "CANCELLED"


async def test_a_new_subscription_after_cancellation_activates(
    platform, session, make_merchant, make_brand, razorpay_billing
):
    brand, old_id = await _paid_brand(platform, make_merchant, make_brand, "back@brands.example.com")
    t = int(time.time())
    await _send(platform, "subscription.cancelled", old_id, event_id="evt_end", created_at=t + 1000, status="cancelled")

    started = (await platform.post(f"{BILLING}/checkout", json={"plan_code": "PRO"}, headers=brand.headers)).json()["data"]
    await platform.post(f"{BILLING}/confirm", json=_signed("pay_2", started["subscription_id"]), headers=brand.headers)
    # Its first charge is older than the old subscription's last event: ordering is per subscription.
    result = await _send(platform, "subscription.charged", started["subscription_id"], event_id="evt_new",
                         created_at=t + 10, current_start=t, current_end=t + 30 * 86400, status="active")  # fmt: skip

    data = await _billing(platform, brand)
    assert result == "applied"
    assert data["plan"]["code"] == "PRO" and data["subscription"]["status"] == "ACTIVE"
    assert data["paused"] is False


async def test_out_of_order_events_do_not_overwrite_newer_state(
    platform, session, make_merchant, make_brand, razorpay_billing
):
    brand, sub_id = await _paid_brand(platform, make_merchant, make_brand, "order@brands.example.com")
    t = int(time.time())

    # The renewal succeeded (t+100), but the earlier halt (t) is delivered after it.
    assert await _send(platform, "subscription.charged", sub_id, event_id="evt_ok", created_at=t + 100,
                       current_start=t, current_end=t + 30 * 86400, status="active") == "applied"  # fmt: skip
    stale = await _send(platform, "subscription.halted", sub_id, event_id="evt_halt", created_at=t, status="halted")

    sub = await _sub(session, brand)
    assert stale == "rejected"
    assert sub.status == "ACTIVE" and sub.past_due_since is None
    # A genuinely newer halt is still applied.
    assert await _send(platform, "subscription.halted", sub_id, event_id="evt_halt2", created_at=t + 200, status="halted") == "applied"
    assert (await _sub(session, brand)).status == "PAST_DUE"


async def test_webhook_retries_do_not_duplicate_credit_grants(
    platform, session, make_merchant, make_brand, razorpay_billing
):
    brand, sub_id = await _paid_brand(platform, make_merchant, make_brand, "credits@brands.example.com", plan="PRO")
    t = int(time.time())
    period = {"current_start": t + 86400 * 14, "current_end": t + 86400 * 44, "status": "active"}

    results = [
        await _send(platform, "subscription.charged", sub_id, event_id="evt_pay", created_at=t, **period),
        await _send(platform, "subscription.charged", sub_id, event_id="evt_pay", created_at=t, **period),
        # Razorpay can also emit a second event for the same charge (new id, same period).
        await _send(platform, "subscription.charged", sub_id, event_id="evt_pay_b", created_at=t + 1, **period),
    ]

    grants = await session.scalar(
        select(func.count()).select_from(AiUsageLedger).where(
            AiUsageLedger.tenant_id == brand.id, AiUsageLedger.reference.like("plan:PRO:%")
        )
    )
    assert results == ["applied", "duplicate", "applied"]
    # One grant for the trial period (at confirm) and one for the first paid period.
    assert grants == 2


async def test_an_event_naming_another_brand_is_rejected(
    platform, session, make_merchant, make_brand, razorpay_billing
):
    brand, sub_id = await _paid_brand(platform, make_merchant, make_brand, "own@brands.example.com")
    other = await make_brand(await make_merchant("thief@brands.example.com"), "Thief", plan="TRIAL")
    t = int(time.time())

    result = await _send(platform, "subscription.cancelled", sub_id, event_id="evt_t", created_at=t,
                         status="cancelled", notes={"tenant_id": str(other.id)})  # fmt: skip

    assert result == "rejected"
    data = await _billing(platform, brand)
    assert data["plan"]["code"] == "BASIC" and data["subscription"]["status"] != "CANCELLED"


async def test_an_unsigned_event_is_not_recorded(platform, session, razorpay_billing):
    body = json.dumps({"event": "subscription.charged", "created_at": 1, "payload": {}}).encode()
    response = await platform.post(HOOK, content=body, headers={"X-Razorpay-Signature": "bad", "X-Razorpay-Event-Id": "evt_forged"})

    assert response.status_code == 401
    assert await session.scalar(select(BillingWebhookEvent).where(BillingWebhookEvent.provider_event_id == "evt_forged")) is None
