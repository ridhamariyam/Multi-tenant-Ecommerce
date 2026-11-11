from __future__ import annotations

import asyncio
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.constants import UserRole
from app.catalogue.constants import CatalogueStatus
from app.catalogue.models import Category, InventoryItem, Product, ProductVariant
from app.catalogue.schemas import (
    CategoryCreate,
    ProductCreate,
    ProductImageCreate,
    VariantCreate,
    VariantOptionValue,
)
from app.catalogue.service import CategoryService, ProductService, VariantService
from app.commands.bootstrap import bootstrap_tenant
from app.commands.seed_offers import seed_demo_offers
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal, dispose_engine
from app.tenants.models import Tenant
from app.users.models import User
from app.users.service import UserService

CATEGORIES: list[tuple[str, str]] = [
    ("Dresses", "Day dresses, midis and occasion wear."),
    ("Tops", "Blouses, shirts and knitwear."),
    ("Bottoms", "Trousers, skirts and denim."),
    ("Outerwear", "Jackets, coats and overshirts."),
    ("Footwear", "Flats, heels, boots and sneakers."),
    ("Bags", "Totes, crossbodies and clutches."),
    ("Jewellery", "Everyday gold, silver and stones."),
    ("Scarves & Wraps", "Silk, wool and cotton layers."),
    ("Loungewear", "Soft separates for off-duty days."),
    ("Accessories", "Belts, sunglasses and small leather goods."),
]

PRODUCT_BRAND = "CliQ."

PRODUCTS: list[tuple[str, str, str, str, str, bool]] = [
    (
        "Dresses",
        "Sona Wrap Midi Dress",
        "Crinkled viscose wrap dress with a tie waist.",
        "3499.00",
        "SONA-WRAP",
        True,
    ),
    (
        "Tops",
        "Ira Poplin Shirt",
        "Boxy cotton poplin shirt with a camp collar.",
        "1899.00",
        "IRA-POPLIN",
        False,
    ),
    (
        "Bottoms",
        "Nila Wide-Leg Trouser",
        "High-rise wide-leg trouser in fluid twill.",
        "2699.00",
        "NILA-WIDE",
        True,
    ),
    (
        "Outerwear",
        "Kesar Quilted Jacket",
        "Lightweight quilted jacket with snap closure.",
        "5499.00",
        "KESAR-QUILT",
        False,
    ),
    (
        "Footwear",
        "Mira Leather Loafer",
        "Almond-toe loafer in soft burnished leather.",
        "4299.00",
        "MIRA-LOAFER",
        True,
    ),
    (
        "Bags",
        "Anvi Structured Tote",
        "Roomy tote with a padded laptop sleeve.",
        "6199.00",
        "ANVI-TOTE",
        False,
    ),
    (
        "Jewellery",
        "Tara Huggie Hoops",
        "Gold-plated huggie hoops for everyday wear.",
        "1299.00",
        "TARA-HOOP",
        False,
    ),
    (
        "Scarves & Wraps",
        "Dhara Silk Scarf",
        "Hand-rolled mulberry silk scarf.",
        "2199.00",
        "DHARA-SILK",
        False,
    ),
    (
        "Loungewear",
        "Ravi Ribbed Lounge Set",
        "Ribbed knit tee and trouser set.",
        "2999.00",
        "RAVI-LOUNGE",
        True,
    ),
    (
        "Accessories",
        "Bela Woven Belt",
        "Woven leather belt with a brushed buckle.",
        "1599.00",
        "BELA-BELT",
        False,
    ),
]

USERS: list[tuple[str, str, UserRole]] = [
    ("priya.menon", "Priya Menon", UserRole.STAFF),
    ("arjun.rao", "Arjun Rao", UserRole.STAFF),
    ("neha.kapoor", "Neha Kapoor", UserRole.CUSTOMER),
    ("rohit.sharma", "Rohit Sharma", UserRole.CUSTOMER),
    ("aisha.khan", "Aisha Khan", UserRole.CUSTOMER),
    ("vikram.das", "Vikram Das", UserRole.CUSTOMER),
    ("meera.nair", "Meera Nair", UserRole.CUSTOMER),
    ("sanjay.gupta", "Sanjay Gupta", UserRole.CUSTOMER),
    ("divya.iyer", "Divya Iyer", UserRole.CUSTOMER),
    ("kabir.singh", "Kabir Singh", UserRole.CUSTOMER),
]

VARIANT_OPTIONS: list[tuple[str, str]] = [
    ("Black", "S"),
    ("Ivory", "M"),
    ("Indigo", "L"),
    ("Olive", "M"),
    ("Rust", "S"),
]

DEMO_USER_PASSWORD = "demo-password-123"
PRODUCTION_REFUSAL = (
    "Demo data is never seeded in production; "
    "run python -m app.commands.bootstrap instead"
)
DEMO_EMAIL_DOMAIN = "example.com"


def _image_url(seed: str, index: int) -> str:
    return f"https://picsum.photos/seed/{seed.lower()}-{index}/800/1000"


async def _count(session, model) -> int:
    return int(await session.scalar(select(func.count()).select_from(model)) or 0)


async def seed_demo(session: AsyncSession, tenant: Tenant) -> None:
    """Fill a non-production tenant with a demo catalogue, users and offers."""
    if get_settings().is_production:
        raise RuntimeError(PRODUCTION_REFUSAL)

    categories_service = CategoryService(session, tenant.id)
    by_name: dict[str, Category] = {}

    existing_categories = (
        await session.scalars(select(Category).where(Category.tenant_id == tenant.id))
    ).all()
    by_name.update({category.name: category for category in existing_categories})

    created_categories = 0
    for name, description in CATEGORIES:
        if name in by_name:
            continue
        by_name[name] = await categories_service.create(
            CategoryCreate(name=name, description=description, status=CatalogueStatus.ACTIVE)
        )
        created_categories += 1
    print(f"Categories: +{created_categories} (total {len(by_name)})")

    products_service = ProductService(session, tenant.id)
    existing_products = {
        product.name: product
        for product in (
            await session.scalars(select(Product).where(Product.tenant_id == tenant.id))
        ).all()
    }

    created_products = 0
    for category_name, name, blurb, _price, sku, featured in PRODUCTS:
        if name in existing_products:
            continue

        seed_key = sku.lower()
        existing_products[name] = await products_service.create(
            ProductCreate(
                category_id=by_name[category_name].id,
                name=name,
                short_description=blurb,
                description=(
                    f"{blurb} Cut and finished in small batches. "
                    "Model is 5'8\" and wears a size S."
                ),
                brand=PRODUCT_BRAND,
                status=CatalogueStatus.ACTIVE,
                is_featured=featured,
                seo_title=f"{name} | {PRODUCT_BRAND}",
                seo_description=blurb,
                images=[
                    ProductImageCreate(
                        url=_image_url(seed_key, 1),
                        alt_text=f"{name}, front view",
                        sort_order=0,
                        is_primary=True,
                    ),
                    ProductImageCreate(
                        url=_image_url(seed_key, 2),
                        alt_text=f"{name}, detail view",
                        sort_order=1,
                        is_primary=False,
                    ),
                ],
            )
        )
        created_products += 1
    print(f"Products: +{created_products} (total {len(existing_products)})")

    variants_service = VariantService(session, tenant.id)
    existing_skus = set(
        (
            await session.scalars(
                select(ProductVariant.sku).where(ProductVariant.tenant_id == tenant.id)
            )
        ).all()
    )

    created_variants = 0
    for index, (_category, name, _blurb, price, sku, _featured) in enumerate(PRODUCTS):
        full_sku = f"{sku}-STD"
        if full_sku in existing_skus:
            continue

        colour, size = VARIANT_OPTIONS[index % len(VARIANT_OPTIONS)]
        await variants_service.create(
            existing_products[name].id,
            VariantCreate(
                sku=full_sku,
                name=f"{size} / {colour}",
                price=Decimal(price),
                status=CatalogueStatus.ACTIVE,
                options=[
                    VariantOptionValue(name="Color", value=colour),
                    VariantOptionValue(name="Size", value=size),
                ],
                initial_quantity=25,
                low_stock_threshold=5,
            ),
        )
        created_variants += 1
    print(f"Variants: +{created_variants}")

    user_service = UserService(session)
    created_users = 0
    for index, (local_part, name, role) in enumerate(USERS, start=1):
        _user, created = await user_service.create(
            role=role,
            tenant_id=tenant.id,
            email=f"{local_part}@{DEMO_EMAIL_DOMAIN}",
            phone=f"+9198100000{index:02d}",
            name=name,
            password=DEMO_USER_PASSWORD,
        )
        created_users += int(created)
    print(f"Users: +{created_users} demo users (plus the tenant admin)")

    await seed_demo_offers(session, tenant)

    print()
    print(f"  categories       {await _count(session, Category):>3}")
    print(f"  products         {await _count(session, Product):>3}")
    print(f"  variants         {await _count(session, ProductVariant):>3}")
    print(f"  inventory rows   {await _count(session, InventoryItem):>3}")
    print(f"  users            {await _count(session, User):>3}")


async def seed() -> None:
    """Bootstrap the seed tenant, then add demo data; never in production."""
    settings = get_settings()
    if settings.is_production:
        raise RuntimeError(PRODUCTION_REFUSAL)

    async with AsyncSessionLocal() as session:
        tenant = await bootstrap_tenant(session, settings)
        await seed_demo(session, tenant)

    await dispose_engine()
    print()
    print("Seed completed successfully.")


def main() -> None:
    asyncio.run(seed())


if __name__ == "__main__":
    main()
