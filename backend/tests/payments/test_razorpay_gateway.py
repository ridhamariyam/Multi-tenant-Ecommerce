"""The Razorpay client and signature checks, against a mocked API rather than the network."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from decimal import Decimal

import httpx
import pytest

from app.core.exceptions import ServiceUnavailableError
from app.payments import razorpay

KEY_ID = "rzp_test_key"
KEY_SECRET = "test-key-secret"
WEBHOOK_SECRET = "test-webhook-secret"


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    settings = razorpay.get_settings()
    monkeypatch.setattr(settings, "razorpay_key_id", KEY_ID)
    monkeypatch.setattr(settings, "razorpay_key_secret", KEY_SECRET)
    monkeypatch.setattr(settings, "razorpay_webhook_secret", WEBHOOK_SECRET)


@pytest.fixture
def razorpay_replies(monkeypatch):
    """Answer the Orders API with a canned response and record what was sent."""
    sent: list[httpx.Request] = []

    def install(handler):
        real_init = httpx.AsyncClient.__init__

        def init(self, *args, **kwargs):
            def record(request: httpx.Request) -> httpx.Response:
                sent.append(request)
                return handler(request)

            kwargs["transport"] = httpx.MockTransport(record)
            real_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", init)
        return sent

    return install


def _hex(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def test_amounts_go_out_in_paise():
    assert razorpay.to_subunits(Decimal("1998.50")) == 199850
    assert razorpay.to_subunits(Decimal("0.01")) == 1


def test_a_checkout_signature_is_order_pipe_payment_under_the_key_secret():
    signature = _hex(KEY_SECRET, b"order_1|pay_1")

    assert razorpay.signature_is_valid("order_1", "pay_1", signature)
    assert not razorpay.signature_is_valid("order_1", "pay_2", signature)
    assert not razorpay.signature_is_valid("order_1", "pay_1", _hex("other", b"order_1|pay_1"))


def test_no_key_secret_means_signatures_cannot_be_checked(monkeypatch):
    monkeypatch.setattr(razorpay.get_settings(), "razorpay_key_secret", None)

    with pytest.raises(ServiceUnavailableError):
        razorpay.signature_is_valid("order_1", "pay_1", _hex("", b"order_1|pay_1"))


def test_a_webhook_signature_covers_the_raw_body():
    body = b'{"event":"payment.captured"}'

    assert razorpay.webhook_signature_valid(body, _hex(WEBHOOK_SECRET, body))
    assert not razorpay.webhook_signature_valid(body + b" ", _hex(WEBHOOK_SECRET, body))


async def test_creating_an_order_sends_paise_and_basic_auth(razorpay_replies):
    sent = razorpay_replies(
        lambda _r: httpx.Response(
            200, json={"id": "order_ABC", "amount": 199800, "currency": "INR"}
        )
    )

    order_id = await razorpay.create_order(Decimal("1998.00"), "INR", "ORD-100001")

    assert order_id == "order_ABC"
    request = sent[0]
    assert request.url.path.endswith("/orders")
    assert json.loads(request.content) == {
        "amount": 199800,
        "currency": "INR",
        "receipt": "ORD-100001",
    }
    expected = base64.b64encode(f"{KEY_ID}:{KEY_SECRET}".encode()).decode()
    assert request.headers["Authorization"] == f"Basic {expected}"


@pytest.mark.parametrize("status_code", [400, 401, 500])
async def test_a_rejected_order_is_reported_as_unavailable(razorpay_replies, status_code):
    razorpay_replies(lambda _r: httpx.Response(status_code, json={"error": {}}))

    with pytest.raises(ServiceUnavailableError):
        await razorpay.create_order(Decimal("10.00"), "INR", "ORD-1")


async def test_a_transport_failure_is_reported_as_unavailable(razorpay_replies):
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable", request=request)

    razorpay_replies(fail)

    with pytest.raises(ServiceUnavailableError):
        await razorpay.create_order(Decimal("10.00"), "INR", "ORD-1")


async def test_no_keys_means_no_call(razorpay_replies, monkeypatch):
    sent = razorpay_replies(lambda _r: httpx.Response(200, json={"id": "order_ABC"}))
    monkeypatch.setattr(razorpay.get_settings(), "razorpay_key_secret", None)

    with pytest.raises(ServiceUnavailableError):
        await razorpay.create_order(Decimal("10.00"), "INR", "ORD-1")
    assert sent == []
