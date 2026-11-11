"""otp authentication and domain tenancy"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4f2a71b0e93"
down_revision: Union[str, Sequence[str], None] = "944003e11fde"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

E164 = r"phone ~ '^\+[1-9][0-9]{7,14}$'"


def upgrade() -> None:
    op.create_table(
        "tenant_domains",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
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
            "domain = lower(domain)", name=op.f("ck_tenant_domains_domain_is_lowercase")
        ),
        sa.CheckConstraint(
            "length(trim(domain)) > 0", name=op.f("ck_tenant_domains_domain_not_blank")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_tenant_domains_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenant_domains")),
        sa.UniqueConstraint("domain", name=op.f("uq_tenant_domains_domain")),
    )
    op.create_index(
        op.f("ix_tenant_domains_tenant_id"), "tenant_domains", ["tenant_id"], unique=False
    )

    op.execute(
        """
        INSERT INTO tenant_domains (id, tenant_id, domain, created_at, updated_at)
        SELECT gen_random_uuid(), id, lower(slug) || '.localhost', now(), now()
        FROM tenants
        """
    )

    op.create_table(
        "otp_requests",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("phone", sa.String(length=16), nullable=False),
        sa.Column("purpose", sa.String(length=20), nullable=False),
        sa.Column("otp_hash", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_otp_requests_attempts_not_negative")),
        sa.CheckConstraint(
            "purpose IN ('CUSTOMER_LOGIN', 'ADMIN_LOGIN')",
            name=op.f("ck_otp_requests_purpose_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_otp_requests_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_otp_requests_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_otp_requests")),
    )
    op.create_index(
        "ix_otp_requests_tenant_id_phone_purpose",
        "otp_requests",
        ["tenant_id", "phone", "purpose"],
        unique=False,
    )

    op.create_table(
        "admin_auth_challenges",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("otp_request_id", sa.UUID(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["otp_request_id"],
            ["otp_requests.id"],
            name=op.f("fk_admin_auth_challenges_otp_request_id_otp_requests"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_admin_auth_challenges_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_admin_auth_challenges_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_auth_challenges")),
    )
    op.create_index(
        op.f("ix_admin_auth_challenges_user_id"),
        "admin_auth_challenges",
        ["user_id"],
        unique=False,
    )

    op.drop_constraint(op.f("ck_users_role_matches_tenant_scope"), "users", type_="check")
    op.drop_constraint(op.f("ck_users_role_valid"), "users", type_="check")
    op.drop_constraint(op.f("ck_users_email_is_lowercase"), "users", type_="check")

    op.add_column("users", sa.Column("phone", sa.String(length=16), nullable=True))
    op.add_column("users", sa.Column("name", sa.String(length=150), nullable=True))
    op.add_column("users", sa.Column("status", sa.String(length=20), nullable=True))
    op.add_column(
        "users",
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    op.alter_column("users", "email", existing_type=sa.VARCHAR(length=255), nullable=True)
    op.alter_column(
        "users", "password_hash", existing_type=sa.VARCHAR(length=255), nullable=True
    )

    op.execute("DELETE FROM users WHERE tenant_id IS NULL")
    op.execute("UPDATE users SET role = 'ADMIN' WHERE role = 'TENANT_ADMIN'")
    op.execute("UPDATE users SET password_hash = NULL WHERE role = 'CUSTOMER'")
    op.execute("UPDATE users SET status = CASE WHEN is_active THEN 'ACTIVE' ELSE 'INACTIVE' END")

    op.alter_column("users", "status", existing_type=sa.String(length=20), nullable=False)
    op.alter_column("users", "is_verified", server_default=None)
    op.alter_column("users", "tenant_id", existing_type=sa.UUID(), nullable=False)
    op.alter_column(
        "users",
        "role",
        existing_type=sa.VARCHAR(length=50),
        type_=sa.String(length=20),
        existing_nullable=False,
    )

    op.create_index(op.f("ix_users_tenant_id"), "users", ["tenant_id"], unique=False)
    op.create_unique_constraint("uq_users_tenant_phone", "users", ["tenant_id", "phone"])
    op.drop_index("uq_users_platform_email", table_name="users")

    op.create_check_constraint(
        op.f("ck_users_role_valid"), "users", "role IN ('CUSTOMER', 'STAFF', 'ADMIN')"
    )
    op.create_check_constraint(
        op.f("ck_users_status_valid"), "users", "status IN ('ACTIVE', 'INACTIVE')"
    )
    op.create_check_constraint(
        op.f("ck_users_email_is_lowercase"), "users", "email IS NULL OR email = lower(email)"
    )
    op.create_check_constraint(
        op.f("ck_users_phone_is_e164"), "users", f"phone IS NULL OR {E164}"
    )
    op.create_check_constraint(
        op.f("ck_users_password_matches_role"),
        "users",
        "(role = 'CUSTOMER') = (password_hash IS NULL)",
    )

    op.add_column("refresh_tokens", sa.Column("tenant_id", sa.UUID(), nullable=True))
    op.execute(
        """
        UPDATE refresh_tokens
        SET tenant_id = users.tenant_id
        FROM users
        WHERE users.id = refresh_tokens.user_id
        """
    )
    op.execute("DELETE FROM refresh_tokens WHERE tenant_id IS NULL")
    op.alter_column("refresh_tokens", "tenant_id", existing_type=sa.UUID(), nullable=False)
    op.create_foreign_key(
        op.f("fk_refresh_tokens_tenant_id_tenants"),
        "refresh_tokens",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_refresh_tokens_tenant_id_tenants"), "refresh_tokens", type_="foreignkey")
    op.drop_column("refresh_tokens", "tenant_id")

    op.drop_constraint(op.f("ck_users_password_matches_role"), "users", type_="check")
    op.drop_constraint(op.f("ck_users_phone_is_e164"), "users", type_="check")
    op.drop_constraint(op.f("ck_users_email_is_lowercase"), "users", type_="check")
    op.drop_constraint(op.f("ck_users_status_valid"), "users", type_="check")
    op.drop_constraint(op.f("ck_users_role_valid"), "users", type_="check")

    op.execute("DELETE FROM users WHERE email IS NULL OR password_hash IS NULL")
    op.execute("UPDATE users SET role = 'TENANT_ADMIN' WHERE role = 'ADMIN'")

    op.create_check_constraint(
        op.f("ck_users_email_is_lowercase"), "users", "email = lower(email)"
    )
    op.create_check_constraint(
        op.f("ck_users_role_valid"),
        "users",
        "role IN ('PLATFORM_ADMIN', 'TENANT_ADMIN', 'STAFF', 'CUSTOMER')",
    )
    op.create_check_constraint(
        op.f("ck_users_role_matches_tenant_scope"),
        "users",
        "(role = 'PLATFORM_ADMIN') = (tenant_id IS NULL)",
    )

    op.create_index(
        "uq_users_platform_email",
        "users",
        ["email"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NULL"),
    )
    op.drop_constraint("uq_users_tenant_phone", "users", type_="unique")
    op.drop_index(op.f("ix_users_tenant_id"), table_name="users")

    op.alter_column(
        "users",
        "role",
        existing_type=sa.String(length=20),
        type_=sa.VARCHAR(length=50),
        existing_nullable=False,
    )
    op.alter_column(
        "users", "password_hash", existing_type=sa.VARCHAR(length=255), nullable=False
    )
    op.alter_column("users", "email", existing_type=sa.VARCHAR(length=255), nullable=False)
    op.alter_column("users", "tenant_id", existing_type=sa.UUID(), nullable=True)

    op.drop_column("users", "is_verified")
    op.drop_column("users", "status")
    op.drop_column("users", "name")
    op.drop_column("users", "phone")

    op.drop_index(
        op.f("ix_admin_auth_challenges_user_id"), table_name="admin_auth_challenges"
    )
    op.drop_table("admin_auth_challenges")
    op.drop_index("ix_otp_requests_tenant_id_phone_purpose", table_name="otp_requests")
    op.drop_table("otp_requests")
    op.drop_index(op.f("ix_tenant_domains_tenant_id"), table_name="tenant_domains")
    op.drop_table("tenant_domains")
