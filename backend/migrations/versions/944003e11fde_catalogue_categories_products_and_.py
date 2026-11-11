"""catalogue categories products and variants"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '944003e11fde'
down_revision: Union[str, Sequence[str], None] = '321641888632'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('categories',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('slug', sa.String(length=100), nullable=False),
    sa.Column('description', sa.String(length=2000), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('length(trim(name)) > 0', name=op.f('ck_categories_name_not_blank')),
    sa.CheckConstraint('slug = lower(slug)', name=op.f('ck_categories_slug_is_lowercase')),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_categories_tenant_id_tenants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_categories')),
    sa.UniqueConstraint('tenant_id', 'id', name='uq_categories_tenant_id_id'),
    sa.UniqueConstraint('tenant_id', 'slug', name='uq_categories_tenant_slug')
    )
    op.create_table('products',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('category_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('slug', sa.String(length=100), nullable=False),
    sa.Column('description', sa.String(length=2000), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('DRAFT', 'ACTIVE', 'ARCHIVED')", name=op.f('ck_products_status_valid')),
    sa.CheckConstraint('length(trim(name)) > 0', name=op.f('ck_products_name_not_blank')),
    sa.CheckConstraint('slug = lower(slug)', name=op.f('ck_products_slug_is_lowercase')),
    sa.ForeignKeyConstraint(['tenant_id', 'category_id'], ['categories.tenant_id', 'categories.id'], name='fk_products_tenant_category_categories', ondelete='NO ACTION'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_products_tenant_id_tenants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_products')),
    sa.UniqueConstraint('tenant_id', 'id', name='uq_products_tenant_id_id'),
    sa.UniqueConstraint('tenant_id', 'slug', name='uq_products_tenant_slug')
    )
    op.create_index('ix_products_tenant_id_category_id', 'products', ['tenant_id', 'category_id'], unique=False)
    op.create_table('product_variants',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('product_id', sa.UUID(), nullable=False),
    sa.Column('sku', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('price', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('DRAFT', 'ACTIVE', 'ARCHIVED')", name=op.f('ck_product_variants_status_valid')),
    sa.CheckConstraint('length(trim(name)) > 0', name=op.f('ck_product_variants_name_not_blank')),
    sa.CheckConstraint('price >= 0', name=op.f('ck_product_variants_price_not_negative')),
    sa.CheckConstraint('sku = upper(sku)', name=op.f('ck_product_variants_sku_is_uppercase')),
    sa.ForeignKeyConstraint(['tenant_id', 'product_id'], ['products.tenant_id', 'products.id'], name='fk_product_variants_tenant_product_products', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_product_variants_tenant_id_tenants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_product_variants')),
    sa.UniqueConstraint('tenant_id', 'sku', name='uq_product_variants_tenant_sku')
    )
    op.create_index('ix_product_variants_tenant_id_product_id', 'product_variants', ['tenant_id', 'product_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_product_variants_tenant_id_product_id', table_name='product_variants')
    op.drop_table('product_variants')
    op.drop_index('ix_products_tenant_id_category_id', table_name='products')
    op.drop_table('products')
    op.drop_table('categories')
