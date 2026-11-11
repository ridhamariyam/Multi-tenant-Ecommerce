"""Platform operators: domain checks by DNS, the cross-brand domain list, totals,
and an audit trail in the affected brand's own activity log."""

from __future__ import annotations

import json

import dns.exception
import pytest
from sqlalchemy import select

from app.audit.models import AuditLog
from app.stores import dns_check

DOMAINS = "/api/v1/brand/domains"
ADMIN = "/api/v1/platform/admin"


@pytest.fixture
def dns_records(monkeypatch):
    """name -> TXT strings; a name mapped to an exception raises it."""
    records: dict[str, object] = {}

    async def fake_lookup(name: str) -> list[str]:
        value = records.get(name, [])
        if isinstance(value, Exception):
            raise value
        return list(value)  # type: ignore[arg-type]

    monkeypatch.setattr(dns_check, "lookup_txt", fake_lookup)
    return records


async def _add_domain(platform, brand, domain="shop.alpha.example"):
    response = await platform.post(DOMAINS, json={"domain": domain}, headers=brand.headers)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def test_a_matching_txt_record_verifies_the_domain(platform, session, brand_a, dns_records):
    domain = await _add_domain(platform, brand_a)
    dns_records["_cliq-verify.shop.alpha.example"] = ["v=spf1 -all", domain["verification_record"]]

    response = await platform.post(f"{DOMAINS}/{domain['id']}/check", headers=brand_a.headers)

    body = response.json()["data"]
    assert response.status_code == 200
    assert body["verified"] is True
    assert body["domain"]["verified_at"] is not None
    assert body["domain"]["verification_record"] is None  # nothing left to publish
    entry = await session.scalar(select(AuditLog).where(AuditLog.action == "domain.verified"))
    assert entry is not None and entry.tenant_id == brand_a.id


async def test_a_missing_or_wrong_record_does_not_verify(platform, brand_a, dns_records):
    domain = await _add_domain(platform, brand_a)

    missing = (await platform.post(f"{DOMAINS}/{domain['id']}/check", headers=brand_a.headers)).json()["data"]
    dns_records["_cliq-verify.shop.alpha.example"] = ["cliq-verify=someone-elses-token"]
    wrong = (await platform.post(f"{DOMAINS}/{domain['id']}/check", headers=brand_a.headers)).json()["data"]

    assert missing["verified"] is False and "not found yet" in missing["problem"]
    assert wrong["verified"] is False and "does not contain" in wrong["problem"]
    assert wrong["found"] == ["cliq-verify=someone-elses-token"]
    assert wrong["domain"]["verified_at"] is None


async def test_a_dns_timeout_is_reported_not_treated_as_success(platform, brand_a, dns_records):
    domain = await _add_domain(platform, brand_a)
    dns_records["_cliq-verify.shop.alpha.example"] = dns.exception.Timeout()

    body = (await platform.post(f"{DOMAINS}/{domain['id']}/check", headers=brand_a.headers)).json()["data"]

    assert body["verified"] is False
    assert "did not answer" in body["problem"]


async def test_a_brand_cannot_check_another_brands_domain(platform, brand_a, brand_b, dns_records):
    domain = await _add_domain(platform, brand_b, "shop.beta.example")

    response = await platform.post(f"{DOMAINS}/{domain['id']}/check", headers=brand_a.headers)

    assert response.status_code == 404


async def test_operators_list_pending_domains_across_brands(platform, make_merchant, brand_a, brand_b):
    admin = await make_merchant("ops@cliq.example.com", platform_admin=True)
    await _add_domain(platform, brand_a)
    await _add_domain(platform, brand_b, "shop.beta.example")

    response = await platform.get(f"{ADMIN}/domains", params={"status": "pending"}, headers=admin.headers)
    searched = await platform.get(f"{ADMIN}/domains", params={"search": "beta"}, headers=admin.headers)

    rows = response.json()["data"]
    assert response.status_code == 200
    assert {(r["domain"]["domain"], r["brand_name"]) for r in rows} == {
        ("shop.alpha.example", "Brand Alpha"),
        ("shop.beta.example", "Brand Beta"),
    }
    assert [r["domain"]["domain"] for r in searched.json()["data"]] == ["shop.beta.example"]


async def test_brand_owners_cannot_use_operator_endpoints(platform, brand_a):
    for method, path in [("get", "/domains"), ("get", "/overview")]:
        response = await getattr(platform, method)(f"{ADMIN}{path}", headers=brand_a.owner.headers)
        assert response.status_code == 403, path


async def test_operator_dns_check_verifies_and_is_audited(platform, session, make_merchant, brand_a, dns_records):
    admin = await make_merchant("ops@cliq.example.com", platform_admin=True)
    domain = await _add_domain(platform, brand_a)
    dns_records["_cliq-verify.shop.alpha.example"] = [domain["verification_record"]]

    response = await platform.post(f"{ADMIN}/domains/{domain['id']}/check", headers=admin.headers)

    assert response.json()["data"]["verified"] is True
    entry = await session.scalar(select(AuditLog).where(AuditLog.action == "domain.verified"))
    assert entry.tenant_id == brand_a.id
    assert entry.actor_role == "PLATFORM_ADMIN"
    assert entry.actor_id is None
    assert "ops@cliq.example.com" in entry.actor_name


async def test_suspending_and_reinstating_is_in_the_brands_activity_log(platform, session, make_merchant, brand_a):
    admin = await make_merchant("ops@cliq.example.com", platform_admin=True)

    await platform.post(f"{ADMIN}/brands/{brand_a.id}/suspend", json={"reason": "Chargeback fraud review"}, headers=admin.headers)
    await platform.post(f"{ADMIN}/brands/{brand_a.id}/activate", headers=admin.headers)

    entries = (
        await session.scalars(select(AuditLog).where(AuditLog.tenant_id == brand_a.id).order_by(AuditLog.created_at))
    ).all()
    actions = [(e.action, e.summary) for e in entries if e.actor_role == "PLATFORM_ADMIN"]
    assert actions == [("brand.suspended", "Suspended: Chargeback fraud review"), ("brand.reinstated", "Reinstated")]


async def test_overview_counts_without_business_data(platform, make_merchant, brand_a, brand_b):
    admin = await make_merchant("ops@cliq.example.com", platform_admin=True)
    await _add_domain(platform, brand_a)
    await platform.post("/api/v1/brand/store/publish", json={"published": True}, headers=brand_b.headers)
    await platform.post(f"{ADMIN}/brands/{brand_a.id}/suspend", json={"reason": "Review"}, headers=admin.headers)

    data = (await platform.get(f"{ADMIN}/overview", headers=admin.headers)).json()["data"]

    assert data["brands_suspended"] == 1
    assert data["brands_active"] == data["brands_total"] - 1
    assert data["stores_published"] >= 1
    assert data["domains_pending"] == 1
    assert data["merchant_accounts"] >= 3
    assert set(data) == {
        "brands_total", "brands_active", "brands_suspended", "stores_published", "domains_pending", "merchant_accounts",
    }


async def test_operators_see_system_health_and_missing_providers(platform, make_merchant, brand_a):
    admin = await make_merchant("ops@cliq.example.com", platform_admin=True)

    response = await platform.get(f"{ADMIN}/system", headers=admin.headers)
    owner = await platform.get(f"{ADMIN}/system", headers=brand_a.owner.headers)

    assert owner.status_code == 403
    body = response.json()["data"]
    assert response.status_code == 200
    assert body["database"] is True and body["redis"] is True
    assert {j["name"] for j in body["jobs"]} >= {"order-sheets", "expire-orders"}
    providers = {p["key"]: p for p in body["providers"]}
    assert "razorpay" in providers and "smtp" in providers
    assert all("secret" not in json.dumps(p).lower() for p in body["providers"])
