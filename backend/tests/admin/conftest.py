"""Fixtures for admin-panel features: staff with chosen permissions."""

from __future__ import annotations

import pytest_asyncio

from app.auth.constants import UserRole
from tests.conftest import headers_for

API = "/api/v1"
STAFF = f"{API}/admin/staff"
AUDIT = f"{API}/admin/audit-logs"
CMS = f"{API}/admin/cms"
STOREFRONT_CMS = f"{API}/storefront/cms"
PRODUCTS = f"{API}/catalogue/products"
CATEGORIES = f"{API}/catalogue/categories"


@pytest_asyncio.fixture(loop_scope="session")
async def staff_with(make_user, tenant, session):
    """Factory: headers for a STAFF account holding exactly these permissions."""
    counter = {"n": 0}

    async def _make(*permissions: str) -> dict[str, str]:
        counter["n"] += 1
        user = await make_user(
            tenant=tenant,
            email=f"perm{counter['n']}@zeen.com",
            phone=f"+91955500{counter['n']:04d}",
            role=UserRole.STAFF.value,
        )
        user.permissions = list(permissions)
        await session.commit()
        return headers_for(user)

    return _make
