"""Production bootstrap provisions only the tenant and its admin; demo data stays in dev."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.auth.constants import UserRole
from app.commands import seed as seed_command
from app.commands.bootstrap import PRODUCTION_MIN_ADMIN_PASSWORD_LENGTH, bootstrap_tenant
from app.commands.seed_offers import DEMO_OFFERS, seed_demo_offers
from app.core.config import get_settings
from app.coupons.models import Coupon
from app.coupons.schemas import CouponUpdate
from app.coupons.service import CouponService
from app.tenants.models import Tenant, TenantDomain
from app.users.models import User

BOOTSTRAP = {
    "seed_tenant_name": "Bootstrap Store",
    "seed_tenant_slug": "bootstrap-store",
    "seed_tenant_domain": "bootstrap.test",
    "seed_admin_phone": "+919800001111",
    "seed_admin_email": "Owner@Bootstrap.test",
    "seed_admin_password": "x" * PRODUCTION_MIN_ADMIN_PASSWORD_LENGTH,
}


def _settings(environment: str, **overrides):
    return get_settings().model_copy(
        update={"environment": environment, **BOOTSTRAP, **overrides}
    )


async def test_production_bootstrap_creates_the_admin_and_no_demo_accounts(session):
    tenant = await bootstrap_tenant(session, _settings("production"))

    users = (await session.scalars(select(User).where(User.tenant_id == tenant.id))).all()
    assert [(user.email, user.role) for user in users] == [
        ("owner@bootstrap.test", UserRole.ADMIN.value)
    ]
    domain = await session.scalar(select(TenantDomain.domain))
    assert domain == "bootstrap.test"
    # Reachable at <slug>.<root> (the TLS allow-list needs the store) and unlimited.
    from app.stores.models import Store
    from app.subscriptions.service import SubscriptionService
    from app.tenants.tls import certificate_allowed

    store = await session.scalar(select(Store).where(Store.tenant_id == tenant.id))
    assert store.subdomain == "bootstrap-store" and store.published is True
    assert (await SubscriptionService(session, tenant.id).effective_plan()).code == "PLATFORM"
    assert await certificate_allowed(session, "bootstrap-store.localhost") is True


async def test_bootstrap_is_safe_to_run_twice(session):
    settings = _settings("production")

    first = await bootstrap_tenant(session, settings)
    second = await bootstrap_tenant(session, settings)

    assert first.id == second.id
    assert len((await session.scalars(select(Tenant))).all()) == 1
    assert len((await session.scalars(select(User))).all()) == 1


async def test_production_bootstrap_refuses_a_short_admin_password(session):
    weak = _settings(
        "production", seed_admin_password="x" * (PRODUCTION_MIN_ADMIN_PASSWORD_LENGTH - 1)
    )

    with pytest.raises(RuntimeError, match="at least"):
        await bootstrap_tenant(session, weak)

    assert (await session.scalars(select(Tenant))).all() == []


async def test_production_never_seeds_demo_data(session, monkeypatch):
    monkeypatch.setattr(get_settings(), "environment", "production")
    tenant = await bootstrap_tenant(session, _settings("production"))

    with pytest.raises(RuntimeError, match="never seeded in production"):
        await seed_command.seed_demo(session, tenant)
    with pytest.raises(RuntimeError, match="never seeded in production"):
        await seed_command.seed()

    staff = await session.scalars(select(User).where(User.role == UserRole.STAFF.value))
    assert staff.all() == []


async def test_demo_offers_are_available_to_the_storefront(client, session, tenant):
    await seed_demo_offers(session, tenant)

    response = await client.get("/api/v1/coupons/offers")

    assert response.status_code == 200
    offers = {offer["code"]: offer for offer in response.json()["data"]}
    assert set(offers) == {offer.code for offer in DEMO_OFFERS}
    assert offers["CLIQ_WELCOME"]["discount_value"] == "15.00"
    assert offers["CLIQ_WELCOME"]["first_order_only"] is True
    assert offers["CLIQ_MORE"]["discount_value"] == "20.00"
    assert offers["CLIQ_MORE"]["min_quantity"] == 3
    assert offers["CLIQ_DELIVERY"]["discount_type"] == "FREE_SHIPPING"
    assert offers["CLIQ_DELIVERY"]["min_order_amount"] == "1499.00"


async def test_demo_offers_seed_preserves_admin_edits(session, tenant):
    await seed_demo_offers(session, tenant)
    service = CouponService(session, tenant.id)
    welcome = await service.coupons.get_by_code("CLIQ_WELCOME")
    await service.update(welcome.id, CouponUpdate(is_active=False))

    await seed_demo_offers(session, tenant)

    coupons = (await session.scalars(select(Coupon).where(Coupon.tenant_id == tenant.id))).all()
    assert len(coupons) == len(DEMO_OFFERS)
    assert (await service.coupons.get_by_code("CLIQ_WELCOME")).is_active is False
    assert {offer.code for offer in await service.live_offers()} == {"CLIQ_MORE", "CLIQ_DELIVERY"}


async def test_demo_offers_are_scoped_to_the_seeded_tenant(
    session, tenant, other_tenant, other_client
):
    await seed_demo_offers(session, tenant)

    response = await other_client.get("/api/v1/coupons/offers")

    assert response.status_code == 200
    assert response.json()["data"] == []


async def test_production_never_seeds_demo_offers(session, tenant, monkeypatch):
    monkeypatch.setattr(get_settings(), "environment", "production")

    with pytest.raises(RuntimeError, match="never seeded in production"):
        await seed_demo_offers(session, tenant)

    assert (await session.scalars(select(Coupon))).all() == []
