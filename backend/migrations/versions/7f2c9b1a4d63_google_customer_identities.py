"""add tenant-scoped customer authentication identities

Revision ID: 7f2c9b1a4d63
Revises: 61b7e2c4a903
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "7f2c9b1a4d63"
down_revision: Union[str, Sequence[str], None] = "61b7e2c4a903"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("uq_users_tenant_email", "users", type_="unique")
    op.create_index(
        "uq_users_tenant_staff_email",
        "users",
        ["tenant_id", "email"],
        unique=True,
        postgresql_where=sa.text("role IN ('ADMIN', 'STAFF')"),
    )

    op.create_table(
        "user_identities",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("subject", sa.String(length=320), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_user_identities_tenant_user",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "provider",
            "subject",
            name="uq_user_identities_tenant_provider_subject",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "user_id",
            "provider",
            name="uq_user_identities_tenant_user_provider",
        ),
    )
    op.create_index(
        "ix_user_identities_tenant_user",
        "user_identities",
        ["tenant_id", "user_id"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    duplicate_customer_email = connection.scalar(
        sa.text(
            "SELECT EXISTS ("
            "SELECT 1 FROM users "
            "WHERE email IS NOT NULL "
            "GROUP BY tenant_id, email HAVING count(*) > 1"
            ")"
        )
    )
    if duplicate_customer_email:
        raise RuntimeError(
            "Cannot restore tenant-wide email uniqueness while duplicate customer "
            "profile emails exist. Resolve duplicates before downgrading."
        )

    op.drop_index("ix_user_identities_tenant_user", table_name="user_identities")
    op.drop_table("user_identities")
    op.drop_index("uq_users_tenant_staff_email", table_name="users")
    op.create_unique_constraint(
        "uq_users_tenant_email", "users", ["tenant_id", "email"]
    )
