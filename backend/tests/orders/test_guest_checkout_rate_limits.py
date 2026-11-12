"""F14: guest checkout limits per shopper, with a looser per-IP ceiling."""

from __future__ import annotations

import uuid

import pytest

from app.core import rate_limit
from app.core.config import get_settings
from app.core.exceptions import RateLimitedError
from tests.orders.test_guest_checkout import _checkout, _guest_cart

NAT_IP = "100.64.0.10"  # carrier-grade NAT range


@pytest.fixture
def limits(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "guest_checkout_rate_limit_attempts", 3)
    monkeypatch.setattr(settings, "guest_checkout_ip_rate_limit_attempts", 8)
    return settings


async def _attempts(tenant: str, ip: str, subject: str, n: int) -> int:
    """How many of n attempts get through."""
    passed = 0
    for _ in range(n):
        try:
            await rate_limit.enforce_guest_checkout(tenant, ip, subject)
            passed += 1
        except RateLimitedError:
            pass
    return passed


async def test_many_shoppers_behind_one_ip_are_not_blocked_by_each_other(limits):
    brand = str(uuid.uuid4())
    # Four shoppers, two attempts each = 8, all under the per-IP ceiling.
    results = [await _attempts(brand, NAT_IP, f"cart:{i}", 2) for i in range(4)]
    assert results == [2, 2, 2, 2]


async def test_one_shopper_is_still_limited(limits):
    assert await _attempts(str(uuid.uuid4()), NAT_IP, "cart:hammer", 5) == 3


async def test_minting_carts_from_one_ip_hits_the_ip_ceiling(limits):
    brand = str(uuid.uuid4())
    passed = sum([await _attempts(brand, NAT_IP, f"cart:mint-{i}", 1) for i in range(12)])
    assert passed == 8


async def test_other_ips_and_other_brands_have_their_own_counters(limits):
    brand, other_brand = str(uuid.uuid4()), str(uuid.uuid4())
    await _attempts(brand, NAT_IP, "cart:x", 5)  # exhaust this shopper

    assert await _attempts(brand, "203.0.113.7", "cart:x", 1) == 1
    assert await _attempts(other_brand, NAT_IP, "cart:x", 1) == 1


async def test_two_guests_on_one_ip_can_both_check_out_over_http(client, variant, limits):
    """Through the API: the per-shopper limit is keyed on the guest cart."""
    first = await _guest_cart(client, variant["id"], 1)
    for _ in range(3):
        await _checkout(client, first)  # one order, then retries on the spent cart
    blocked = await _checkout(client, first)
    second = await _checkout(client, await _guest_cart(client, variant["id"], 1))

    assert blocked.status_code == 429
    assert second.status_code == 201, second.text


async def test_a_spoofed_forwarded_for_header_does_not_reset_the_limit(client, variant, limits):
    """The app reads the peer address only (uvicorn decides which proxy to trust)."""
    headers = await _guest_cart(client, variant["id"], 1)
    for i in range(3):
        await _checkout(client, {**headers, "X-Forwarded-For": f"198.51.100.{i}"})

    spoofed = await _checkout(client, {**headers, "X-Forwarded-For": "198.51.100.99"})
    assert spoofed.status_code == 429
