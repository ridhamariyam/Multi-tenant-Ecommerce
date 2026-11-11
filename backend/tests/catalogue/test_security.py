"""Catalogue access control: tenant isolation and role permissions."""

from __future__ import annotations

from app.auth.constants import UserRole, UserStatus
from app.auth.security import create_access_token
from tests.catalogue.factories import (
    CATEGORIES,
    IMAGE,
    PRODUCTS,
    VARIANTS,
    make_category,
    make_product,
    make_variant,
)
from tests.conftest import headers_for

UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"


async def test_another_tenants_category_cannot_be_read(
    other_client, other_admin_headers, category
):
    response = await other_client.get(
        f"{CATEGORIES}/{category['id']}", headers=other_admin_headers
    )

    assert response.status_code == 404


async def test_another_tenants_category_cannot_be_updated(
    other_client, other_admin_headers, category
):
    response = await other_client.patch(
        f"{CATEGORIES}/{category['id']}",
        json={"name": "Hijacked"},
        headers=other_admin_headers,
    )

    assert response.status_code == 404


async def test_another_tenants_category_cannot_be_deleted(
    other_client, other_admin_headers, category
):
    response = await other_client.delete(
        f"{CATEGORIES}/{category['id']}", headers=other_admin_headers
    )

    assert response.status_code == 404


async def test_another_tenants_product_cannot_be_read(
    other_client, other_admin_headers, product
):
    response = await other_client.get(
        f"{PRODUCTS}/{product['id']}", headers=other_admin_headers
    )

    assert response.status_code == 404


async def test_another_tenants_variant_cannot_be_read(
    other_client, other_admin_headers, variant
):
    response = await other_client.get(
        f"{VARIANTS}/{variant['id']}", headers=other_admin_headers
    )

    assert response.status_code == 404


async def test_a_listing_only_shows_the_callers_own_tenant(
    client, other_client, admin_headers, other_admin_headers
):
    await make_category(client, admin_headers, name="Mine")
    await make_category(other_client, other_admin_headers, name="Theirs")

    response = await client.get(CATEGORIES, headers=admin_headers)

    body = response.json()
    assert body["meta"]["total_items"] == 1
    assert [c["name"] for c in body["data"]] == ["Mine"]


async def test_a_product_cannot_be_created_in_another_tenants_category(
    other_client, other_admin_headers, category
):
    response = await other_client.post(
        PRODUCTS,
        json={
            "category_id": category["id"],
            "name": "Smuggled",
            "images": [IMAGE],
        },
        headers=other_admin_headers,
    )

    assert response.status_code == 404
    assert response.json()["message"] == "Category not found"


async def test_a_product_cannot_be_moved_into_another_tenants_category(
    other_client, other_admin_headers, category
):
    own_category = await make_category(other_client, other_admin_headers, name="Own")
    own_product = await make_product(
        other_client, other_admin_headers, own_category["id"]
    )

    response = await other_client.patch(
        f"{PRODUCTS}/{own_product['id']}",
        json={"category_id": category["id"]},
        headers=other_admin_headers,
    )

    assert response.status_code == 404


async def test_a_variant_cannot_be_added_to_another_tenants_product(
    other_client, other_admin_headers, product
):
    response = await other_client.post(
        f"{PRODUCTS}/{product['id']}/variants",
        json={"sku": "SMUGGLE-1", "name": "Smuggled", "price": "10.00"},
        headers=other_admin_headers,
    )

    assert response.status_code == 404


async def test_listing_another_tenants_variants_is_a_404(
    other_client, other_admin_headers, product
):
    response = await other_client.get(
        f"{PRODUCTS}/{product['id']}/variants", headers=other_admin_headers
    )

    assert response.status_code == 404


async def test_filtering_by_another_tenants_category_is_a_404(
    other_client, other_admin_headers, category
):
    response = await other_client.get(
        PRODUCTS, params={"category_id": category["id"]}, headers=other_admin_headers
    )

    assert response.status_code == 404


async def test_the_same_category_name_may_exist_in_two_tenants(
    other_client, other_admin_headers, category
):
    response = await other_client.post(
        CATEGORIES, json={"name": category["name"]}, headers=other_admin_headers
    )

    assert response.status_code == 201


async def test_the_same_sku_may_exist_in_two_tenants(
    client, other_client, admin_headers, other_admin_headers, product
):
    await make_variant(client, admin_headers, product["id"], sku="SHARED-1")
    their_category = await make_category(other_client, other_admin_headers)
    their_product = await make_product(
        other_client, other_admin_headers, their_category["id"]
    )

    response = await other_client.post(
        f"{PRODUCTS}/{their_product['id']}/variants",
        json={"sku": "SHARED-1", "name": "Theirs", "price": "1.00"},
        headers=other_admin_headers,
    )

    assert response.status_code == 201


async def test_a_tenant_id_in_the_body_is_rejected(
    client, admin_headers, other_tenant, tenant
):
    response = await client.post(
        CATEGORIES,
        json={"name": "Dresses", "tenant_id": str(other_tenant.id)},
        headers=admin_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == "tenant_id"

    clean = await client.post(CATEGORIES, json={"name": "Dresses"}, headers=admin_headers)
    assert clean.json()["data"]["tenant_id"] == str(tenant.id)


async def test_a_forged_tenant_claim_does_not_change_scope(
    client, make_user, tenant, other_tenant
):
    """The token's tenant must match the hostname's tenant, or it is refused."""
    admin = await make_user(
        tenant=tenant, email="forge@zeen.com", role=UserRole.ADMIN.value
    )
    forged = create_access_token(
        user_id=admin.id, tenant_id=other_tenant.id, role=admin.role
    )

    response = await client.get(
        CATEGORIES, headers={"Authorization": f"Bearer {forged}"}
    )

    assert response.status_code == 401


async def test_staff_may_read_the_catalogue(client, staff_headers, tenant):
    response = await client.get(CATEGORIES, headers=staff_headers)

    assert response.status_code == 200


async def test_staff_may_not_write_to_the_catalogue(client, staff_headers, tenant):
    response = await client.post(
        CATEGORIES, json={"name": "Staff Made"}, headers=staff_headers
    )

    assert response.status_code == 403


async def test_a_customer_may_not_touch_the_catalogue(
    client, customer_headers, tenant
):
    response = await client.get(CATEGORIES, headers=customer_headers)

    assert response.status_code == 403


async def test_a_forged_role_claim_grants_nothing(client, make_user, tenant):
    """Role comes from the database row, not from the token."""
    customer = await make_user(tenant=tenant, role=UserRole.CUSTOMER.value)
    forged = create_access_token(
        user_id=customer.id, tenant_id=tenant.id, role=UserRole.ADMIN.value
    )

    response = await client.post(
        CATEGORIES,
        json={"name": "Escalated"},
        headers={"Authorization": f"Bearer {forged}"},
    )

    assert response.status_code == 403


async def test_a_deactivated_admin_loses_access(client, session, make_user, tenant):
    admin = await make_user(
        tenant=tenant, email="gone@zeen.com", role=UserRole.ADMIN.value
    )
    headers = headers_for(admin)
    admin.status = UserStatus.INACTIVE.value
    await session.commit()

    response = await client.get(CATEGORIES, headers=headers)

    assert response.status_code == 401


async def test_an_anonymous_caller_is_rejected(client, tenant):
    response = await client.get(CATEGORIES)

    assert response.status_code == 401
