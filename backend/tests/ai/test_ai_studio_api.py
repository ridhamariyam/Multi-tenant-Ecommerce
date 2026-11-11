"""AI studio API: credits, configuration, permissions and the FASHN webhook."""

from __future__ import annotations

import uuid

from app.ai.providers import registry
from app.core.config import get_settings

AI = "/api/v1/admin/ai"


async def test_credits_show_balance_prices_and_whether_ai_is_set_up(client, admin_headers, monkeypatch):
    monkeypatch.setattr(registry, "_override", None)
    monkeypatch.setattr(get_settings(), "ai_provider", None)

    data = (await client.get(f"{AI}/credits", headers=admin_headers)).json()["data"]

    assert data["configured"] is False and data["provider"] is None
    assert data["price_table"]["balanced:1k"] == 2
    assert isinstance(data["balance"], int)


async def test_generating_without_a_provider_says_so(client, admin_headers, monkeypatch):
    monkeypatch.setattr(registry, "_override", None)
    monkeypatch.setattr(get_settings(), "ai_provider", None)

    response = await client.post(
        f"{AI}/jobs", json={"product_id": str(uuid.uuid4()), "virtual_model_id": str(uuid.uuid4())}, headers=admin_headers
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AI_PROVIDER_NOT_CONFIGURED"


async def test_bad_generation_settings_are_refused(client, admin_headers):
    response = await client.post(
        f"{AI}/jobs",
        json={"product_id": str(uuid.uuid4()), "virtual_model_id": str(uuid.uuid4()), "num_images": 9, "resolution": "8k"},
        headers=admin_headers,
    )
    assert response.status_code == 422


async def test_customers_cannot_use_the_ai_studio(client, make_user, tenant):
    from tests.conftest import headers_for

    shopper = await make_user(tenant=tenant, phone="+919800001234")
    assert (await client.get(f"{AI}/credits", headers=headers_for(shopper))).status_code == 403


async def test_an_unknown_job_is_not_found(client, admin_headers):
    assert (await client.get(f"{AI}/jobs/{uuid.uuid4()}", headers=admin_headers)).status_code == 404


async def test_the_fashn_webhook_needs_the_secret(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "fashn_webhook_secret", "hook-secret")

    wrong = await client.post("/api/v1/webhooks/fashn?token=nope", json={"id": "pred_1"})
    right = await client.post("/api/v1/webhooks/fashn?token=hook-secret", json={"id": "pred_unknown"})

    assert wrong.status_code == 401
    assert right.status_code == 200 and right.json()["data"]["result"] == "ignored"
