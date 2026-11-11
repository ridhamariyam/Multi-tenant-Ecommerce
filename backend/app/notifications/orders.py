"""Customer emails about orders: a confirmation once an order is a sale, and
review requests. Queued from the scheduler, never from checkout itself."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import and_, exists, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.integrations.order_sheets import is_sale
from app.notifications import email
from app.notifications.models import OutboxEmail
from app.orders.constants import PaymentMethod
from app.orders.models import Order
from app.ratings.service import ReviewRequestMessage
from app.stores.models import Store
from app.stores.service import store_url
from app.tenants.models import Tenant
from app.users.models import User

# Orders older than this never get a confirmation (e.g. on the first deploy).
CONFIRMATION_WINDOW = timedelta(days=3)


def _money(amount: Decimal | None, currency: str) -> str:
    value = amount or Decimal("0")
    symbol = "₹" if currency == "INR" else f"{currency} "
    return f"{symbol}{value:,.2f}"


def confirmation(order: Order, tenant: Tenant, store: Store | None, currency: str) -> tuple[str, str, str]:
    """(subject, text, html) for one order."""
    brand = (store.name if store else None) or tenant.name
    lines = [
        f"{item.quantity} × {item.product_name}" + (f" ({item.variant_name})" if item.variant_name else "")
        for item in order.items
    ]
    cod = order.payment_method == PaymentMethod.CASH_ON_DELIVERY.value
    total = _money(order.total_amount, currency)
    payment = f"Pay {total} on delivery." if cod else f"Paid {total} online."
    track = f"{store_url(store)}/track-order?order={order.order_number}" if store else None
    paragraphs = [
        f"Hi {order.delivery_name}, thank you for shopping with {brand}.",
        f"Your order {order.order_number} is confirmed.",
        *lines,
        payment,
        f"Delivering to: {order.delivery_address_line_1}, {order.delivery_city}, "
        f"{order.delivery_state} {order.delivery_postal_code}.",
        "Track it any time with your order number and phone number.",
    ]
    subject = f"{brand}: order {order.order_number} confirmed"
    text = "\n\n".join(paragraphs + ([track] if track else []))
    html_body = email.simple_html(f"Order {order.order_number} confirmed", paragraphs, ("Track your order", track) if track else None)
    return subject, text, html_body


async def queue_order_confirmations(session: AsyncSession, *, limit: int = 200) -> int:
    since = datetime.now(timezone.utc) - CONFIRMATION_WINDOW
    key = literal("order-confirmation:") + func.cast(Order.id, OutboxEmail.dedupe_key.type)
    recipient = func.coalesce(Order.contact_email, User.email)
    rows = (
        await session.execute(
            select(Order, recipient)
            .join(User, and_(User.id == Order.customer_id), isouter=True)
            .where(
                is_sale(),
                Order.created_at >= since,
                recipient.is_not(None),
                ~exists().where(OutboxEmail.dedupe_key == key),
            )
            .options(selectinload(Order.items))
            .order_by(Order.created_at)
            .limit(limit)
        )
    ).all()
    queued = 0
    for order, to in rows:
        tenant = await session.get(Tenant, order.tenant_id)
        store = await session.scalar(select(Store).where(Store.tenant_id == order.tenant_id))
        if tenant is None:
            continue
        subject, text, html_body = confirmation(order, tenant, store, tenant.currency)
        if await email.enqueue(
            session,
            kind="order-confirmation",
            dedupe_key=f"order-confirmation:{order.id}",
            to=to,
            subject=subject,
            text=text,
            html_body=html_body,
            tenant_id=order.tenant_id,
            from_name=(store.name if store else None) or tenant.name,
            reply_to=tenant.contact_email,
        ):
            queued += 1
    await session.commit()
    return queued


class EmailReviewNotifier:
    """Review requests by email (when the order has an address)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def send(self, message: ReviewRequestMessage) -> None:
        if not message.email:
            return
        from uuid import UUID

        tenant = await self.session.get(Tenant, UUID(message.tenant_id))
        store = await self.session.scalar(select(Store).where(Store.tenant_id == UUID(message.tenant_id)))
        brand = (store.name if store else None) or (tenant.name if tenant else "our store")
        link = f"{store_url(store)}/account/reviews" if store else None
        paragraphs = [
            f"Hi {message.customer_name or 'there'}, how are you finding your order {message.order_number}?",
            "A short review helps other shoppers: " + ", ".join(message.products) + ".",
        ]
        await email.enqueue(
            self.session,
            kind="review-request",
            dedupe_key=f"review-request:{message.tenant_id}:{message.order_number}",
            to=message.email,
            subject=f"{brand}: how was your order?",
            text="\n\n".join(paragraphs + ([link] if link else [])),
            html_body=email.simple_html("How was your order?", paragraphs, ("Write a review", link) if link else None),
            tenant_id=UUID(message.tenant_id),
            from_name=brand,
            reply_to=tenant.contact_email if tenant else None,
        )
