"""External services report honestly whether they are connected."""

from __future__ import annotations

from tests.admin.conftest import API


async def test_ccavenue_is_pending_and_shiprocket_is_integrated(client, admin_headers):
    response = await client.get(f"{API}/admin/integrations", headers=admin_headers)

    status = {i["key"]: i for i in response.json()["data"]}
    assert status["ccavenue"]["integrated"] is False
    assert status["shiprocket"]["integrated"] is True
    assert status["shiprocket"]["required_settings"] == [
        "SHIPROCKET_EMAIL", "SHIPROCKET_PASSWORD", "SHIPROCKET_TENANT_ID"
    ]
    assert "CCAVENUE_MERCHANT_ID" in status["ccavenue"]["required_settings"]


async def test_customers_cannot_see_integrations(client, customer_headers):
    response = await client.get(f"{API}/admin/integrations", headers=customer_headers)

    assert response.status_code == 403
