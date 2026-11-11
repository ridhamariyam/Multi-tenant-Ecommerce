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

SEARCH = DATA["routes"]["search"]
HISTORY = DATA["routes"]["history"]
SUGGESTIONS = DATA["routes"]["suggestions"]
PRODUCTS = DATA["routes"]["products"]


@pytest_asyncio.fixture(loop_scope="session")
async def search_shopper(make_user, tenant):
    return await make_user(tenant=tenant, phone="+919822224001")


@pytest.fixture
def search_auth(search_shopper) -> dict[str, str]:
    return headers_for(search_shopper)


@pytest_asyncio.fixture(loop_scope="session")
async def search_test_catalogue(client, admin_headers):

    category = await make_category(client, admin_headers, name="Apparel")

    product_data = [
        {
            "name": "Running Sneaker",
            "price": "1499.00",
            "brand": "Nike",
            "gender": "MEN",
            "options": [
                {"name": "Color", "value": "Black"},
                {"name": "Size", "value": "M"},
            ],
        },
        {
            "name": "Cotton T-Shirt",
            "price": "499.00",
            "brand": "Puma",
            "gender": "WOMEN",
            "options": [
                {"name": "Color", "value": "White"},
                {"name": "Size", "value": "S"},
            ],
        },
        {
            "name": "Formal Shirt",
            "price": "999.00",
            "brand": "Adidas",
            "gender": "UNISEX",
            "options": [
                {"name": "Color", "value": "Blue"},
                {"name": "Size", "value": "L"},
            ],
        },
    ]

    created = {}
    for item in product_data:
        prod = await make_product(
            client,
            admin_headers,
            category["id"],
            name=item["name"],
            status="ACTIVE",
            brand=item["brand"],
            gender=item["gender"],
        )
        payload = sample(DATA, "variant")
        payload["sku"] = f"SRCH-SKU-{item['name'][:3].upper()}"
        payload["price"] = item["price"]
        payload["options"] = item["options"]
        response = await client.post(
            f"{PRODUCTS}/{prod['id']}/variants", json=payload, headers=admin_headers
        )
        assert response.status_code == 201, response.text
        variant = response.json()["data"]
        created[item["name"]] = {"product": prod, "variant": variant}

    return created


@pytest_asyncio.fixture(loop_scope="session")
async def search_multi_variant_product(client, admin_headers):
    category = await make_category(client, admin_headers, name="Multi-Variant Apparel")
    product = await make_product(
        client, admin_headers, category["id"], name="Graphic Hoodie", status="ACTIVE", brand="Zeen"
    )

    combos = [
        ("Black", "S", "HOODIE-BLK-S"),
        ("Black", "M", "HOODIE-BLK-M"),
        ("Green", "S", "HOODIE-GRN-S"),
    ]
    variants = []
    for color, size, sku in combos:
        payload = sample(DATA, "variant")
        payload["sku"] = sku
        payload["options"] = [
            {"name": "Color", "value": color},
            {"name": "Size", "value": size},
        ]
        response = await client.post(
            f"{PRODUCTS}/{product['id']}/variants", json=payload, headers=admin_headers
        )
        assert response.status_code == 201, response.text
        variants.append(response.json()["data"])

    return {"product": product, "variants": variants}


@pytest_asyncio.fixture(loop_scope="session")
async def search_token_matching_catalogue(client, admin_headers):
    category = await make_category(client, admin_headers, name="Token Match Apparel")

    product_data = [
        {
            "name": "Women's Maxi Dress",
            "brand": "Zara",
            "short_description": "Elegant women's dress for evening wear",
            "gender": "WOMEN",
        },
        {
            "name": "Women's Casual Tops",
            "brand": "Zara",
            "short_description": "Comfortable women's tops for daily wear",
            "gender": "WOMEN",
        },
        {
            "name": "Men's Casual T-Shirt",
            "brand": "Zara",
            "short_description": "Everyday men's clothes essential",
            "gender": "MEN",
        },
        {
            "name": "Leather Wallet",
            "brand": "Fossil",
            "short_description": "Slim bifold wallet in genuine leather",
            "gender": None,
        },
    ]

    created = {}
    for item in product_data:
        prod = await make_product(
            client,
            admin_headers,
            category["id"],
            name=item["name"],
            status="ACTIVE",
            brand=item["brand"],
            short_description=item["short_description"],
            gender=item["gender"],
        )
        payload = sample(DATA, "variant")
        payload["sku"] = f"TOK-SKU-{uuid4().hex[:8].upper()}"
        payload["options"] = []
        response = await client.post(
            f"{PRODUCTS}/{prod['id']}/variants", json=payload, headers=admin_headers
        )
        assert response.status_code == 201, response.text
        created[item["name"]] = {"product": prod, "variant": response.json()["data"]}

    return created


@pytest_asyncio.fixture(loop_scope="session")
async def search_ratings_and_orders(session, tenant, search_shopper, make_user, search_test_catalogue):
    catalogue = search_test_catalogue

    # A second reviewer: one review per (user, product) is enforced at the
    # database level, so averaging two ratings on the same product needs two
    # distinct users.
    second_reviewer = await make_user(tenant=tenant, phone="+919822224002")

    reviews = [
        (catalogue["Cotton T-Shirt"]["product"]["id"], search_shopper.id, 5),
        (catalogue["Cotton T-Shirt"]["product"]["id"], second_reviewer.id, 3),
        (catalogue["Formal Shirt"]["product"]["id"], search_shopper.id, 2),
    ]
    for product_id, user_id, rating in reviews:
        session.add(
            Review(
                tenant_id=tenant.id,
                product_id=product_id,
                user_id=user_id,
                rating=rating,
                is_verified_purchase=True,
                is_approved=True,
            )
        )
    await session.commit()

    async def _place_order(item_name: str, quantity: int, order_status: str) -> None:
        variant = catalogue[item_name]["variant"]
        product = catalogue[item_name]["product"]
        unit_price = Decimal(str(variant["price"]))
        subtotal = unit_price * quantity

        order = Order(
            tenant_id=tenant.id,
            customer_id=search_shopper.id,
            order_number=f"ORD-{uuid4().hex[:10].upper()}",
            status=order_status,
            payment_status=PaymentStatus.PAID.value,
            subtotal=subtotal,
            shipping_amount=Decimal("0.00"),
            tax_amount=Decimal("0.00"),
            total_amount=subtotal,
            delivery_name="Search Tester",
            delivery_phone="+919876500002",
            delivery_address_line_1="1 Test Street",
            delivery_city="Testville",
            delivery_state="TS",
            delivery_postal_code="100001",
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
                quantity=quantity,
                subtotal=subtotal,
            )
        )
        await session.commit()

    await _place_order("Cotton T-Shirt", 5, OrderStatus.DELIVERED.value)
    await _place_order("Formal Shirt", 2, OrderStatus.DELIVERED.value)
    # A cancelled order for the Sneaker must NOT count toward its popularity.
    await _place_order("Running Sneaker", 10, OrderStatus.CANCELLED.value)

    return catalogue


@pytest_asyncio.fixture(loop_scope="session")
async def search_price_spread_catalogue(client, admin_headers):
    """Two products whose cheapest and dearest variants disagree about the order."""
    category = await make_category(client, admin_headers, name="Spread Apparel")

    spread = {
        "Budget Spreadwear Tee": ["100.00", "900.00"],
        "Premium Spreadwear Tee": ["500.00", "600.00"],
    }

    created = {}
    for name, prices in spread.items():
        product = await make_product(
            client,
            admin_headers,
            category["id"],
            name=name,
            status="ACTIVE",
            brand="Spreadwear",
        )
        for price in prices:
            payload = sample(DATA, "variant")
            payload["sku"] = f"SPRD-{uuid4().hex[:8].upper()}"
            payload["price"] = price
            payload["options"] = [{"name": "Size", "value": price}]
            response = await client.post(
                f"{PRODUCTS}/{product['id']}/variants",
                json=payload,
                headers=admin_headers,
            )
            assert response.status_code == 201, response.text
        created[name] = product

    return created


@pytest_asyncio.fixture(loop_scope="session")
async def second_shopper_auth(make_user, tenant):
    shopper = await make_user(tenant=tenant, phone="+919822224003")
    return headers_for(shopper)
