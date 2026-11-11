"""Order confirmation emails and the outbox that delivers them."""

from __future__ import annotations

import smtplib
from uuid import UUID

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.notifications import email
from app.notifications.models import EmailStatus, OutboxEmail
from app.notifications.orders import queue_order_confirmations
from app.orders.models import Order
from tests.orders.test_order_sheets import _guest_order


@pytest.fixture
def smtp(monkeypatch):
    sent: list = []
    monkeypatch.setattr(get_settings(), "smtp_host", "smtp.example.test")
    monkeypatch.setattr(email, "send_message", lambda message: sent.append(message))
    return sent


async def test_a_cod_order_gets_one_confirmation(client, session, variant, smtp):
    placed = await _guest_order(client, variant["id"], 2)

    assert await queue_order_confirmations(session) == 1
    assert await queue_order_confirmations(session) == 0  # never twice
    result = await email.send_due(session)

    assert result == {"sent": 1, "failed": 0}
    (message,) = smtp
    assert message["To"] == "asha@example.com"
    assert placed["order_number"] in message["Subject"]
    body = message.get_body(("plain",)).get_content()
    assert "Pay ₹" in body and "on delivery" in body
    row = await session.scalar(select(OutboxEmail))
    assert row.status == EmailStatus.SENT and row.tenant_id is not None


async def test_an_unpaid_online_order_waits_for_payment(client, session, variant, smtp):
    placed = await _guest_order(client, variant["id"])
    order = await session.get(Order, UUID(placed["id"]))
    order.payment_method, order.payment_status = "UPI", "PENDING"
    await session.commit()

    assert await queue_order_confirmations(session) == 0
    order.payment_status = "PAID"
    await session.commit()
    assert await queue_order_confirmations(session) == 1


async def test_failures_retry_with_backoff_then_give_up(session, monkeypatch, smtp):
    def broken(_message):
        raise smtplib.SMTPServerDisconnected("connection closed")

    monkeypatch.setattr(email, "send_message", broken)
    monkeypatch.setattr(get_settings(), "email_max_attempts", 2)
    await email.enqueue(session, kind="test", dedupe_key="t-1", to="a@example.com", subject="s", text="t")
    await session.commit()

    first = await email.send_due(session)
    row = await session.scalar(select(OutboxEmail))
    assert first == {"sent": 0, "failed": 1}
    assert row.status == EmailStatus.PENDING and row.attempts == 1 and "SMTPServerDisconnected" in row.last_error

    # Not due yet: backoff.
    assert (await email.send_due(session))["failed"] == 0
    row.send_after = row.created_at
    await session.commit()
    await email.send_due(session)
    await session.refresh(row)
    assert row.status == EmailStatus.FAILED and row.attempts == 2


async def test_without_smtp_emails_wait_in_the_outbox(session, monkeypatch):
    monkeypatch.setattr(get_settings(), "smtp_host", None)
    await email.enqueue(session, kind="test", dedupe_key="t-2", to="a@example.com", subject="s", text="t")
    await session.commit()

    assert (await email.send_due(session))["sent"] == 0
    assert (await session.scalar(select(OutboxEmail))).status == EmailStatus.PENDING


def test_html_bodies_escape_customer_text():
    html = email.simple_html("Hi", ["<script>alert(1)</script>"], ("Go", 'https://x.test/"onmouseover'))
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert '"onmouseover' not in html
