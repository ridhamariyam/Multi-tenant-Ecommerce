"""Return reasons: the store's list, capture on RETURNED, and the returns report."""

from __future__ import annotations

from datetime import date

from tests.orders.conftest import ADMIN_ORDERS

REASONS = "/api/v1/admin/return-reasons"
TODAY = date.today().isoformat()


async def _reason(client, headers, label, **extra):
    response = await client.post(REASONS, json={"label": label, **extra}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _ship(set_status, order_id):
    for status in ("CONFIRMED", "PACKED", "SHIPPED"):
        await set_status(order_id, status)


async def test_reasons_are_listed_in_order(client, admin_headers):
    await _reason(client, admin_headers, "Refused at door")
    await _reason(client, admin_headers, "Address not found")
    off = await _reason(client, admin_headers, "Old reason", is_active=False)

    everything = (await client.get(REASONS, headers=admin_headers)).json()["data"]
    active = (await client.get(REASONS, params={"active_only": True}, headers=admin_headers)).json()["data"]

    assert [r["label"] for r in everything] == ["Refused at door", "Address not found", "Old reason"]
    assert off["id"] not in [r["id"] for r in active]


async def test_duplicate_labels_are_refused(client, admin_headers):
    await _reason(client, admin_headers, "Refused at door")

    response = await client.post(REASONS, json={"label": "refused at door"}, headers=admin_headers)

    assert response.status_code == 409


async def test_a_returned_order_keeps_its_reason_and_note(client, admin_headers, order, set_status):
    reason = await _reason(client, admin_headers, "Refused at door")
    await _ship(set_status, order["id"])

    returned = await set_status(order["id"], "RETURNED", return_reason_id=reason["id"], return_note="Customer not home twice")
    await client.patch(f"{REASONS}/{reason['id']}", json={"label": "Refused delivery"}, headers=admin_headers)
    later = (await client.get(f"{ADMIN_ORDERS}/{order['id']}", headers=admin_headers)).json()["data"]

    assert returned["data"]["return_reason"] == "Refused at door"
    assert later["return_reason"] == "Refused at door"  # renaming does not rewrite history
    assert later["return_note"] == "Customer not home twice"


async def test_a_reason_only_goes_with_returned(client, admin_headers, order, set_status):
    reason = await _reason(client, admin_headers, "Refused at door")

    response = await set_status(order["id"], "CONFIRMED", expect=400, return_reason_id=reason["id"])

    assert "RETURNED" in response["message"]


async def test_a_switched_off_reason_cannot_be_used(client, admin_headers, order, set_status):
    reason = await _reason(client, admin_headers, "Old reason", is_active=False)
    await _ship(set_status, order["id"])

    await set_status(order["id"], "RETURNED", expect=409, return_reason_id=reason["id"])


async def test_returning_without_a_reason_still_works(client, admin_headers, order, set_status):
    await _ship(set_status, order["id"])

    returned = await set_status(order["id"], "RETURNED")

    assert returned["data"]["return_reason"] is None


async def test_the_returns_report_groups_by_reason(client, admin_headers, customer_auth, order_in, set_status):
    refused = await _reason(client, admin_headers, "Refused at door")
    orders = [await order_in(customer_auth) for _ in range(3)]
    for o in orders:
        await _ship(set_status, o["id"])
    await set_status(orders[0]["id"], "RETURNED", return_reason_id=refused["id"])
    await set_status(orders[1]["id"], "RETURNED", return_reason_id=refused["id"])
    await set_status(orders[2]["id"], "RETURNED")

    report = (await client.get("/api/v1/admin/reports/returns", params={"start_date": TODAY, "end_date": TODAY}, headers=admin_headers)).json()["data"]
    csv = await client.get(
        "/api/v1/admin/reports/returns",
        params={"start_date": TODAY, "end_date": TODAY, "format": "csv", "breakdown": "reason"},
        headers=admin_headers,
    )

    assert [(r["reason"], r["orders"]) for r in report["by_reason"]] == [("Refused at door", 2), ("Not recorded", 1)]
    assert csv.text.lstrip("﻿").splitlines()[0] == "reason,orders,returned_value"


async def test_reason_management_needs_permissions(client, staff_headers):
    assert (await client.get(REASONS, headers=staff_headers)).status_code == 200
    assert (await client.post(REASONS, json={"label": "X"}, headers=staff_headers)).status_code == 403


async def test_another_stores_reason_cannot_be_used(client, other_client, admin_headers, other_admin_headers, order, set_status):
    theirs = (await other_client.post(REASONS, json={"label": "Theirs"}, headers=other_admin_headers)).json()["data"]
    await _ship(set_status, order["id"])

    listed = (await client.get(REASONS, headers=admin_headers)).json()["data"]
    response = await set_status(order["id"], "RETURNED", expect=404, return_reason_id=theirs["id"])

    assert listed == []
    assert response["error"]["code"] == "NOT_FOUND"
