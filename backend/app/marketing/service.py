"""Marketing consent, segments, campaigns and abandoned-cart reminders.

Only customers who opted in (users.marketing_opt_in) ever get marketing email
(campaigns and cart reminders). Every such email carries a one-click
unsubscribe link signed with the platform secret.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from sqlalchemy import and_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cart.models import Cart, CartItem
from app.core.config import get_settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.marketing.models import CampaignStatus, EmailCampaign
from app.notifications import email
from app.orders.models import Order
from app.stores.models import Store
from app.stores.service import store_url
from app.tenants.models import Tenant
from app.auth.constants import UserRole, UserStatus
from app.users.models import User

SEGMENT_KINDS = ("ALL", "ORDERED_WITHIN", "NO_ORDERS", "TAG")
CART_REMINDER_AFTER = timedelta(hours=1)
CART_REMINDER_UNTIL = timedelta(hours=48)


# ------------------------------------------------------------ unsubscribe


def unsubscribe_token(tenant_id: uuid.UUID, user_id: uuid.UUID) -> str:
    secret = get_settings().jwt_secret.encode()
    return hmac.new(secret, f"unsubscribe:{tenant_id}:{user_id}".encode(), hashlib.sha256).hexdigest()[:32]


def unsubscribe_url(store: Store | None, tenant_id: uuid.UUID, user_id: uuid.UUID) -> str | None:
    if store is None:
        return None
    query = urlencode({"u": str(user_id), "t": unsubscribe_token(tenant_id, user_id)})
    return f"{store_url(store)}/unsubscribe?{query}"


async def unsubscribe(session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID, token: str) -> None:
    if not hmac.compare_digest(unsubscribe_token(tenant_id, user_id), token):
        raise ValidationError("This unsubscribe link is not valid.")
    user = await session.scalar(select(User).where(User.tenant_id == tenant_id, User.id == user_id))
    if user is not None and user.marketing_opt_in:
        user.marketing_opt_in = False
        user.marketing_opt_in_at = None
        await session.commit()


async def set_consent(session: AsyncSession, user: User, opt_in: bool, email_address: str | None = None) -> None:
    """Record a customer's choice. Caller commits."""
    if opt_in and not user.marketing_opt_in:
        user.marketing_opt_in_at = datetime.now(timezone.utc)
    user.marketing_opt_in = opt_in
    if opt_in and email_address and not user.email:
        user.marketing_email = email_address.strip().lower()


# ---------------------------------------------------------------- segments


def recipient_email():
    return func.coalesce(User.marketing_email, User.email)


def _segment_filter(tenant_id: uuid.UUID, segment: dict):
    kind = segment.get("kind", "ALL")
    if kind not in SEGMENT_KINDS:
        raise ValidationError("Unknown segment", details=[{"field": "segment", "message": "Unknown segment"}])
    base = [
        User.tenant_id == tenant_id,
        User.role == UserRole.CUSTOMER.value,
        User.status == UserStatus.ACTIVE.value,
        User.marketing_opt_in.is_(True),
        recipient_email().is_not(None),
    ]
    ordered = select(Order.id).where(Order.tenant_id == tenant_id, Order.customer_id == User.id)
    if kind == "ORDERED_WITHIN":
        days = int(segment.get("days") or 90)
        base.append(exists(ordered.where(Order.created_at >= datetime.now(timezone.utc) - timedelta(days=days))))
    elif kind == "NO_ORDERS":
        base.append(~exists(ordered))
    elif kind == "TAG":
        tag = str(segment.get("tag") or "").strip()
        if not tag:
            raise ValidationError("Choose a tag", details=[{"field": "segment", "message": "Choose a tag"}])
        base.append(User.tags.contains([tag]))
    return and_(*base)


async def segment_size(session: AsyncSession, tenant_id: uuid.UUID, segment: dict) -> int:
    return int(await session.scalar(select(func.count(User.id)).where(_segment_filter(tenant_id, segment))) or 0)


async def consent_counts(session: AsyncSession, tenant_id: uuid.UUID) -> dict[str, int]:
    customers = await session.scalar(
        select(func.count(User.id)).where(User.tenant_id == tenant_id, User.role == UserRole.CUSTOMER.value)
    )
    subscribed = await segment_size(session, tenant_id, {"kind": "ALL"})
    return {"customers": int(customers or 0), "subscribed": subscribed}


# --------------------------------------------------------------- campaigns


async def _brand(session: AsyncSession, tenant_id: uuid.UUID) -> tuple[Tenant, Store | None, str]:
    tenant = await session.get(Tenant, tenant_id)
    store = await session.scalar(select(Store).where(Store.tenant_id == tenant_id))
    return tenant, store, (store.name if store else None) or tenant.name


def _with_footer(paragraphs: list[str], brand: str, unsubscribe: str | None) -> tuple[str, str]:
    footer = f"You get this because you agreed to emails from {brand}."
    text = "\n\n".join(paragraphs + [footer] + ([f"Unsubscribe: {unsubscribe}"] if unsubscribe else []))
    html_body = email.simple_html(paragraphs[0] if paragraphs else brand, paragraphs[1:] + [footer], ("Unsubscribe", unsubscribe) if unsubscribe else None)
    return text, html_body


async def send_campaign(session: AsyncSession, tenant_id: uuid.UUID, campaign_id: uuid.UUID) -> EmailCampaign:
    campaign = await session.scalar(
        select(EmailCampaign).where(EmailCampaign.tenant_id == tenant_id, EmailCampaign.id == campaign_id).with_for_update()
    )
    if campaign is None:
        raise NotFoundError("Campaign not found")
    if campaign.status != CampaignStatus.DRAFT:
        raise ConflictError("This campaign was already sent")
    tenant, store, brand = await _brand(session, tenant_id)
    rows = (
        await session.execute(select(User.id, User.name, recipient_email()).where(_segment_filter(tenant_id, campaign.segment)))
    ).all()
    paragraphs = [p.strip() for p in campaign.body.split("\n\n") if p.strip()]
    for user_id, name, to in rows:
        greeting = f"Hi {name}," if name else "Hi,"
        text, html_body = _with_footer([campaign.subject, greeting, *paragraphs], brand, unsubscribe_url(store, tenant_id, user_id))
        await email.enqueue(
            session,
            kind="campaign",
            dedupe_key=f"campaign:{campaign.id}:{user_id}",
            to=to,
            subject=campaign.subject,
            text=text,
            html_body=html_body,
            tenant_id=tenant_id,
            from_name=brand,
            reply_to=tenant.contact_email,
        )
    campaign.status = CampaignStatus.SENT
    campaign.recipients = len(rows)
    campaign.sent_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(campaign)
    return campaign


# ---------------------------------------------------------- abandoned carts


async def queue_cart_reminders(session: AsyncSession, *, limit: int = 200) -> int:
    """One reminder per abandoned cart, to signed-in customers who opted in."""
    from app.cart.models import CartStatus

    now = datetime.now(timezone.utc)
    has_items = exists().where(CartItem.cart_id == Cart.id)
    ordered_since = exists().where(
        Order.tenant_id == Cart.tenant_id, Order.customer_id == Cart.customer_id, Order.created_at >= Cart.last_activity_at
    )
    rows = (
        await session.execute(
            select(Cart, User.name, recipient_email())
            .join(User, and_(User.id == Cart.customer_id, User.tenant_id == Cart.tenant_id))
            .where(
                Cart.status == CartStatus.ACTIVE.value,
                Cart.customer_id.is_not(None),
                Cart.reminder_sent_at.is_(None),
                Cart.last_activity_at <= now - CART_REMINDER_AFTER,
                Cart.last_activity_at >= now - CART_REMINDER_UNTIL,
                User.marketing_opt_in.is_(True),
                recipient_email().is_not(None),
                has_items,
                ~ordered_since,
            )
            .limit(limit)
        )
    ).all()
    queued = 0
    for cart, name, to in rows:
        tenant, store, brand = await _brand(session, cart.tenant_id)
        link = f"{store_url(store)}/cart" if store else None
        paragraphs = [
            "You left something in your bag",
            f"Hi {name or 'there'}, the pieces you picked at {brand} are still waiting for you.",
            "Stock moves fast, so finish your order while your size is available.",
        ]
        text, html_body = _with_footer(paragraphs + ([f"Your bag: {link}"] if link else []), brand, unsubscribe_url(store, cart.tenant_id, cart.customer_id))
        if await email.enqueue(
            session, kind="cart-reminder", dedupe_key=f"cart-reminder:{cart.id}", to=to,
            subject=f"{brand}: your bag is waiting", text=text, html_body=html_body,
            tenant_id=cart.tenant_id, from_name=brand, reply_to=tenant.contact_email,
        ):  # fmt: skip
            queued += 1
        cart.reminder_sent_at = now
    await session.commit()
    return queued
