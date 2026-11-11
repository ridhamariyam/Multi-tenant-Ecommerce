"""Fixtures for the checkout and order tests."""

from __future__ import annotations

import pytest
import pytest_asyncio

from app.auth.constants import UserRole
from app.auth.permissions import Permission
from tests.catalogue.factories import PRODUCTS, make_category, make_product
from tests.conftest import headers_for
from tests.helpers import load_data, sample

DATA = load_data(__file__)

ADDRESSES = DATA["routes"]["addresses"]
CHECKOUT = DATA["routes"]["checkout"]
ORDERS = DATA["routes"]["orders"]
ADMIN_ORDERS = DATA["routes"]["admin_orders"]
CART = DATA["routes"]["cart"]
CUSTOMERS = DATA["customers"]


def address_payload(**overrides) -> dict:
    return sample(DATA, "address", **overrides)


@pytest_asyncio.fixture(loop_scope="session")
async def customer(make_user, tenant):
    return await make_user(tenant=tenant, phone=CUSTOMERS["buyer"])


@pytest.fixture
def customer_auth(customer) -> dict[str, str]:
    return headers_for(customer)


@pytest_asyncio.fixture(loop_scope="session")
async def new_variant(client, admin_headers, tax_ready):
    """Factory: `await new_variant(initial_quantity=3, price="1199.00")`."""
    counter = {"n": 0}
    category = await make_category(client, admin_headers, name="Order Test Category")

    async def _make(**overrides) -> dict:
        counter["n"] += 1
        product = await make_product(
            client,
            admin_headers,
            category["id"],
            name=f"T-Shirt {counter['n']}",
            status=overrides.pop("product_status", "ACTIVE"),
        )
        payload = sample(DATA, "variant", **overrides)
        payload["sku"] = f"ORD-SKU-{counter['n']}"

        response = await client.post(
            f"{PRODUCTS}/{product['id']}/variants", json=payload, headers=admin_headers
        )
        assert response.status_code == 201, response.text
        return response.json()["data"]

    return _make


@pytest_asyncio.fixture(loop_scope="session")
async def variant(new_variant) -> dict:
    """An ACTIVE variant priced at 999.00 with 10 in stock."""
    return await new_variant()


@pytest_asyncio.fixture(loop_scope="session")
async def add_to_cart(client):
    """Factory: `await add_to_cart(headers, variant_id, quantity=2)`."""

    async def _add(headers, variant_id, quantity: int = 1):
        response = await client.post(
            f"{CART}/items",
            json={"variant_id": variant_id, "quantity": quantity},
            headers=headers,
        )
        assert response.status_code == 201, response.text
        return response.json()["data"]

    return _add


@pytest_asyncio.fixture(loop_scope="session")
async def save_address(client):
    """Factory: `await save_address(headers, city="Kochi")`."""

    async def _save(headers, **overrides) -> dict:
        response = await client.post(
            ADDRESSES, json=address_payload(**overrides), headers=headers
        )
        assert response.status_code == 201, response.text
        return response.json()["data"]

    return _save


@pytest_asyncio.fixture(loop_scope="session")
async def address(save_address, customer_auth) -> dict:
    return await save_address(customer_auth)


@pytest_asyncio.fixture(loop_scope="session")
async def place_order(client):
    """Factory: `await place_order(headers, address_id, coupon_code=None)`."""

    async def _place(
        headers,
        address_id,
        coupon_code: str | None = None,
        payment_method: str | None = None,
    ):
        payload = {"address_id": str(address_id)}
        if coupon_code is not None:
            payload["coupon_code"] = coupon_code
        if payment_method is not None:
            payload["payment_method"] = payment_method
        return await client.post(CHECKOUT, json=payload, headers=headers)

    return _place


@pytest_asyncio.fixture(loop_scope="session")
async def preview_checkout(client):
    """Factory: `await preview_checkout(headers, coupon_code=None)`."""

    async def _preview(
        headers, coupon_code: str | None = None, payment_method: str | None = None
    ):
        params = {"coupon_code": coupon_code} if coupon_code is not None else {}
        request = (
            {"json": {"payment_method": payment_method}}
            if payment_method is not None
            else {}
        )
        return await client.post(
            f"{CHECKOUT}/preview", params=params, headers=headers, **request
        )

    return _preview


@pytest_asyncio.fixture(loop_scope="session")
async def order(client, customer_auth, address, variant, add_to_cart, place_order) -> dict:
    """A placed order: 2 x 999.00, PENDING, unpaid."""
    await add_to_cart(customer_auth, variant["id"], 2)
    response = await place_order(customer_auth, address["id"])
    assert response.status_code == 201, response.text
    return response.json()["data"]


@pytest_asyncio.fixture(loop_scope="session")
async def order_in(client, variant, add_to_cart, save_address):
    """Factory: `await order_in(headers, quantity=1, state="Kerala")` -> a placed order.

    Each call places one cash order for `variant`, delivered to a newly saved
    address with any field overridden.
    """

    async def _order(headers, quantity: int = 1, **address) -> dict:
        await add_to_cart(headers, variant["id"], quantity)
        saved = await save_address(headers, **address)
        response = await client.post(
            CHECKOUT, json={"address_id": saved["id"]}, headers=headers
        )
        assert response.status_code == 201, response.text
        return response.json()["data"]

    return _order


@pytest_asyncio.fixture(loop_scope="session")
async def set_status(client, admin_headers):
    """Factory: `await set_status(order_id, "SHIPPED", expect=200, note=...)` -> body."""

    async def _set(order_id, value: str, expect: int = 200, **fields) -> dict:
        response = await client.patch(
            f"{ADMIN_ORDERS}/{order_id}/status",
            json={"status": value, **fields},
            headers=admin_headers,
        )
        assert response.status_code == expect, response.text
        return response.json()

    return _set


@pytest_asyncio.fixture(loop_scope="session")
async def staff_with_customers(make_user, tenant, session) -> dict[str, str]:
    """Headers for a STAFF account that may see customers but not manage them."""
    staff = await make_user(
        tenant=tenant, email="customers-viewer@zeen.com", role=UserRole.STAFF.value
    )
    staff.permissions = [Permission.CUSTOMERS_VIEW.value]
    await session.commit()
    return headers_for(staff)
