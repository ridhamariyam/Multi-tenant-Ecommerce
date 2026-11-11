"""Admin review of the system GST defaults: who may, and that it stays in one store."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from app.audit.models import AuditLog
from tests.gst_defaults.conftest import GST, gst_payload


async def test_the_defaults_are_listed_awaiting_verification(client, admin_headers, set_gst):
    await set_gst()

    response = await client.get(f"{GST}/defaults", headers=admin_headers)

    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert body["status"] == "AWAITING_VERIFICATION"
    in_force = {rule["code"]: rule for rule in body["rules"] if rule["in_force"]}
    assert set(in_force) == {"APPAREL_UPTO_2500", "APPAREL_ABOVE_2500", "FALLBACK_UNCLASSIFIED"}
    assert all(rule["verification_status"] == "UNVERIFIED" for rule in body["rules"])
    assert Decimal(body["system_fallback_rate"]) == Decimal("18.00")


async def test_an_unsaved_store_reads_as_system_defaults(client, admin_headers):
    response = await client.get(GST, headers=admin_headers)

    body = response.json()["data"]
    assert body["is_system_default"] is True
    assert body["default_classification"] == "APPAREL"
    assert body["gstin"] is None and body["state"] is None


async def test_reviewing_verifies_new_order_lines(
    client, admin_headers, set_gst, new_variant, add_to_cart
):
    await set_gst()
    await new_variant("2000.00", hsn_code="6204")

    response = await client.post(
        f"{GST}/defaults/review", json={"reviewed": True}, headers=admin_headers
    )
    review = await client.get(f"{GST}/product-review", headers=admin_headers)

    assert response.status_code == 200, response.text
    assert response.json()["data"]["status"] == "REVIEWED"
    assert [row["verification"] for row in review.json()["data"]] == ["VERIFIED"]


async def test_changing_the_assumptions_reopens_the_review(client, admin_headers, set_gst):
    await set_gst()
    await client.post(f"{GST}/defaults/review", json={"reviewed": True}, headers=admin_headers)

    saved = await set_gst(fallback_gst_rate="12.00")

    assert saved["defaults_reviewed_at"] is None
    defaults = await client.get(f"{GST}/defaults", headers=admin_headers)
    assert defaults.json()["data"]["status"] == "AWAITING_VERIFICATION"


async def test_an_out_of_range_fallback_rate_is_rejected(client, admin_headers):
    response = await client.put(
        GST, json=gst_payload(fallback_gst_rate="101.00"), headers=admin_headers
    )

    assert response.status_code == 422


async def test_an_unknown_classification_is_rejected(client, admin_headers):
    response = await client.put(
        GST, json=gst_payload(default_classification="JEWELLERY"), headers=admin_headers
    )

    assert response.status_code == 422


async def test_the_review_is_audited(session, client, admin_headers, set_gst, tenant):
    await set_gst()

    await client.post(f"{GST}/defaults/review", json={"reviewed": True}, headers=admin_headers)

    actions = (
        await session.scalars(select(AuditLog.action).where(AuditLog.tenant_id == tenant.id))
    ).all()
    assert any("review" in action for action in actions), actions


async def test_staff_may_view_but_not_review(client, staff_headers, set_gst):
    await set_gst()

    view = await client.get(f"{GST}/defaults", headers=staff_headers)
    review = await client.post(
        f"{GST}/defaults/review", json={"reviewed": True}, headers=staff_headers
    )

    assert view.status_code == 200
    assert review.status_code == 403


async def test_customers_and_anonymous_callers_are_refused(client, customer_auth):
    assert (await client.get(f"{GST}/defaults", headers=customer_auth)).status_code == 403
    assert (await client.get(f"{GST}/product-review", headers=customer_auth)).status_code == 403
    assert (await client.get(f"{GST}/defaults")).status_code == 401


async def test_one_stores_review_and_settings_leave_another_alone(
    client, other_client, admin_headers, other_admin_headers, set_gst, other_tenant,
    new_variant,
):
    await set_gst(state="Kerala")
    await new_variant("2000.00")
    other = await other_client.put(
        GST, json=gst_payload(gst_enabled=False, fallback_gst_rate="3.00"),
        headers=other_admin_headers,
    )
    assert other.status_code == 200, other.text
    await other_client.post(
        f"{GST}/defaults/review", json={"reviewed": True}, headers=other_admin_headers
    )

    zeen = (await client.get(GST, headers=admin_headers)).json()["data"]
    zeen_defaults = (await client.get(f"{GST}/defaults", headers=admin_headers)).json()["data"]
    acme_products = await other_client.get(f"{GST}/product-review", headers=other_admin_headers)

    assert zeen["gst_enabled"] is True and zeen["fallback_gst_rate"] is None
    assert zeen_defaults["status"] == "AWAITING_VERIFICATION"
    # Acme sees none of Zeen's products.
    assert acme_products.json()["data"] == []


async def test_another_stores_admin_cannot_review_this_store(
    client, admin_headers, other_admin_headers, set_gst
):
    """A token from another store is refused on this store's domain."""
    await set_gst()

    response = await client.post(
        f"{GST}/defaults/review", json={"reviewed": True}, headers=other_admin_headers
    )

    assert response.status_code == 401
    # Zeen's review is untouched.
    zeen = await client.get(f"{GST}/defaults", headers=admin_headers)
    assert zeen.json()["data"]["status"] == "AWAITING_VERIFICATION"
