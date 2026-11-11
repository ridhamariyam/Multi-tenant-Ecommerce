"""sub-categories and product filter attributes

* `categories.parent_id` makes a category a sub-category of another one in
  the same tenant. NULL keeps every existing category top-level.
* `products.fabric`, `occasion`, `sleeve` and `neckline` are nullable
  free-text attributes the storefront filters by. Existing products simply
  have none set.

Revision ID: 529df9259e68
Revises: 27f827e24c4a
Create Date: 2026-10-01 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "529df9259e68"
down_revision: Union[str, Sequence[str], None] = "4b7d9a21c63f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PRODUCT_ATTRIBUTES = ("fabric", "occasion", "sleeve", "neckline")


def upgrade() -> None:
    """Upgrade schema."""
    # ---------------------------------------------------------- sub-categories
    op.add_column("categories", sa.Column("parent_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_categories_tenant_parent_categories",
        "categories",
        "categories",
        ["tenant_id", "parent_id"],
        ["tenant_id", "id"],
        ondelete="NO ACTION",
    )
    op.create_check_constraint(
        op.f("ck_categories_parent_not_self"),
        "categories",
        "parent_id IS NULL OR parent_id <> id",
    )
    op.create_index(
        "ix_categories_tenant_id_parent_id",
        "categories",
        ["tenant_id", "parent_id"],
        unique=False,
    )

    # ------------------------------------------------ product filter attributes
    for attribute in PRODUCT_ATTRIBUTES:
        op.add_column(
            "products", sa.Column(attribute, sa.String(length=100), nullable=True)
        )
        op.create_index(
            f"ix_products_tenant_id_{attribute}",
            "products",
            ["tenant_id", attribute],
            unique=False,
        )


def downgrade() -> None:
    """Downgrade schema."""
    has_feature_data = op.get_bind().execute(sa.text("""
        SELECT EXISTS (SELECT 1 FROM categories WHERE parent_id IS NOT NULL)
            OR EXISTS (SELECT 1 FROM products WHERE fabric IS NOT NULL OR occasion IS NOT NULL
                       OR sleeve IS NOT NULL OR neckline IS NOT NULL)
    """)).scalar_one()
    if has_feature_data:
        raise RuntimeError("Cannot remove category hierarchy or populated product filters")
    for attribute in reversed(PRODUCT_ATTRIBUTES):
        op.drop_index(f"ix_products_tenant_id_{attribute}", table_name="products")
        op.drop_column("products", attribute)

    op.drop_index("ix_categories_tenant_id_parent_id", table_name="categories")
    op.drop_constraint(
        op.f("ck_categories_parent_not_self"), "categories", type_="check"
    )
    op.drop_constraint(
        "fk_categories_tenant_parent_categories", "categories", type_="foreignkey"
    )
    op.drop_column("categories", "parent_id")
