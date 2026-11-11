"""Server-side adapter for Razorpay order, payment and refund APIs."""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.error_codes import PaymentErrorCode
from app.core.exceptions import ServiceUnavailableError

UNAVAILABLE = "Online payment is not available right now"


@dataclass(frozen=True)
class Credentials:
    key_id: str
    key_secret: str
    api_url: str
    timeout_seconds: float


@dataclass(frozen=True)
class Scope:
    """The Razorpay account in use for the current brand (see app.payments.gateway)."""

    credentials: Credentials | None
    webhook_secret: str | None


# Set by gateway.scoped() around a brand's payment work. Outside any scope
# (scripts, older call sites) the platform keys from the environment apply.
_scope: ContextVar[Scope | None] = ContextVar("razorpay_scope", default=None)


@contextmanager
def use_scope(scope: Scope) -> Iterator[None]:
    token = _scope.set(scope)
    try:
        yield
    finally:
        _scope.reset(token)


def env_credentials() -> Credentials | None:
    settings = get_settings()
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        return None
    return Credentials(
        key_id=settings.razorpay_key_id,
        key_secret=settings.razorpay_key_secret,
        api_url=settings.razorpay_api_url.rstrip("/"),
        timeout_seconds=settings.razorpay_timeout_seconds,
    )


def is_configured() -> bool:
    """Whether the current brand (or, unscoped, the platform) can take online payments."""
    scope = _scope.get()
    if scope is not None:
        return scope.credentials is not None
    return env_credentials() is not None


def credentials() -> Credentials:
    scope = _scope.get()
    creds = scope.credentials if scope is not None else env_credentials()
    if creds is None:
        raise ServiceUnavailableError(UNAVAILABLE, error_code=PaymentErrorCode.GATEWAY_UNAVAILABLE)
    return creds


def to_subunits(amount: Decimal) -> int:
    subunits = amount * 100
    if subunits != subunits.to_integral_value():
        raise ValueError("Payment amount must have no more than two decimal places")
    return int(subunits)


async def create_order(amount: Decimal, currency: str, receipt: str) -> str:
    creds = credentials()
    expected_amount = to_subunits(amount)
    try:
        async with httpx.AsyncClient(timeout=creds.timeout_seconds) as client:
            response = await client.post(
                f"{creds.api_url}/orders",
                auth=(creds.key_id, creds.key_secret),
                json={
                    "amount": expected_amount,
                    "currency": currency,
                    "receipt": receipt[:40],
                },
            )
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ServiceUnavailableError(
            UNAVAILABLE,
            error_code=PaymentErrorCode.GATEWAY_UNAVAILABLE,
        ) from exc

    order_id = payload.get("id") if isinstance(payload, dict) else None
    if (
        response.status_code != httpx.codes.OK
        or not isinstance(order_id, str)
        or not order_id.startswith("order_")
        or payload.get("amount") != expected_amount
        or payload.get("currency") != currency
    ):
        raise ServiceUnavailableError(UNAVAILABLE, error_code=PaymentErrorCode.GATEWAY_UNAVAILABLE)
    return order_id


async def fetch_payment(payment_id: str) -> dict[str, Any]:
    if not payment_id.startswith("pay_"):
        raise ServiceUnavailableError(UNAVAILABLE, error_code=PaymentErrorCode.GATEWAY_UNAVAILABLE)
    return await _get(f"/payments/{payment_id}")


def signature_is_valid(order_id: str, payment_id: str, signature: str) -> bool:
    secret = credentials().key_secret.encode("utf-8")
    expected = hmac.new(
        secret,
        f"{order_id}|{payment_id}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def webhook_signature_valid(raw_body: bytes, signature: str) -> bool:
    """Check X-Razorpay-Signature: HMAC-SHA256 of the raw body with the webhook secret."""
    scope = _scope.get()
    secret = scope.webhook_secret if scope is not None else get_settings().razorpay_webhook_secret
    if not secret:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


async def _get(path: str) -> dict[str, Any]:
    creds = credentials()
    try:
        async with httpx.AsyncClient(timeout=creds.timeout_seconds) as client:
            response = await client.get(
                f"{creds.api_url}{path}", auth=(creds.key_id, creds.key_secret)
            )
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ServiceUnavailableError(
            UNAVAILABLE,
            error_code=PaymentErrorCode.GATEWAY_UNAVAILABLE,
        ) from exc

    if response.status_code != httpx.codes.OK or not isinstance(payload, dict):
        raise ServiceUnavailableError(UNAVAILABLE, error_code=PaymentErrorCode.GATEWAY_UNAVAILABLE)
    return payload


async def fetch_order_payment_statuses(order_id: str) -> list[str]:
    """The status of every payment attempted against a Razorpay order."""
    if not order_id.startswith("order_"):
        raise ServiceUnavailableError(UNAVAILABLE, error_code=PaymentErrorCode.GATEWAY_UNAVAILABLE)
    items = (await _get(f"/orders/{order_id}/payments")).get("items")
    if not isinstance(items, list):
        raise ServiceUnavailableError(UNAVAILABLE, error_code=PaymentErrorCode.GATEWAY_UNAVAILABLE)
    return [str(item.get("status", "")) for item in items if isinstance(item, dict)]


async def create_refund(*, payment_id: str, amount: Decimal, receipt: str) -> tuple[str, str]:
    """Ask Razorpay to refund a captured payment in full; returns the refund id and status."""
    creds = credentials()
    if not payment_id.startswith("pay_"):
        raise ServiceUnavailableError(UNAVAILABLE, error_code=PaymentErrorCode.GATEWAY_UNAVAILABLE)
    expected_amount = to_subunits(amount)
    try:
        async with httpx.AsyncClient(timeout=creds.timeout_seconds) as client:
            response = await client.post(
                f"{creds.api_url}/payments/{payment_id}/refund",
                auth=(creds.key_id, creds.key_secret),
                json={"amount": expected_amount, "receipt": receipt[:40]},
            )
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ServiceUnavailableError(
            UNAVAILABLE,
            error_code=PaymentErrorCode.GATEWAY_UNAVAILABLE,
        ) from exc

    refund_id = payload.get("id") if isinstance(payload, dict) else None
    if (
        response.status_code != httpx.codes.OK
        or not isinstance(refund_id, str)
        or not refund_id.startswith("rfnd_")
        or payload.get("amount") != expected_amount
    ):
        raise ServiceUnavailableError(UNAVAILABLE, error_code=PaymentErrorCode.GATEWAY_UNAVAILABLE)
    return refund_id, str(payload.get("status", ""))
