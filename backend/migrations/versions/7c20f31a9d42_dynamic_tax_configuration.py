"""Dynamic, confirmed GST settings and immutable order tax snapshots.

Revision ID: 7c20f31a9d42
Revises: a8c3f1d9206b
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid


revision = "7c20f31a9d42"
down_revision = "a8c3f1d9206b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("gst_settings", sa.Column("registration_status", sa.String(30), nullable=False, server_default="UNKNOWN"))
    op.add_column("gst_settings", sa.Column("accounting_software", sa.String(30), nullable=False, server_default="NOT_DECIDED"))
    op.add_column("gst_settings", sa.Column("configuration_status", sa.String(30), nullable=False, server_default="DRAFT"))
    op.add_column("gst_settings", sa.Column("prices_include_gst", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("gst_settings", sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("gst_settings", sa.Column("confirmed_by_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("gst_settings", sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key("fk_gst_settings_updated_by_users", "gst_settings", "users", ["updated_by_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_gst_settings_confirmed_by_users", "gst_settings", "users", ["confirmed_by_id"], ["id"], ondelete="SET NULL")
    op.create_check_constraint(op.f("ck_gst_settings_gst_registration_status_valid"), "gst_settings", "registration_status IN ('REGISTERED', 'NOT_REGISTERED', 'APPLICATION_PENDING', 'UNKNOWN')")
    op.create_check_constraint(op.f("ck_gst_settings_gst_accounting_software_valid"), "gst_settings", "accounting_software IN ('TALLY', 'ZOHO_BOOKS', 'OTHER', 'NONE', 'NOT_DECIDED')")
    op.create_check_constraint(op.f("ck_gst_settings_gst_configuration_status_valid"), "gst_settings", "configuration_status IN ('DRAFT', 'PENDING_CA_CONFIRMATION', 'ACTIVE')")
    op.create_check_constraint(op.f("ck_gst_settings_gst_active_requires_confirmation"), "gst_settings", "configuration_status != 'ACTIVE' OR (confirmed_by_id IS NOT NULL AND confirmed_at IS NOT NULL)")

    op.add_column("tax_settings", sa.Column("confirmed_by_ca", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute("UPDATE tax_settings SET is_active = false WHERE is_active")
    op.alter_column("tax_settings", "is_active", existing_type=sa.Boolean(), server_default=sa.false())
    op.create_check_constraint(op.f("ck_tax_settings_tax_active_requires_confirmation"), "tax_settings", "NOT is_active OR confirmed_by_ca")

    op.create_table(
        "tax_rate_configurations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("hsn_code", sa.String(8), nullable=False),
        sa.Column("gst_rate", sa.Numeric(5, 2), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="PENDING"),
        sa.Column("ca_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_tax_rate_configurations_tenant_id_tenants", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id", "product_id"], ["products.tenant_id", "products.id"], name="fk_tax_rate_product_tenant", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "category_id"], ["categories.tenant_id", "categories.id"], name="fk_tax_rate_category_tenant", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], name="fk_tax_rate_configurations_created_by_id_users", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approved_by_id"], ["users.id"], name="fk_tax_rate_configurations_approved_by_id_users", ondelete="SET NULL"),
        sa.CheckConstraint("(product_id IS NOT NULL AND category_id IS NULL) OR (product_id IS NULL AND category_id IS NOT NULL)", name="tax_rate_one_target"),
        sa.CheckConstraint("gst_rate >= 0 AND gst_rate <= 100", name="tax_rate_in_range"),
        sa.CheckConstraint("status IN ('PENDING', 'ACTIVE', 'RETIRED')", name="tax_rate_status_valid"),
        sa.CheckConstraint("status != 'ACTIVE' OR (ca_confirmed AND approved_by_id IS NOT NULL AND approved_at IS NOT NULL)", name="tax_rate_active_needs_confirmation"),
        sa.CheckConstraint("hsn_code ~ '^[0-9]{4}([0-9]{2}){0,2}$'", name="tax_rate_hsn_valid"),
    )
    op.create_index("ix_tax_rate_tenant_product_effective", "tax_rate_configurations", ["tenant_id", "product_id", "effective_from"])
    op.create_index("ix_tax_rate_tenant_category_effective", "tax_rate_configurations", ["tenant_id", "category_id", "effective_from"])

    # Preserve complete legacy mappings as drafts; never activate rates that
    # have not been explicitly confirmed by the tenant's accountant.
    connection = op.get_bind()
    for row in connection.execute(sa.text(
        "SELECT tenant_id, id, hsn_code, gst_rate FROM categories "
        "WHERE hsn_code IS NOT NULL AND gst_rate IS NOT NULL "
        "AND hsn_code ~ '^[0-9]{4}([0-9]{2}){0,2}$'"
    )):
        connection.execute(sa.text(
            "INSERT INTO tax_rate_configurations "
            "(id, tenant_id, category_id, hsn_code, gst_rate, effective_from, status, ca_confirmed, created_at, updated_at) "
            "VALUES (:id, :tenant_id, :category_id, :hsn, :rate, CURRENT_DATE, 'PENDING', false, now(), now())"
        ), {"id": uuid.uuid4(), "tenant_id": row.tenant_id, "category_id": row.id, "hsn": row.hsn_code, "rate": row.gst_rate})
    for row in connection.execute(sa.text(
        "SELECT tenant_id, id, hsn_code, gst_rate FROM products "
        "WHERE hsn_code IS NOT NULL AND gst_rate IS NOT NULL "
        "AND hsn_code ~ '^[0-9]{4}([0-9]{2}){0,2}$'"
    )):
        connection.execute(sa.text(
            "INSERT INTO tax_rate_configurations "
            "(id, tenant_id, product_id, hsn_code, gst_rate, effective_from, status, ca_confirmed, created_at, updated_at) "
            "VALUES (:id, :tenant_id, :product_id, :hsn, :rate, CURRENT_DATE, 'PENDING', false, now(), now())"
        ), {"id": uuid.uuid4(), "tenant_id": row.tenant_id, "product_id": row.id, "hsn": row.hsn_code, "rate": row.gst_rate})

    op.add_column("orders", sa.Column("tax_included_amount", sa.Numeric(12, 2), nullable=False, server_default="0"))
    op.add_column("orders", sa.Column("seller_legal_name", sa.String(200), nullable=True))
    op.add_column("orders", sa.Column("seller_address", sa.String(500), nullable=True))
    op.add_column("orders", sa.Column("seller_state", sa.String(100), nullable=True))
    op.add_column("orders", sa.Column("seller_state_code", sa.String(2), nullable=True))
    op.add_column("orders", sa.Column("invoice_prefix", sa.String(20), nullable=True))
    op.add_column("orders", sa.Column("shipping_sac_code", sa.String(8), nullable=True))
    op.add_column("orders", sa.Column("charges_gst_rate", sa.Numeric(5, 2), nullable=True))
    op.add_column("orders", sa.Column("prices_include_gst", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("orders", sa.Column("gst_registration_status", sa.String(30), nullable=True))
    op.drop_constraint(op.f("ck_orders_total_matches_components"), "orders", type_="check")
    op.create_check_constraint(op.f("ck_orders_total_matches_components"), "orders", "total_amount = subtotal - discount_amount + shipping_amount + cod_fee + tax_amount - tax_included_amount")
    op.create_check_constraint(op.f("ck_orders_tax_included_valid"), "orders", "tax_included_amount >= 0 AND tax_included_amount <= tax_amount")

    op.add_column("order_items", sa.Column("tax_configuration_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_order_items_tax_configuration", "order_items", "tax_rate_configurations", ["tax_configuration_id"], ["id"], ondelete="RESTRICT")
    op.create_index("ix_order_items_tax_configuration_id", "order_items", ["tax_configuration_id"])


def downgrade() -> None:
    raise RuntimeError("GST configuration snapshots are historical financial records; downgrade requires a reviewed data-preserving migration")
