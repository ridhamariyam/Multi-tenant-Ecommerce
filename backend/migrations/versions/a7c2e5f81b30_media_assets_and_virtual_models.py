"""Media assets and the shared virtual-model library (Phase 7).

1. `media_assets`: every stored file, brand-owned (tenant_id) or, for the
   character library only, platform-owned (tenant_id NULL).
2. `virtual_models` and `virtual_model_poses`: the shared character library.
   No tenant_id by design.
3. `product_images` gains `source` (UPLOAD for every existing row) and an
   optional `media_asset_id`, so approved AI images can join a product's
   gallery without ever replacing the brand's original photos. A composite
   unique (tenant_id, id) lets other tables reference images per brand.

Only additions; existing rows are untouched apart from the defaulted column.

Revision ID: a7c2e5f81b30
Revises: 9b3f1c2d7e4a
Create Date: 2026-11-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a7c2e5f81b30"
down_revision: Union[str, Sequence[str], None] = "9b3f1c2d7e4a"
branch_labels = None
depends_on = None

KINDS = "('PRODUCT_ORIGINAL', 'AI_GENERATED', 'STOREFRONT', 'THUMBNAIL', 'VIRTUAL_MODEL')"


def upgrade() -> None:
    op.create_table(
        "media_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE", name="fk_media_assets_tenant_id_tenants"),
            nullable=True,
        ),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("visibility", sa.String(10), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("url", sa.String(2048), nullable=True),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("width", sa.Integer, nullable=True),
        sa.Column("height", sa.Integer, nullable=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("output_index", sa.Integer, nullable=True),
        sa.Column("source_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("review_status", sa.String(10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_media_assets"),
        sa.UniqueConstraint("storage_key", name="uq_media_assets_storage_key"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_media_assets_tenant_id_id"),
        sa.CheckConstraint(f"kind IN {KINDS}", name=op.f("ck_media_assets_kind_valid")),
        sa.CheckConstraint("visibility IN ('PUBLIC', 'PRIVATE')", name=op.f("ck_media_assets_visibility_valid")),
        sa.CheckConstraint(
            "review_status IS NULL OR review_status IN ('PENDING', 'APPROVED', 'REJECTED')",
            name=op.f("ck_media_assets_review_status_valid"),
        ),
        sa.CheckConstraint(
            "(tenant_id IS NULL) = (kind = 'VIRTUAL_MODEL')", name=op.f("ck_media_assets_owner_matches_kind")
        ),
        sa.CheckConstraint("visibility = 'PRIVATE' OR url IS NOT NULL", name=op.f("ck_media_assets_public_has_url")),
        sa.CheckConstraint(
            "(kind = 'AI_GENERATED') = (review_status IS NOT NULL)", name=op.f("ck_media_assets_review_only_for_ai")
        ),
        sa.CheckConstraint("size_bytes > 0", name=op.f("ck_media_assets_size_positive")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["products.tenant_id", "products.id"],
            name="fk_media_assets_tenant_product_products",
            ondelete="SET NULL (product_id)",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_asset_id"],
            ["media_assets.tenant_id", "media_assets.id"],
            name="fk_media_assets_tenant_source_media_assets",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_media_assets_tenant_id_kind", "media_assets", ["tenant_id", "kind"])
    op.create_index("ix_media_assets_tenant_id_product_id", "media_assets", ["tenant_id", "product_id"])
    op.create_index("ix_media_assets_job_id", "media_assets", ["job_id"])

    op.create_table(
        "virtual_models",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("gender_presentation", sa.String(20), nullable=False),
        sa.Column("model_type", sa.String(20), nullable=False),
        sa.Column("available_categories", postgresql.ARRAY(sa.String(50)), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("supported_garments", postgresql.ARRAY(sa.String(50)), server_default=sa.text("'{}'"), nullable=False),
        sa.Column(
            "image_asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("media_assets.id", ondelete="RESTRICT", name="fk_virtual_models_image_asset_id_media_assets"),
            nullable=True,
        ),
        sa.Column("license_note", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_virtual_models"),
        sa.UniqueConstraint("name", name="uq_virtual_models_name"),
        sa.CheckConstraint(
            "gender_presentation IN ('FEMININE', 'MASCULINE', 'ANDROGYNOUS')",
            name=op.f("ck_virtual_models_gender_valid"),
        ),
        sa.CheckConstraint(
            "model_type IN ('FULL_BODY', 'UPPER_BODY', 'LOWER_BODY')", name=op.f("ck_virtual_models_model_type_valid")
        ),
        sa.CheckConstraint(
            "NOT is_active OR image_asset_id IS NOT NULL", name=op.f("ck_virtual_models_active_has_image")
        ),
    )
    op.create_index("ix_virtual_models_is_active", "virtual_models", ["is_active"])

    op.create_table(
        "virtual_model_poses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "virtual_model_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("virtual_models.id", ondelete="CASCADE", name="fk_virtual_model_poses_virtual_model_id_virtual_models"),
            nullable=False,
        ),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("media_assets.id", ondelete="RESTRICT", name="fk_virtual_model_poses_asset_id_media_assets"),
            nullable=False,
        ),
        sa.Column("label", sa.String(100), nullable=True),
        sa.Column("sort_order", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_virtual_model_poses"),
        sa.UniqueConstraint("asset_id", name="uq_virtual_model_poses_asset_id"),
        sa.CheckConstraint("sort_order >= 0", name=op.f("ck_virtual_model_poses_sort_order_valid")),
    )
    op.create_index("ix_virtual_model_poses_virtual_model_id", "virtual_model_poses", ["virtual_model_id"])

    op.add_column(
        "product_images",
        sa.Column("source", sa.String(20), server_default=sa.text("'UPLOAD'"), nullable=False),
    )
    op.add_column("product_images", sa.Column("media_asset_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_unique_constraint("uq_product_images_tenant_id_id", "product_images", ["tenant_id", "id"])
    op.create_foreign_key(
        "fk_product_images_tenant_media_asset_media_assets",
        "product_images",
        "media_assets",
        ["tenant_id", "media_asset_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        op.f("ck_product_images_image_source_valid"), "product_images", "source IN ('UPLOAD', 'AI_GENERATED')"
    )
    op.create_check_constraint(
        op.f("ck_product_images_ai_image_has_asset"),
        "product_images",
        "source = 'UPLOAD' OR media_asset_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_product_images_ai_image_has_asset"), "product_images", type_="check")
    op.drop_constraint(op.f("ck_product_images_image_source_valid"), "product_images", type_="check")
    op.drop_constraint("fk_product_images_tenant_media_asset_media_assets", "product_images", type_="foreignkey")
    op.drop_constraint("uq_product_images_tenant_id_id", "product_images", type_="unique")
    # AI images in a gallery have no meaning without their assets.
    op.execute("DELETE FROM product_images WHERE source <> 'UPLOAD'")
    op.drop_column("product_images", "media_asset_id")
    op.drop_column("product_images", "source")
    op.drop_table("virtual_model_poses")
    op.drop_table("virtual_models")
    op.drop_table("media_assets")
