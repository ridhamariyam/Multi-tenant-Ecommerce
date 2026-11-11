from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio

from app.orders.constants import OrderStatus
from app.orders.models import Order, OrderItem
from app.payments.constants import PaymentStatus
from app.ratings.models import Review
from tests.catalogue.factories import make_category, make_product
from tests.conftest import headers_for
from tests.helpers import load_data, sample

DATA = load_data(__file__)

REVIEWS = DATA["routes"]["reviews"]
ADMIN_REVIEWS = DATA["routes"]["admin_reviews"]
PRODUCTS = DATA["routes"]["products"]


def review_payload(product_id, **overrides) -> dict:
    return sample(DATA, "review", product_id=str(product_id), **overrides)


async def make_sellable_product(client, headers, name: str) -> dict:
    """A product with one active variant, ready to be ordered."""
    category = await make_category(client, headers, name=f"{name} Category")
    product = await make_product(
        client, headers, category["id"], name=name, status="ACTIVE"
    )

    payload = sample(DATA, "variant")
    payload["sku"] = f"REV-{uuid4().hex[:8].upper()}"
    response = await client.post(
        f"{PRODUCTS}/{product['id']}/variants", json=payload, headers=headers
    )
    assert response.status_code == 201, response.text

    return {"product": product, "variant": response.json()["data"]}


async def place_order(session, tenant, customer, listing, status: str) -> Order:
    """Write an order straight to the database, at whatever status the test needs."""
    product = listing["product"]
    variant = listing["variant"]
    unit_price = Decimal(str(variant["price"]))

    order = Order(
        tenant_id=tenant.id,
        customer_id=customer.id,
        order_number=f"ORD-{uuid4().hex[:10].upper()}",
        status=status,
        payment_status=PaymentStatus.PAID.value,
        subtotal=unit_price,
        shipping_amount=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        total_amount=unit_price,
        delivery_name="Review Tester",
        delivery_phone="+919876500100",
        delivery_address_line_1="1 Review Street",
        delivery_city="Reviewville",
        delivery_state="RV",
        delivery_postal_code="100100",
        delivery_country="IN",
    )
    session.add(order)
    await session.flush()

    session.add(
        OrderItem(
            tenant_id=tenant.id,
            order_id=order.id,
            variant_id=variant["id"],
            product_id=product["id"],
            product_name=product["name"],
            variant_name=variant["name"],
            sku=variant["sku"],
            unit_price=unit_price,
            quantity=1,
            subtotal=unit_price,
        )
    )
    await session.commit()
    return order


@pytest_asyncio.fixture(loop_scope="session")
async def reviewable_product(client, admin_headers):
    return await make_sellable_product(client, admin_headers, "Merino Sweater")


@pytest_asyncio.fixture(loop_scope="session")
async def buyer(make_user, tenant):
    return await make_user(tenant=tenant, phone="+919833330001")


@pytest_asyncio.fixture(loop_scope="session")
async def second_buyer(make_user, tenant):
    return await make_user(tenant=tenant, phone="+919833330002")


@pytest_asyncio.fixture(loop_scope="session")
async def non_buyer(make_user, tenant):
    return await make_user(tenant=tenant, phone="+919833330003")


@pytest.fixture
def buyer_auth(buyer) -> dict[str, str]:
    return headers_for(buyer)


@pytest.fixture
def second_buyer_auth(second_buyer) -> dict[str, str]:
    return headers_for(second_buyer)


@pytest.fixture
def non_buyer_auth(non_buyer) -> dict[str, str]:
    return headers_for(non_buyer)


@pytest_asyncio.fixture(loop_scope="session")
async def delivered_order(session, tenant, buyer, reviewable_product):
    return await place_order(
        session, tenant, buyer, reviewable_product, OrderStatus.DELIVERED.value
    )


@pytest_asyncio.fixture(loop_scope="session")
async def second_delivered_order(session, tenant, second_buyer, reviewable_product):
    return await place_order(
        session, tenant, second_buyer, reviewable_product, OrderStatus.DELIVERED.value
    )


@pytest_asyncio.fixture(loop_scope="session")
async def review(client, buyer_auth, reviewable_product, delivered_order) -> dict:
    response = await client.post(
        REVIEWS,
        json=review_payload(reviewable_product["product"]["id"]),
        headers=buyer_auth,
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


@pytest_asyncio.fixture(loop_scope="session")
async def other_tenant_listing(other_client, other_admin_headers):
    return await make_sellable_product(other_client, other_admin_headers, "Acme Widget")


@pytest_asyncio.fixture(loop_scope="session")
async def other_tenant_review(session, other_tenant, make_user, other_tenant_listing):
    """A review that belongs to Acme and must never surface on Zeen."""
    shopper = await make_user(tenant=other_tenant, phone="+919844440001")
    entry = Review(
        tenant_id=other_tenant.id,
        product_id=other_tenant_listing["product"]["id"],
        user_id=shopper.id,
        rating=5,
        title="Acme internal",
        comment="Should never reach another storefront",
        is_verified_purchase=True,
        is_approved=True,
    )
    session.add(entry)
    await session.commit()
    return entry
