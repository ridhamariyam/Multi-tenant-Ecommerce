"""Seed the CliQ. dummy catalogue used by the "Try the Look" runway homepage.

Eight placeholder products built from the runway's product cut-outs. Each
image is downloaded once and stored in this store's own media storage, so
the storefront serves it from the API host like any staff upload.

Idempotent: a product whose slug already exists is left untouched. Never
runs in production.

    docker cp backend/app/commands/seed_cliq_demo.py tws_ec2_api:/app/app/commands/
    docker exec tws_ec2_api python -m app.commands.seed_cliq_demo
"""

from __future__ import annotations

import asyncio
import urllib.request
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select

from app.catalogue.constants import CatalogueStatus
from app.catalogue.models import Category, Product
from app.catalogue.schemas import (
    CategoryCreate,
    ProductCreate,
    ProductImageCreate,
    VariantCreate,
    VariantOptionValue,
)
from app.catalogue.service import CategoryService, ProductService, VariantService
from app.catalogue.uploads import store_image
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal, dispose_engine
from app.tenants.models import Tenant

BRAND = "CliQ."
ASSETS = "https://reel-ref-try-the-look.vercel.app/assets/"
APPAREL_SIZES = ["S", "M", "L", "XL"]
SHOE_SIZES = ["40", "41", "42", "43", "44", "45", "46"]
STOCK_PER_SIZE = 25


@dataclass(frozen=True)
class DemoProduct:
    slug: str
    name: str
    category: str
    blurb: str
    price: str
    image: str
    sizes: list[str]
    sku: str
    featured: bool = False


PRODUCTS: list[DemoProduct] = [
    DemoProduct("dune-low-sneaker", "Dune Low Sneaker", "Footwear",
                "Low-top sneaker in sand and cream with tonal panels.", "6999.00",
                "source-tatum-5-orbit-copy.webp", SHOE_SIZES, "DUNE-LOW", True),
    DemoProduct("court-classic-sneaker", "Court Classic Sneaker", "Footwear",
                "White leather court sneaker with a printed overlay and contrast collar.", "7499.00",
                "source-tatum-5-orbit.webp", SHOE_SIZES, "COURT-CLASSIC", True),
    DemoProduct("noir-leather-sneaker", "Noir Leather Sneaker", "Footwear",
                "All-black leather low-top on a clean white sole.", "6499.00",
                "source-air-jordan-12-retro-copy.webp", SHOE_SIZES, "NOIR-LEATHER"),
    DemoProduct("reign-graphic-tee", "Reign Graphic Tee", "Tops",
                "Heavyweight black jersey tee with a rib collar and chest graphic.", "1499.00",
                "source-tshirt.webp", APPAREL_SIZES, "REIGN-TEE", True),
    DemoProduct("sand-crew-sweatshirt", "Sand Crew Sweatshirt", "Tops",
                "Brushed-back crew sweatshirt in warm sand.", "2499.00",
                "source-sweatshirt.webp", APPAREL_SIZES, "SAND-CREW"),
    DemoProduct("varsity-hoodie", "Varsity Hoodie", "Outerwear",
                "Bottle-green hoodie with cream varsity lettering.", "2999.00",
                "source-sweatshirt-plus.webp", APPAREL_SIZES, "VARSITY-HOOD"),
    DemoProduct("statement-hoodie", "Statement Hoodie", "Outerwear",
                "Heather-grey hoodie with a bold slogan print.", "2799.00",
                "source-hoodie.webp", APPAREL_SIZES, "STATEMENT-HOOD"),
    DemoProduct("star-graphic-hoodie", "Star Graphic Hoodie", "Outerwear",
                "Black hoodie with a soft grey star graphic.", "2799.00",
                "source-hoodie-black.webp", APPAREL_SIZES, "STAR-HOOD", True),
]

CATEGORY_DESCRIPTIONS = {
    "Footwear": "Sneakers and everyday shoes.",
    "Tops": "Tees and sweatshirts.",
    "Outerwear": "Hoodies and layers.",
}


def _download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "cliq-seed/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - fixed https host
        return response.read()


async def seed_cliq_demo() -> None:
    if get_settings().is_production:
        raise RuntimeError("The CliQ. dummy catalogue is never seeded in production")

    async with AsyncSessionLocal() as session:
        tenants = (await session.scalars(select(Tenant))).all()
        if len(tenants) != 1:
            raise RuntimeError(f"Expected exactly one store, found {len(tenants)}")
        tenant = tenants[0]

        categories = {
            c.name: c
            for c in (
                await session.scalars(
                    select(Category).where(
                        Category.tenant_id == tenant.id, Category.status == CatalogueStatus.ACTIVE.value
                    )
                )
            ).all()
        }
        category_service = CategoryService(session, tenant.id)
        for name, description in CATEGORY_DESCRIPTIONS.items():
            if name not in categories:
                categories[name] = await category_service.create(
                    CategoryCreate(name=name, description=description, status=CatalogueStatus.ACTIVE)
                )

        existing = set(
            (await session.scalars(select(Product.slug).where(Product.tenant_id == tenant.id))).all()
        )
        products = ProductService(session, tenant.id)
        variants = VariantService(session, tenant.id)

        created = 0
        for demo in PRODUCTS:
            if demo.slug in existing:
                print(f"skip   {demo.slug} (already exists)")
                continue

            image_url = await store_image(tenant.id, "image/webp", _download(ASSETS + demo.image))
            product = await products.create(
                ProductCreate(
                    category_id=categories[demo.category].id,
                    name=demo.name,
                    slug=demo.slug,
                    short_description=demo.blurb,
                    description=f"{demo.blurb} Placeholder product for the CliQ. runway.",
                    brand=BRAND,
                    status=CatalogueStatus.ACTIVE,
                    is_featured=demo.featured,
                    seo_title=f"{demo.name} | {BRAND}",
                    seo_description=demo.blurb,
                    images=[ProductImageCreate(url=image_url, alt_text=demo.name, sort_order=0, is_primary=True)],
                )
            )
            for size in demo.sizes:
                await variants.create(
                    product.id,
                    VariantCreate(
                        sku=f"CLIQ-{demo.sku}-{size}",
                        name=size,
                        price=Decimal(demo.price),
                        status=CatalogueStatus.ACTIVE,
                        options=[VariantOptionValue(name="Size", value=size)],
                        initial_quantity=STOCK_PER_SIZE,
                        low_stock_threshold=5,
                    ),
                )
            created += 1
            print(f"create {demo.slug} ({len(demo.sizes)} sizes)")

    await dispose_engine()
    print(f"Done: {created} created, {len(PRODUCTS) - created} skipped.")


def main() -> None:
    asyncio.run(seed_cliq_demo())


if __name__ == "__main__":
    main()
