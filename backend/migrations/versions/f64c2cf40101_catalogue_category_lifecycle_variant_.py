"""catalogue: category lifecycle, variant options, inventory

Revision ID: f64c2cf40101
Revises: b7d41f0ac592
Create Date: 2026-08-21 20:57:26.205914

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f64c2cf40101'
down_revision: Union[str, Sequence[str], None] = 'b7d41f0ac592'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Child tables key on (tenant_id, id), so the target of those composite
    # foreign keys has to exist before the tables that reference it.
    op.create_unique_constraint(
        'uq_product_variants_tenant_id_id', 'product_variants', ['tenant_id', 'id']
    )

    op.create_table('product_options',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('product_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=60), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('length(trim(name)) > 0', name=op.f('ck_product_options_name_not_blank')),
    sa.CheckConstraint('position >= 0', name=op.f('ck_product_options_position_not_negative')),
    sa.ForeignKeyConstraint(['tenant_id', 'product_id'], ['products.tenant_id', 'products.id'], name='fk_product_options_tenant_product_products', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_product_options_tenant_id_tenants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_product_options')),
    sa.UniqueConstraint('tenant_id', 'id', name='uq_product_options_tenant_id_id'),
    sa.UniqueConstraint('tenant_id', 'product_id', 'name', name='uq_product_options_tenant_product_name')
    )
    op.create_index('ix_product_options_tenant_id_product_id', 'product_options', ['tenant_id', 'product_id'], unique=False)
    op.create_table('inventory_items',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('variant_id', sa.UUID(), nullable=False),
    sa.Column('available_quantity', sa.Integer(), nullable=False),
    sa.Column('reserved_quantity', sa.Integer(), nullable=False),
    sa.Column('low_stock_threshold', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('available_quantity >= 0', name=op.f('ck_inventory_items_available_not_negative')),
    sa.CheckConstraint('low_stock_threshold >= 0', name=op.f('ck_inventory_items_threshold_not_negative')),
    sa.CheckConstraint('reserved_quantity <= available_quantity', name=op.f('ck_inventory_items_reserved_within_available')),
    sa.CheckConstraint('reserved_quantity >= 0', name=op.f('ck_inventory_items_reserved_not_negative')),
    sa.ForeignKeyConstraint(['tenant_id', 'variant_id'], ['product_variants.tenant_id', 'product_variants.id'], name='fk_inventory_items_tenant_variant_product_variants', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_inventory_items_tenant_id_tenants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_inventory_items')),
    sa.UniqueConstraint('tenant_id', 'variant_id', name='uq_inventory_items_tenant_variant')
    )
    op.create_table('inventory_movements',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('variant_id', sa.UUID(), nullable=False),
    sa.Column('delta', sa.Integer(), nullable=False),
    sa.Column('reason', sa.String(length=20), nullable=False),
    sa.Column('reference', sa.String(length=120), nullable=True),
    sa.Column('note', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("reason IN ('INITIAL', 'ADJUSTMENT', 'RESTOCK', 'RESERVATION', 'RELEASE', 'FULFILLMENT')", name=op.f('ck_inventory_movements_reason_valid')),
    sa.ForeignKeyConstraint(['tenant_id', 'variant_id'], ['product_variants.tenant_id', 'product_variants.id'], name='fk_inventory_movements_tenant_variant_product_variants', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_inventory_movements_tenant_id_tenants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_inventory_movements'))
    )
    op.create_index('ix_inventory_movements_tenant_id_variant_id_created_at', 'inventory_movements', ['tenant_id', 'variant_id', 'created_at'], unique=False)
    op.create_table('product_variant_options',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('variant_id', sa.UUID(), nullable=False),
    sa.Column('option_id', sa.UUID(), nullable=False),
    sa.Column('value', sa.String(length=100), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('length(trim(value)) > 0', name=op.f('ck_product_variant_options_value_not_blank')),
    sa.ForeignKeyConstraint(['tenant_id', 'option_id'], ['product_options.tenant_id', 'product_options.id'], name='fk_product_variant_options_tenant_option_product_options', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id', 'variant_id'], ['product_variants.tenant_id', 'product_variants.id'], name='fk_product_variant_options_tenant_variant_product_variants', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_product_variant_options_tenant_id_tenants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_product_variant_options')),
    sa.UniqueConstraint('tenant_id', 'variant_id', 'option_id', name='uq_product_variant_options_tenant_variant_option')
    )
    op.create_index('ix_product_variant_options_tenant_id_option_id', 'product_variant_options', ['tenant_id', 'option_id'], unique=False)
    # Categories move from an is_active flag to the shared catalogue lifecycle.
    # Added nullable, backfilled from the old flag, then tightened -- existing
    # rows have no value and the model declares no server default.
    op.add_column('categories', sa.Column('status', sa.String(length=20), nullable=True))
    op.execute(
        "UPDATE categories SET status = CASE WHEN is_active THEN 'ACTIVE' ELSE 'DRAFT' END"
    )
    op.alter_column('categories', 'status', nullable=False)
    op.create_index('ix_categories_tenant_id_status', 'categories', ['tenant_id', 'status'], unique=False)
    op.create_check_constraint(op.f('ck_categories_status_valid'), 'categories', "status IN ('DRAFT', 'ACTIVE', 'ARCHIVED')")
    op.drop_column('categories', 'is_active')

    # Existing data may already carry two primary images for one product, which
    # is exactly the bug this index closes. Demote the extras first, keeping the
    # lowest sort_order as the winner, or the index cannot be built.
    op.execute(
        """
        UPDATE product_images AS pi
           SET is_primary = false
         WHERE pi.is_primary
           AND pi.id <> (
                 SELECT keep.id
                   FROM product_images AS keep
                  WHERE keep.tenant_id = pi.tenant_id
                    AND keep.product_id = pi.product_id
                    AND keep.is_primary
                  ORDER BY keep.sort_order, keep.created_at, keep.id
                  LIMIT 1
               )
        """
    )
    op.create_index('uq_product_images_one_primary_per_product', 'product_images', ['tenant_id', 'product_id'], unique=True, postgresql_where=sa.text('is_primary'))

    # Every existing variant needs an inventory row so stock operations never
    # have to cope with a missing record. They open at zero.
    op.execute(
        """
        INSERT INTO inventory_items
              (id, tenant_id, variant_id, available_quantity,
               reserved_quantity, low_stock_threshold, created_at, updated_at)
        SELECT gen_random_uuid(), v.tenant_id, v.id, 0, 0, 0, now(), now()
          FROM product_variants AS v
        """
    )
    op.create_index('ix_products_tenant_id_brand', 'products', ['tenant_id', 'brand'], unique=False)
    op.create_index('ix_products_tenant_id_is_featured', 'products', ['tenant_id', 'is_featured'], unique=False)
    op.create_index('ix_products_tenant_id_status', 'products', ['tenant_id', 'status'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index('ix_products_tenant_id_status', table_name='products')
    op.drop_index('ix_products_tenant_id_is_featured', table_name='products')
    op.drop_index('ix_products_tenant_id_brand', table_name='products')
    op.drop_index('uq_product_images_one_primary_per_product', table_name='product_images', postgresql_where=sa.text('is_primary'))
    op.add_column('categories', sa.Column('is_active', sa.BOOLEAN(), autoincrement=False, nullable=True))
    op.execute("UPDATE categories SET is_active = (status = 'ACTIVE')")
    op.alter_column('categories', 'is_active', nullable=False)
    op.drop_constraint(op.f('ck_categories_status_valid'), 'categories', type_='check')
    op.drop_index('ix_categories_tenant_id_status', table_name='categories')
    op.drop_column('categories', 'status')
    op.drop_index('ix_product_variant_options_tenant_id_option_id', table_name='product_variant_options')
    op.drop_table('product_variant_options')
    op.drop_index('ix_inventory_movements_tenant_id_variant_id_created_at', table_name='inventory_movements')
    op.drop_table('inventory_movements')
    op.drop_table('inventory_items')
    op.drop_index('ix_product_options_tenant_id_product_id', table_name='product_options')
    op.drop_table('product_options')

    # Last: the composite foreign keys above depend on this constraint.
    op.drop_constraint(
        'uq_product_variants_tenant_id_id', 'product_variants', type_='unique'
    )
    # ### end Alembic commands ###
