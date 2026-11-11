"""Provision one tenant, its domain, its admin and default pricing; safe in production."""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.constants import UserRole
from app.auth.phone import normalize_phone
from app.auth.security import hash_password
from app.core.config import Settings, get_settings
from app.core.database import AsyncSessionLocal, dispose_engine
from app.tenants.models import Tenant, TenantDomain
from app.tenants.provisioning import ensure_tenant_defaults
from app.tenants.repository import TenantRepository
from app.users.repository import UserRepository

PRODUCTION_MIN_ADMIN_PASSWORD_LENGTH = 12


def check_bootstrap_settings(settings: Settings) -> None:
    """Refuse missing admin details, and a short admin password in production."""
    if not settings.seed_admin_phone:
        raise RuntimeError("SEED_ADMIN_PHONE is not configured")
    if not settings.seed_admin_email:
        raise RuntimeError("SEED_ADMIN_EMAIL is not configured")
    if not settings.seed_admin_password:
        raise RuntimeError("SEED_ADMIN_PASSWORD is not configured")
    if (
        settings.is_production
        and len(settings.seed_admin_password) < PRODUCTION_MIN_ADMIN_PASSWORD_LENGTH
    ):
        raise RuntimeError(
            "SEED_ADMIN_PASSWORD must be at least "
            f"{PRODUCTION_MIN_ADMIN_PASSWORD_LENGTH} characters in production"
        )


async def bootstrap_tenant(session: AsyncSession, settings: Settings) -> Tenant:
    """Create whatever of the tenant, domain, admin and pricing rows is missing."""
    check_bootstrap_settings(settings)

    slug = settings.seed_tenant_slug.strip().lower()
    domain = settings.seed_tenant_domain.strip().lower()
    email = settings.seed_admin_email.strip().lower()
    phone = normalize_phone(settings.seed_admin_phone)

    tenants = TenantRepository(session)
    users = UserRepository(session)

    tenant = await tenants.get_active_by_slug(slug)
    if tenant is None:
        tenant = Tenant(
            name=settings.seed_tenant_name,
            slug=slug,
            currency=settings.seed_tenant_currency,
            is_active=True,
        )
        session.add(tenant)
        await session.flush()
        print(f"Created tenant: {tenant.name} ({tenant.slug})")
    else:
        print(f"Tenant already exists: {tenant.name} ({tenant.slug})")

    existing_domain = await session.scalar(
        select(TenantDomain).where(TenantDomain.domain == domain)
    )
    if existing_domain is None:
        session.add(TenantDomain(tenant_id=tenant.id, domain=domain))
        await session.flush()
        print(f"Registered domain: {domain}")
    else:
        print(f"Domain already registered: {domain}")

    if await users.get_by_email(
        tenant_id=tenant.id,
        email=email,
        roles=frozenset({UserRole.ADMIN.value}),
    ) is None:
        await users.create(
            tenant_id=tenant.id,
            phone=phone,
            email=email,
            role=UserRole.ADMIN.value,
            name="Seed Admin",
            password_hash=await hash_password(settings.seed_admin_password),
        )
        print(f"Created tenant admin: {email}")
    else:
        print(f"Tenant admin already exists: {email}")

    await ensure_tenant_defaults(session, tenant, log=print)

    await session.commit()
    return tenant


async def bootstrap() -> None:
    """Run the bootstrap against the configured database."""
    settings = get_settings()
    async with AsyncSessionLocal() as session:
        await bootstrap_tenant(session, settings)
    await dispose_engine()
    print("Bootstrap completed successfully.")


def main() -> None:
    asyncio.run(bootstrap())


if __name__ == "__main__":
    main()
