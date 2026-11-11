"""Turn payment rows into API payloads."""

from __future__ import annotations

from app.payments.models import Payment
from app.payments.schemas import PaymentRead


def payment_read(payment: Payment, currency: str) -> PaymentRead:
    """Render a payment; `currency` comes from the tenant, not from the payment."""
    return PaymentRead(
        id=payment.id,
        order_id=payment.order_id,
        amount=payment.amount,
        currency=currency,
        status=payment.status,
        provider=payment.provider,
        purpose=payment.purpose,
        gateway_order_id=payment.razorpay_order_id,
        gateway_payment_id=payment.razorpay_payment_id,
        remitted_at=payment.remitted_at,
        remittance_reference=payment.remittance_reference,
        created_at=payment.created_at,
    )
