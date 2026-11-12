"""Brands pay for their plan with Razorpay Subscriptions (the platform's account).

Every brand starts on a free Basic trial with no payment details. Flow: the
console asks for a checkout (a Razorpay subscription is created; if the trial
is still running, its first charge is at the trial's end) → the owner
authorises it in Razorpay Checkout → the signed result is verified here and
the plan switches → Razorpay webhooks keep the status right from then on
(renewals, failed charges, cancellation). Prices are before GST; Razorpay
charges price + PLATFORM_GST_PERCENT. Brands' own Razorpay accounts are never
used. A subscription that ends leaves the brand paused (CANCELLED), not deleted.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.error_codes import BillingErrorCode, PaymentErrorCode
from app.core.exceptions import (
    AuthenticationError,
    ConflictError,
    ServiceUnavailableError,
    ValidationError,
)
from app.payments import razorpay
from app.subscriptions.constants import SubscriptionStatus
from app.subscriptions.models import BillingWebhookEvent, BrandSubscription, SubscriptionPlan
from app.subscriptions.service import SubscriptionService, _add_month, grant_allowance, gross_amount, plan_by_code
from app.tenants.models import Tenant

logger = logging.getLogger(__name__)

UNAVAILABLE = "Online billing is not set up yet. Contact the platform team to change plans."
TOTAL_CYCLES = 120  # ten years of monthly renewals; Razorpay requires a count


def _creds() -> razorpay.Credentials:
    creds = razorpay.env_credentials()
    if creds is None:
        raise ServiceUnavailableError(UNAVAILABLE, error_code=PaymentErrorCode.GATEWAY_UNAVAILABLE)
    return creds


async def _call(method: str, path: str, body: dict | None = None) -> dict[str, Any]:
    creds = _creds()
    try:
        async with httpx.AsyncClient(timeout=creds.timeout_seconds) as client:
            response = await client.request(
                method, f"{creds.api_url}{path}", json=body, auth=(creds.key_id, creds.key_secret)
            )
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ServiceUnavailableError(
            "Could not reach Razorpay. Try again shortly.", error_code=PaymentErrorCode.GATEWAY_UNAVAILABLE
        ) from exc
    if response.status_code != 200 or not isinstance(payload, dict):
        description = payload.get("error", {}).get("description") if isinstance(payload, dict) else None
        logger.warning("razorpay billing %s %s -> %s %s", method, path.split("/")[1], response.status_code, description)
        raise ServiceUnavailableError(
            "Razorpay could not set up the subscription. Try again shortly.",
            error_code=PaymentErrorCode.GATEWAY_UNAVAILABLE,
        )
    return payload


async def ensure_razorpay_plan(session: AsyncSession, plan: SubscriptionPlan) -> str:
    if plan.razorpay_plan_id:
        return plan.razorpay_plan_id
    created = await _call(
        "POST",
        "/plans",
        {
            "period": "monthly",
            "interval": 1,
            "item": {
                "name": f"CliQ {plan.name} (incl. GST)",
                "amount": gross_amount(plan.monthly_price),
                "currency": plan.currency,
            },
            "notes": {"plan_code": plan.code, "price_before_gst": str(plan.monthly_price)},
        },
    )
    plan.razorpay_plan_id = str(created["id"])
    await session.commit()
    return plan.razorpay_plan_id


async def start_checkout(session: AsyncSession, tenant: Tenant, plan_code: str) -> dict[str, Any]:
    """Create the Razorpay subscription the owner will authorise in Checkout."""
    plan = await plan_by_code(session, plan_code)
    if not plan.is_active or plan.monthly_price <= 0:
        raise ValidationError("Choose one of the paid plans.", error_code=BillingErrorCode.PLAN_NOT_FOUND)
    subscription = await session.scalar(select(BrandSubscription).where(BrandSubscription.tenant_id == tenant.id))
    if subscription is None:
        raise ConflictError("This brand has no subscription record.")
    if (
        subscription.plan_id == plan.id
        and subscription.billing_provider == "razorpay"
        and subscription.status in (SubscriptionStatus.ACTIVE.value, SubscriptionStatus.TRIALING.value)
    ):
        raise ConflictError(f"You are already on the {plan.name} plan.")

    razorpay_plan_id = await ensure_razorpay_plan(session, plan)
    now = datetime.now(timezone.utc)
    # Paying during the free trial: the first charge waits for the trial's end.
    trial_end = (
        subscription.current_period_end
        if subscription.status == SubscriptionStatus.TRIALING.value and subscription.current_period_end > now
        else None
    )
    body: dict[str, Any] = {
        "plan_id": razorpay_plan_id,
        "total_count": TOTAL_CYCLES,
        "quantity": 1,
        "customer_notify": 1,
        "notes": {"tenant_id": str(tenant.id), "plan_code": plan.code},
    }
    if trial_end is not None:
        body["start_at"] = int(trial_end.timestamp())
    created = await _call("POST", "/subscriptions", body)
    subscription.pending_plan_id = plan.id
    # The new subscription replaces the stored id only once it is authorised.
    pending_id = str(created["id"])
    await session.commit()
    return {
        "subscription_id": pending_id,
        "key_id": _creds().key_id,
        "plan_code": plan.code,
        "plan_name": plan.name,
        "amount": gross_amount(plan.monthly_price),
        "amount_before_gst": plan.monthly_price,
        "currency": plan.currency,
        "trial_days": max(0, (trial_end - now).days) if trial_end else 0,
        "first_charge_at": trial_end,
        "short_url": created.get("short_url"),
    }


def _signature_ok(payment_id: str, subscription_id: str, signature: str) -> bool:
    expected = hmac.new(_creds().key_secret.encode(), f"{payment_id}|{subscription_id}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


async def confirm_checkout(
    session: AsyncSession, tenant_id: uuid.UUID, *, payment_id: str, subscription_id: str, signature: str
) -> BrandSubscription:
    if not _signature_ok(payment_id, subscription_id, signature):
        raise ValidationError("The payment could not be verified.", error_code=PaymentErrorCode.INVALID_SIGNATURE)
    remote = await _call("GET", f"/subscriptions/{subscription_id}")
    if (remote.get("notes") or {}).get("tenant_id") != str(tenant_id):
        raise ValidationError("This subscription belongs to another brand.", error_code=PaymentErrorCode.VERIFICATION_FAILED)
    subscription = await session.scalar(
        select(BrandSubscription).where(BrandSubscription.tenant_id == tenant_id).with_for_update()
    )
    plan = await plan_by_code(session, (remote.get("notes") or {}).get("plan_code", ""))
    previous = subscription.external_subscription_id if subscription.billing_provider == "razorpay" else None

    now = datetime.now(timezone.utc)
    start_at = remote.get("start_at")
    trialing = bool(start_at) and int(start_at) > now.timestamp()
    subscription.plan_id = plan.id
    subscription.pending_plan_id = None
    subscription.billing_provider = "razorpay"
    if subscription.external_subscription_id != subscription_id:
        subscription.provider_event_at = None  # ordering is per Razorpay subscription
    subscription.external_subscription_id = subscription_id
    subscription.cancel_at_period_end = False
    subscription.past_due_since = None
    subscription.current_period_start = now
    if trialing:
        subscription.status = SubscriptionStatus.TRIALING.value
        subscription.trial_used = True
        subscription.current_period_end = datetime.fromtimestamp(int(start_at), timezone.utc)
    else:
        subscription.status = SubscriptionStatus.ACTIVE.value
        subscription.trial_used = True
        subscription.current_period_end = _add_month(now)
    await session.flush()
    await grant_allowance(session, tenant_id, plan, subscription.current_period_start)
    await session.commit()

    if previous and previous != subscription_id:
        # Switching plans: stop billing the old one now.
        try:
            await _call("POST", f"/subscriptions/{previous}/cancel", {"cancel_at_cycle_end": 0})
        except ServiceUnavailableError:
            logger.error("could not cancel replaced subscription %s for tenant %s", previous, tenant_id)
    return subscription


async def cancel(session: AsyncSession, tenant_id: uuid.UUID) -> BrandSubscription:
    """Stop renewing; the paid plan lasts until the end of the period already paid."""
    subscription = await session.scalar(select(BrandSubscription).where(BrandSubscription.tenant_id == tenant_id))
    if subscription is None or subscription.billing_provider != "razorpay" or not subscription.external_subscription_id:
        raise ConflictError("There is no paid subscription to cancel.")
    if subscription.status == SubscriptionStatus.TRIALING.value:
        # Nothing has been charged yet: drop the mandate; the free trial runs on.
        await _call("POST", f"/subscriptions/{subscription.external_subscription_id}/cancel", {"cancel_at_cycle_end": 0})
        subscription.billing_provider = "manual"
        subscription.external_subscription_id = None
        subscription.provider_event_at = None
        subscription.cancel_at_period_end = False
    else:
        await _call("POST", f"/subscriptions/{subscription.external_subscription_id}/cancel", {"cancel_at_cycle_end": 1})
        subscription.cancel_at_period_end = True
    await session.commit()
    return subscription


async def _downgrade(session: AsyncSession, subscription: BrandSubscription) -> None:
    """The paid subscription ended: the brand is paused on its plan until it pays again."""
    now = datetime.now(timezone.utc)
    subscription.status = SubscriptionStatus.CANCELLED.value
    subscription.billing_provider = "manual"
    subscription.external_subscription_id = None
    subscription.provider_event_at = None
    subscription.cancel_at_period_end = False
    subscription.past_due_since = None
    if subscription.current_period_end > now:
        # Ended early (e.g. cancelled by Razorpay): pause from now.
        subscription.current_period_end = max(now, subscription.current_period_start + timedelta(seconds=1))


def webhook_signature_ok(raw_body: bytes, signature: str | None) -> bool:
    settings = get_settings()
    secret = settings.razorpay_billing_webhook_secret or settings.razorpay_webhook_secret
    if not secret:
        raise ServiceUnavailableError("Billing webhooks are not configured")
    if not signature:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


# Razorpay's own state of the subscription, as carried in the event payload.
_TERMINAL_REMOTE_STATES = frozenset({"cancelled", "completed", "expired"})
_ACTIVATING = ("subscription.activated", "subscription.charged", "subscription.resumed")
_PAST_DUE = ("subscription.pending", "subscription.halted")
_ENDING = ("subscription.cancelled", "subscription.completed")


async def handle_webhook(
    session: AsyncSession, raw_body: bytes, signature: str | None, event_id: str | None = None
) -> str:
    """Apply one signed subscription event; returns applied/ignored/rejected/duplicate.

    State policy (F13): an event is applied only if it is newer than the last
    event applied to that subscription (Razorpay's ``created_at``), belongs to
    the same brand, and — for activating events — Razorpay itself does not
    already report the subscription as ended. A cancelled subscription's id is
    cleared, so any later event for it is ignored. Each event id is recorded
    once, which makes retries no-ops; the outcome and reason are kept.
    """
    if not webhook_signature_ok(raw_body, signature):
        raise AuthenticationError("Invalid webhook signature", error_code=PaymentErrorCode.INVALID_SIGNATURE)
    try:
        event = json.loads(raw_body)
    except ValueError as exc:
        raise ValidationError("Webhook body is not JSON") from exc
    if not isinstance(event, dict):
        raise ValidationError("Webhook body is not a JSON object")
    name = str(event.get("event", ""))[:60]
    if not name.startswith("subscription."):
        return "ignored"
    entity = ((event.get("payload") or {}).get("subscription") or {}).get("entity") or {}
    external_id = str(entity["id"])[:200] if entity.get("id") else None
    created = event.get("created_at")
    event_at = datetime.fromtimestamp(int(created), timezone.utc) if isinstance(created, (int, float)) else None
    # Razorpay sends X-Razorpay-Event-Id; a retry repeats it. Without it, the
    # signed body itself identifies the delivery.
    provider_event_id = (event_id or "").strip()[:100] or "sha256:" + hashlib.sha256(raw_body).hexdigest()

    recorded = await session.execute(
        insert(BillingWebhookEvent)
        .values(
            id=uuid.uuid4(), provider_event_id=provider_event_id, event=name,
            external_subscription_id=external_id, event_created_at=event_at, outcome="pending",
        )
        .on_conflict_do_nothing(constraint="uq_billing_webhook_events_provider_event_id")
        .returning(BillingWebhookEvent.id)
    )  # fmt: skip
    row_id = recorded.scalar_one_or_none()
    if row_id is None:
        await session.rollback()
        logger.info("billing webhook duplicate", extra={"event": name, "provider_event_id": provider_event_id})
        return "duplicate"

    async def finish(outcome: str, reason: str | None = None, tenant_id: uuid.UUID | None = None) -> str:
        await session.execute(
            update(BillingWebhookEvent)
            .where(BillingWebhookEvent.id == row_id)
            .values(outcome=outcome, reason=reason, tenant_id=tenant_id)
        )
        await session.commit()
        if outcome == "rejected":
            logger.warning(
                "billing webhook rejected",
                extra={"event": name, "reason": reason, "subscription": external_id, "tenant_id": str(tenant_id)},
            )
        return outcome

    if not external_id:
        return await finish("ignored", "no subscription id")
    subscription = await session.scalar(
        select(BrandSubscription).where(BrandSubscription.external_subscription_id == external_id).with_for_update()
    )
    if subscription is None:
        # Never confirmed, replaced by a plan switch, or already cancelled.
        return await finish("ignored", "unknown, replaced or ended subscription")
    tenant_id = subscription.tenant_id

    noted_tenant = (entity.get("notes") or {}).get("tenant_id") if isinstance(entity.get("notes"), dict) else None
    if noted_tenant is not None and str(noted_tenant) != str(tenant_id):
        return await finish("rejected", "subscription notes name another brand", tenant_id)
    if name not in _ACTIVATING + _PAST_DUE + _ENDING:
        return await finish("ignored", "event not handled", tenant_id)
    if event_at is not None and subscription.provider_event_at is not None and event_at < subscription.provider_event_at:
        return await finish("rejected", "stale: older than the last applied event", tenant_id)
    remote_status = str(entity.get("status") or "").lower()
    if name in _ACTIVATING and remote_status in _TERMINAL_REMOTE_STATES:
        return await finish("rejected", f"activation for a subscription Razorpay reports as {remote_status}", tenant_id)

    plan = await session.get(SubscriptionPlan, subscription.plan_id)

    def ts(key: str) -> datetime | None:
        value = entity.get(key)
        return datetime.fromtimestamp(int(value), timezone.utc) if value else None

    if name in _ACTIVATING:
        subscription.status = SubscriptionStatus.ACTIVE.value
        subscription.past_due_since = None
        start, end = ts("current_start"), ts("current_end")
        if start and end and end > start:
            subscription.current_period_start, subscription.current_period_end = start, end
        await session.flush()
        if plan is not None:
            # Unique per plan and period: a retried charge grants nothing twice.
            await grant_allowance(session, subscription.tenant_id, plan, subscription.current_period_start)
    elif name in _PAST_DUE:
        if subscription.status != SubscriptionStatus.PAST_DUE.value:
            subscription.status = SubscriptionStatus.PAST_DUE.value
            subscription.past_due_since = datetime.now(timezone.utc)
    else:
        await _downgrade(session, subscription)
    if event_at is not None:
        subscription.provider_event_at = event_at
    return await finish("applied", None, tenant_id)


async def overview(session: AsyncSession, tenant_id: uuid.UUID) -> dict[str, Any]:
    service = SubscriptionService(session, tenant_id)
    current = await service.current()
    effective = await service.effective_plan()
    plans = (
        await session.scalars(
            select(SubscriptionPlan).where(SubscriptionPlan.is_active.is_(True)).order_by(SubscriptionPlan.sort_order)
        )
    ).all()
    await session.commit()
    subscription, plan = current if current else (None, None)
    return {
        "subscription": subscription,
        "plan": plan,
        "effective_plan": effective,
        "usage": await service.usage(),
        "plans": list(plans),
        "online_billing": razorpay.env_credentials() is not None,
    }
