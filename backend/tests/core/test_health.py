"""Liveness and readiness probes, and the endpoints removed as unsafe or dead."""

from __future__ import annotations


async def test_liveness_answers_without_dependencies(client):
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readiness_reports_a_dependency_that_is_down(client, monkeypatch):
    async def redis_down() -> bool:
        return False

    monkeypatch.setattr("app.main.redis_healthy", redis_down)

    response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["redis"] == "unavailable"


async def test_the_current_tenant_is_the_only_one_disclosed(client, tenant, other_tenant):
    current = await client.get("/api/v1/auth/tenant")
    listing = await client.get("/api/v1/auth/tenants")

    assert current.status_code == 200
    assert current.json()["data"]["slug"] == tenant.slug
    assert listing.status_code == 404


async def test_the_dead_staff_otp_route_is_gone(client, tenant):
    response = await client.post(
        "/api/v1/admin/auth/verify-otp",
        json={"verification_id": "00000000-0000-0000-0000-000000000000", "otp": "123456"},
    )

    assert response.status_code == 404
