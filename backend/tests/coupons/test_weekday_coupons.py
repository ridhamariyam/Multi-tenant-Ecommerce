"""Coupons that only work on chosen days of the week (shop's local time)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.coupons.service import valid_today

ADMIN_COUPONS = "/api/v1/admin/coupons"
IST = timedelta(hours=5, minutes=30)


def _today_ist() -> int:
    return (datetime.now(timezone.utc) + IST).weekday()


def test_the_weekday_is_judged_in_shop_time_not_utc():
    coupon = SimpleNamespace(valid_weekdays=[4])  # Friday
    # Thursday 20:00 UTC is already Friday 01:30 in India.
    thursday_evening_utc = datetime(2026, 10, 1, 20, 0, tzinfo=timezone.utc)

    assert thursday_evening_utc.weekday() == 3
    assert valid_today(coupon, thursday_evening_utc) is True
    assert valid_today(SimpleNamespace(valid_weekdays=None), thursday_evening_utc) is True
    assert valid_today(SimpleNamespace(valid_weekdays=[3]), thursday_evening_utc) is False


async def _coupon(client, headers, code, weekdays, **extra):
    response = await client.post(
        ADMIN_COUPONS,
        json={"code": code, "discount_type": "FIXED_AMOUNT", "discount_value": "10", "valid_weekdays": weekdays, **extra},
        headers=headers,
    )
    assert response.status_code == 200, response.text  # this endpoint answers 200 on create
    return response.json()["data"]


async def test_weekdays_are_saved_sorted_and_deduplicated(client, admin_headers):
    coupon = await _coupon(client, admin_headers, "MWF", [4, 0, 2, 0])

    assert coupon["valid_weekdays"] == [0, 2, 4]


async def test_an_empty_selection_means_every_day(client, admin_headers):
    coupon = await _coupon(client, admin_headers, "ANYDAY", [])

    assert coupon["valid_weekdays"] == []


async def test_invalid_weekdays_are_rejected(client, admin_headers):
    response = await client.post(
        ADMIN_COUPONS,
        json={"code": "BAD", "discount_type": "FIXED_AMOUNT", "discount_value": "10", "valid_weekdays": [7]},
        headers=admin_headers,
    )

    assert response.status_code == 422


async def test_weekdays_can_be_changed_and_cleared(client, admin_headers):
    coupon = await _coupon(client, admin_headers, "CHANGE", [1])

    changed = await client.put(f"{ADMIN_COUPONS}/{coupon['id']}", json={"valid_weekdays": [5, 6]}, headers=admin_headers)
    cleared = await client.put(f"{ADMIN_COUPONS}/{coupon['id']}", json={"valid_weekdays": []}, headers=admin_headers)

    assert changed.json()["data"]["valid_weekdays"] == [5, 6]
    assert cleared.json()["data"]["valid_weekdays"] == []


async def _apply(client, headers, code):
    return await client.post("/api/v1/coupons/apply", json={"code": code}, headers=headers)


async def test_a_coupon_works_on_its_days(client, admin_headers, customer_headers, cart_worth):
    await cart_worth(customer_headers, "300.00")
    await _coupon(client, admin_headers, "TODAYONLY", [_today_ist()])

    response = await _apply(client, customer_headers, "TODAYONLY")

    assert response.status_code == 200, response.text


async def test_a_coupon_is_refused_on_other_days(client, admin_headers, customer_headers, cart_worth):
    await cart_worth(customer_headers, "300.00")
    other_days = [d for d in range(7) if d != _today_ist()]
    await _coupon(client, admin_headers, "NOTTODAY", other_days)

    response = await _apply(client, customer_headers, "NOTTODAY")

    assert response.status_code == 400
    assert response.json()["message"].startswith("This coupon is only valid on")


async def test_automatic_offers_respect_the_days(client, admin_headers):
    other_days = [d for d in range(7) if d != _today_ist()]
    await _coupon(client, admin_headers, "AUTOTODAY", [_today_ist()], is_automatic=True)
    await _coupon(client, admin_headers, "AUTOOTHER", other_days, is_automatic=True)

    offers = (await client.get("/api/v1/coupons/offers")).json()["data"]

    codes = [o["code"] for o in offers]
    assert "AUTOTODAY" in codes
    assert "AUTOOTHER" not in codes
