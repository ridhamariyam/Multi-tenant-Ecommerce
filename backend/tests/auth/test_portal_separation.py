"""The storefront and the admin panel are separate doors.

Customers sign in on the storefront with a phone code; admins and staff sign
in on the admin panel with a password, each through their own endpoint. These
tests pin that a customer can never come through the admin door, and that a
customer's token opens no staff-guarded route even if it is presented there.
"""

from __future__ import annotations

import re

import pytest
from fastapi.routing import APIRoute

from app.api.v1 import api_router
from app.auth.constants import UserRole
from app.auth.dependencies import require_admin, require_staff
from tests.conftest import ADMIN_PASSWORD, admin_login, headers_for, widget_login

API = "/api/v1"


def _dependency_calls(dependant, found: set) -> set:
    for sub in dependant.dependencies:
        found.add(sub.call)
        _dependency_calls(sub, found)
    return found


def _is_staff_guard(call) -> bool:
    if call is require_admin or call is require_staff:
        return True
    return getattr(call, "__qualname__", "").startswith("require_permission.")


_ANY_ID = "00000000-0000-4000-8000-000000000000"


def _staff_routes() -> list[tuple[str, str]]:
    routes = []
    for included in api_router.routes:
        router = getattr(included, "original_router", None)
        for route in getattr(router, "routes", [included]):
            if not isinstance(route, APIRoute):
                continue
            if not any(_is_staff_guard(c) for c in _dependency_calls(route.dependant, set())):
                continue
            path = re.sub(r"\{[^}]+\}", _ANY_ID, route.path)
            for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
                routes.append((method, path))
    return routes


STAFF_ROUTES = _staff_routes()


def test_the_admin_api_is_found_at_all():
    # Guards against the sweep below silently checking nothing.
    assert len(STAFF_ROUTES) > 50
    assert any(path.startswith("/admin/") for _, path in STAFF_ROUTES)


@pytest.mark.parametrize("method,path", STAFF_ROUTES)
async def test_a_customer_token_opens_no_staff_route(client, customer_headers, method, path):
    response = await client.request(method, f"{API}{path}", headers=customer_headers, json={})

    assert response.status_code == 403, f"{method} {path} -> {response.status_code}"


@pytest.mark.parametrize("portal", ["admin", "staff"])
async def test_a_customer_cannot_sign_in_at_the_admin_panel(client, tenant, make_user, portal):
    # Customers hold no password (the database forbids one), so there is
    # nothing for either password door to match.
    await make_user(tenant=tenant, phone="+919000222333", email="shopper@zeen.com")

    for identifier in ("shopper@zeen.com", "+919000222333"):
        response = await client.post(
            f"{API}/{portal}/auth/login",
            json={"identifier": identifier, "password": ADMIN_PASSWORD},
        )
        assert response.status_code == 401, response.text


async def test_each_password_portal_takes_only_its_own_role(client, tenant, make_user):
    await make_user(tenant=tenant, email="boss@zeen.com", role=UserRole.ADMIN.value)
    await make_user(tenant=tenant, email="packer@zeen.com", role=UserRole.STAFF.value)

    staff_at_admin = await admin_login(client, "packer@zeen.com")
    admin_at_staff = await client.post(
        f"{API}/staff/auth/login",
        json={"identifier": "boss@zeen.com", "password": ADMIN_PASSWORD},
    )

    assert staff_at_admin.status_code == 401
    assert admin_at_staff.status_code == 401


async def test_staff_cannot_sign_in_through_the_storefront(client, tenant, make_user, msg91):
    await make_user(tenant=tenant, phone="+919000333444", role=UserRole.STAFF.value)

    response = await widget_login(client, msg91.token_for("+919000333444"))

    assert response.status_code == 401


async def test_a_demoted_account_loses_admin_access_at_once(client, tenant, make_user, session):
    # The role is read from the database on every request, not trusted from
    # the token, so an access token minted while staff stops working.
    staff = await make_user(tenant=tenant, email="leaver@zeen.com", role=UserRole.STAFF.value)
    headers = headers_for(staff)
    assert (await client.get(f"{API}/admin/orders", headers=headers)).status_code == 200

    staff.role = UserRole.CUSTOMER.value
    staff.password_hash = None
    await session.commit()

    assert (await client.get(f"{API}/admin/orders", headers=headers)).status_code == 403
