"""Admin customer management: list, totals, detail, tags, notes, history."""

from __future__ import annotations

from decimal import Decimal

from tests.orders.conftest import address_payload

CUSTOMERS_API = "/api/v1/admin/customers"


async def test_customers_list_with_their_totals(client, admin_headers, customer, customer_auth, order_in):
    first = await order_in(customer_auth)
    second = await order_in(customer_auth)

    rows = (await client.get(CUSTOMERS_API, headers=admin_headers)).json()["data"]

    row = next(r for r in rows if r["id"] == str(customer.id))
    assert row["total_orders"] == 2
    assert Decimal(row["total_spent"]) == Decimal(first["total_amount"]) + Decimal(second["total_amount"])
    assert row["last_order_at"] is not None


async def test_cancelled_orders_do_not_count_as_spending(client, admin_headers, customer, customer_auth, order_in):
    order = await order_in(customer_auth)
    await client.post(f"/api/v1/orders/{order['id']}/cancel", headers=customer_auth)

    detail = (await client.get(f"{CUSTOMERS_API}/{customer.id}", headers=admin_headers)).json()["data"]

    assert detail["total_orders"] == 0
    assert detail["cancelled_orders"] == 1
    assert Decimal(detail["total_spent"]) == Decimal("0.00")


async def test_search_by_phone_or_name(client, admin_headers, make_user, tenant):
    await make_user(tenant=tenant, phone="+919777700001", name="Lakshmi Menon")
    await make_user(tenant=tenant, phone="+919777700002", name="Someone Else")

    by_name = (await client.get(CUSTOMERS_API, params={"search": "lakshmi"}, headers=admin_headers)).json()["data"]
    by_phone = (await client.get(CUSTOMERS_API, params={"search": "7700002"}, headers=admin_headers)).json()["data"]

    assert [r["name"] for r in by_name] == ["Lakshmi Menon"]
    assert [r["name"] for r in by_phone] == ["Someone Else"]


async def test_staff_accounts_are_not_customers(client, admin_headers):
    rows = (await client.get(CUSTOMERS_API, headers=admin_headers)).json()["data"]

    assert all(r["email"] != "admin@zeen.com" for r in rows)


async def test_tags_are_set_listed_and_filterable(client, admin_headers, customer):
    response = await client.put(
        f"{CUSTOMERS_API}/{customer.id}/tags", json={"tags": ["VIP", " vip ", "Frequent returner"]}, headers=admin_headers
    )
    tags = await client.get(f"{CUSTOMERS_API}/tags", headers=admin_headers)
    filtered = await client.get(CUSTOMERS_API, params={"tag": "VIP"}, headers=admin_headers)

    assert response.json()["data"] == ["VIP", "Frequent returner"]
    assert tags.json()["data"] == ["Frequent returner", "VIP"]
    assert [r["id"] for r in filtered.json()["data"]] == [str(customer.id)]


async def test_notes_are_added_shown_and_deleted(client, admin_headers, customer):
    note = (await client.post(f"{CUSTOMERS_API}/{customer.id}/notes", json={"body": "Prefers evening delivery"}, headers=admin_headers)).json()["data"]

    detail = (await client.get(f"{CUSTOMERS_API}/{customer.id}", headers=admin_headers)).json()["data"]
    deleted = await client.delete(f"{CUSTOMERS_API}/{customer.id}/notes/{note['id']}", headers=admin_headers)
    after = (await client.get(f"{CUSTOMERS_API}/{customer.id}", headers=admin_headers)).json()["data"]

    assert [n["body"] for n in detail["notes"]] == ["Prefers evening delivery"]
    assert detail["notes"][0]["author_name"]
    assert deleted.status_code == 204
    assert after["notes"] == []


async def test_detail_includes_addresses_and_order_history(client, admin_headers, customer, customer_auth, order_in):
    order = await order_in(customer_auth)

    detail = (await client.get(f"{CUSTOMERS_API}/{customer.id}", headers=admin_headers)).json()["data"]
    history = (await client.get(f"{CUSTOMERS_API}/{customer.id}/orders", headers=admin_headers)).json()["data"]

    assert detail["addresses"][0]["city"] == "Bengaluru"
    assert [o["id"] for o in history] == [order["id"]]


async def test_customer_management_needs_permission(client, staff_headers, staff_with_customers, customer):
    legacy = await client.get(CUSTOMERS_API, headers=staff_headers)
    viewer = await client.get(CUSTOMERS_API, headers=staff_with_customers)
    tagging = await client.put(f"{CUSTOMERS_API}/{customer.id}/tags", json={"tags": ["x"]}, headers=staff_with_customers)

    assert legacy.status_code == 403
    assert viewer.status_code == 200
    assert tagging.status_code == 403


async def test_customers_are_isolated_per_tenant(other_client, other_admin_headers, customer):
    detail = await other_client.get(f"{CUSTOMERS_API}/{customer.id}", headers=other_admin_headers)
    listed = (await other_client.get(CUSTOMERS_API, headers=other_admin_headers)).json()["data"]

    assert detail.status_code == 404
    assert listed == []


async def test_a_staff_account_is_not_a_customer_record(client, admin_headers, make_user, tenant):
    staff = await make_user(tenant=tenant, role="STAFF", email="s2@zeen.com")

    response = await client.get(f"{CUSTOMERS_API}/{staff.id}", headers=admin_headers)

    assert response.status_code == 404





# ------------------------------------------------------------ blocking orders


async def _block(client, headers, customer_id, blocked=True, reason="Repeated fake orders"):
    return await client.put(
        f"{CUSTOMERS_API}/{customer_id}/order-block",
        json={"blocked": blocked, "reason": reason},
        headers=headers,
    )


async def test_a_blocked_customer_cannot_order(
    client, admin_headers, customer, customer_auth, address, variant, add_to_cart, place_order
):
    blocked = await _block(client, admin_headers, customer.id)
    await add_to_cart(customer_auth, variant["id"], 1)

    response = await place_order(customer_auth, address["id"])

    assert blocked.json()["data"]["order_blocked"] is True
    assert blocked.json()["data"]["order_block_reason"] == "Repeated fake orders"
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CUSTOMER_BLOCKED"


async def test_a_blocked_customer_cannot_order_as_a_guest_either(client, admin_headers, customer, variant):
    await _block(client, admin_headers, customer.id)
    cart = (await client.post("/api/v1/cart/guest")).json()["data"]
    headers = {"X-Cart-Token": cart["guest_token"]}
    await client.post("/api/v1/cart/items", json={"variant_id": variant["id"], "quantity": 1}, headers=headers)

    response = await client.post(
        "/api/v1/checkout/guest",
        json={"contact": {"name": "Same Person", "phone": customer.phone}, "address": address_payload()},
        headers=headers,
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CUSTOMER_BLOCKED"


async def test_unblocking_lets_them_order_again_and_keeps_history(
    client, admin_headers, customer, customer_auth, order_in, variant, add_to_cart, address, place_order
):
    earlier = await order_in(customer_auth)
    await _block(client, admin_headers, customer.id)
    await _block(client, admin_headers, customer.id, blocked=False)
    await add_to_cart(customer_auth, variant["id"], 1)

    response = await place_order(customer_auth, address["id"])
    history = (await client.get(f"{CUSTOMERS_API}/{customer.id}/orders", headers=admin_headers)).json()["data"]
    detail = (await client.get(f"{CUSTOMERS_API}/{customer.id}", headers=admin_headers)).json()["data"]

    assert response.status_code == 201
    assert earlier["id"] in [o["id"] for o in history]
    assert detail["order_blocked"] is False
    assert detail["order_block_reason"] is None


async def test_blocking_leaves_existing_orders_alone(client, admin_headers, customer, customer_auth, order_in):
    order = await order_in(customer_auth)

    await _block(client, admin_headers, customer.id)
    fetched = (await client.get(f"/api/v1/admin/orders/{order['id']}", headers=admin_headers)).json()["data"]

    assert fetched["status"] == "PENDING"


async def test_blocked_customers_can_be_listed(client, admin_headers, customer, make_user, tenant):
    await make_user(tenant=tenant, phone="+919777700099")
    await _block(client, admin_headers, customer.id)

    blocked = (await client.get(CUSTOMERS_API, params={"blocked": True}, headers=admin_headers)).json()["data"]

    assert [c["id"] for c in blocked] == [str(customer.id)]


async def test_blocking_is_recorded_and_needs_customers_manage(client, admin_headers, staff_with_customers, customer):
    denied = await _block(client, staff_with_customers, customer.id)
    await _block(client, admin_headers, customer.id)
    logs = (await client.get("/api/v1/admin/audit-logs", params={"entity_id": str(customer.id)}, headers=admin_headers)).json()["data"]

    assert denied.status_code == 403
    assert logs[0]["action"] == "customer.order_blocked"


async def test_another_store_cannot_block_our_customer(other_client, other_admin_headers, customer):
    response = await _block(other_client, other_admin_headers, customer.id)

    assert response.status_code == 404
