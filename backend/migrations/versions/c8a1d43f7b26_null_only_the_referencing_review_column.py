"""null only the referencing review column on delete

Revision ID: c8a1d43f7b26
Revises: 312bdf33cd6b
Create Date: 2026-09-05 09:20:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c8a1d43f7b26'
down_revision: Union[str, Sequence[str], None] = '312bdf33cd6b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# A plain ON DELETE SET NULL on a composite key nulls every referencing column.
# reviews.tenant_id is NOT NULL, so deleting a product or a user aborted instead
# of leaving the review behind. Naming the column restores the intent.
_KEYS = (
    ('fk_reviews_tenant_product_products', 'products', 'product_id'),
    ('fk_reviews_tenant_user_users', 'users', 'user_id'),
    ('fk_reviews_tenant_order_orders', 'orders', 'order_id'),
)


def upgrade() -> None:
    """Upgrade schema."""
    for name, referred, column in _KEYS:
        op.drop_constraint(name, 'reviews', type_='foreignkey')
        op.create_foreign_key(
            name,
            'reviews',
            referred,
            ['tenant_id', column],
            ['tenant_id', 'id'],
            ondelete=f'SET NULL ({column})',
        )


def downgrade() -> None:
    """Downgrade schema."""
    for name, referred, column in _KEYS:
        op.drop_constraint(name, 'reviews', type_='foreignkey')
        op.create_foreign_key(
            name,
            'reviews',
            referred,
            ['tenant_id', column],
            ['tenant_id', 'id'],
            ondelete='SET NULL',
        )
