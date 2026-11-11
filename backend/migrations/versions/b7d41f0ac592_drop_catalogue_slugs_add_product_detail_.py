"""drop catalogue slugs, add product detail columns and product images

Brings the migration chain back in line with the ORM:

* `slug` is gone from the catalogue entirely -- products and categories are
  addressed by id.
* The product detail columns (short_description, brand, is_featured, seo_*)
  existed only on the model.
* `product_images` had no migration at all.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7d41f0ac592"
down_revision: Union[str, Sequence[str], None] = "e18d5c30ba47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------ slugs
    # Check constraints are named through the metadata naming convention, so
    # the short name is passed here and alembic expands it.
    op.drop_constraint("uq_categories_tenant_slug", "categories", type_="unique")
    op.drop_constraint("slug_is_lowercase", "categories", type_="check")
    op.drop_column("categories", "slug")

    op.drop_constraint("uq_products_tenant_slug", "products", type_="unique")
    op.drop_constraint("slug_is_lowercase", "products", type_="check")
    op.drop_column("products", "slug")

    # -------------------------------------------------- product detail columns
    op.add_column("products", sa.Column("short_description", sa.String(length=500), nullable=True))
    op.add_column("products", sa.Column("brand", sa.String(length=150), nullable=True))
    op.add_column("products", sa.Column("seo_title", sa.String(length=200), nullable=True))
    op.add_column("products", sa.Column("seo_description", sa.String(length=500), nullable=True))

    # Added nullable, backfilled, then tightened: existing rows have no value
    # and the model declares no server default.
    op.add_column("products", sa.Column("is_featured", sa.Boolean(), nullable=True))
    op.execute("UPDATE products SET is_featured = false WHERE is_featured IS NULL")
    op.alter_column("products", "is_featured", nullable=False)

    # ----------------------------------------------------------- product images
    op.create_table(
        "product_images",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("alt_text", sa.String(length=255), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(trim(url)) > 0", name=op.f("ck_product_images_image_url_not_blank")
        ),
        sa.CheckConstraint(
            "sort_order >= 0", name=op.f("ck_product_images_image_sort_order_valid")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["products.tenant_id", "products.id"],
            name="fk_product_images_tenant_product_products",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_product_images_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_images")),
    )
    op.create_index(
        "ix_product_images_tenant_id_product_id",
        "product_images",
        ["tenant_id", "product_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_product_images_tenant_id_product_id", table_name="product_images")
    op.drop_table("product_images")

    op.drop_column("products", "is_featured")
    op.drop_column("products", "seo_description")
    op.drop_column("products", "seo_title")
    op.drop_column("products", "brand")
    op.drop_column("products", "short_description")

    # Slugs come back as backfilled placeholders -- the original values are
    # gone, so uniqueness is restored from the row id rather than invented.
    op.add_column("products", sa.Column("slug", sa.String(length=100), nullable=True))
    op.execute("UPDATE products SET slug = 'product-' || replace(id::text, '-', '')")
    op.alter_column("products", "slug", nullable=False)
    op.create_check_constraint("slug_is_lowercase", "products", "slug = lower(slug)")
    op.create_unique_constraint("uq_products_tenant_slug", "products", ["tenant_id", "slug"])

    op.add_column("categories", sa.Column("slug", sa.String(length=100), nullable=True))
    op.execute("UPDATE categories SET slug = 'category-' || replace(id::text, '-', '')")
    op.alter_column("categories", "slug", nullable=False)
    op.create_check_constraint("slug_is_lowercase", "categories", "slug = lower(slug)")
    op.create_unique_constraint("uq_categories_tenant_slug", "categories", ["tenant_id", "slug"])
