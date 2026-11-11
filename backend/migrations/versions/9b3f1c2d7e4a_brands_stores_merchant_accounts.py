"""Brands, stores and platform merchant accounts.

Turns the existing tenants into brands on a multi-brand platform without
touching any brand-owned data:

1. New tables: `merchant_accounts` and `merchant_refresh_tokens` (platform
   logins), `stores` (one per brand: subdomain, theme, publication) and
   `brand_members` (account <-> brand <-> that brand's ADMIN/STAFF user row).
2. New nullable/defaulted columns on `tenants` (profile, owner, platform
   status) and `tenant_domains` (verification, primary flag). Existing
   domains are marked verified: an operator configured them.
3. Backfill:
   - every tenant gets a store, published, since it is already live;
     its subdomain is the tenant slug (adjusted if reserved or clashing);
   - every ADMIN/STAFF user with an email gets a merchant account (one per
     email, keeping the first password hash found, so the person signs in
     to the platform with the password they already use) and a membership.
     Each brand's earliest active ADMIN becomes its OWNER and the brand's
     `owner_account_id`; other admins are ADMIN; staff are CUSTOM, keeping
     the permissions they were given on the staff screen. Users without an
     email keep only the per-store login they have today.
4. `users.phone_is_e164` is relaxed so staff created through a membership
   (who sign in by email) may have no phone. A stored phone is still E.164.

The per-store admin login keeps working throughout. Downgrade drops the new
tables and columns; it restores the stricter phone rule as NOT VALID so
rows created meanwhile are kept rather than deleted.

Revision ID: 9b3f1c2d7e4a
Revises: 76034eb57569
Create Date: 2026-11-06

"""
import re
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "9b3f1c2d7e4a"
down_revision: Union[str, Sequence[str], None] = "76034eb57569"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Frozen copy of app/stores/constants.py RESERVED_SUBDOMAINS at this revision.
_RESERVED = frozenset(
    {
        "www", "api", "admin", "app", "dashboard", "platform", "studio", "static",
        "media", "cdn", "assets", "mail", "smtp", "ftp", "status", "help", "support",
        "docs", "blog", "auth", "login", "signup", "billing", "webhooks", "minio",
    }
)
_E164 = r"phone ~ '^\+[1-9][0-9]{7,14}$'"
_STRICT_PHONE = f"({_E164}) OR (role = 'CUSTOMER' AND phone IS NULL)"
_RELAXED_PHONE = f"phone IS NULL OR {_E164}"


def _subdomain(slug: str, taken: set[str]) -> str:
    base = re.sub(r"[^a-z0-9-]+", "-", slug.lower()).strip("-")[:63].strip("-") or "store"
    candidate = base if base not in _RESERVED else f"{base[:57]}-store"
    n = 1
    while candidate in taken:
        n += 1
        suffix = f"-{n}"
        candidate = base[: 63 - len(suffix)].rstrip("-") + suffix
    taken.add(candidate)
    return candidate


def _create_schema() -> None:
    op.create_table(
        "merchant_accounts",
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=True),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'ACTIVE'"), nullable=False),
        sa.Column("is_platform_admin", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('ACTIVE', 'SUSPENDED')", name=op.f("ck_merchant_accounts_status_valid")),
        sa.CheckConstraint("email = lower(email)", name=op.f("ck_merchant_accounts_email_is_lowercase")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_merchant_accounts")),
        sa.UniqueConstraint("email", name=op.f("uq_merchant_accounts_email")),
    )
    op.create_table(
        "merchant_refresh_tokens",
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"], ["merchant_accounts.id"],
            name=op.f("fk_merchant_refresh_tokens_account_id_merchant_accounts"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_merchant_refresh_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_merchant_refresh_tokens_token_hash")),
    )
    op.create_index("ix_merchant_refresh_tokens_account", "merchant_refresh_tokens", ["account_id"], unique=False)

    op.create_table(
        "stores",
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("subdomain", sa.String(length=63), nullable=False),
        sa.Column("theme", sa.String(length=30), server_default=sa.text("'runway'"), nullable=False),
        sa.Column("logo_url", sa.String(length=2048), nullable=True),
        sa.Column("favicon_url", sa.String(length=2048), nullable=True),
        sa.Column("primary_color", sa.String(length=7), nullable=True),
        sa.Column("secondary_color", sa.String(length=7), nullable=True),
        sa.Column("published", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("primary_color IS NULL OR primary_color ~ '^#[0-9a-fA-F]{6}$'", name=op.f("ck_stores_primary_color_hex")),
        sa.CheckConstraint("secondary_color IS NULL OR secondary_color ~ '^#[0-9a-fA-F]{6}$'", name=op.f("ck_stores_secondary_color_hex")),
        sa.CheckConstraint("subdomain ~ '^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$'", name=op.f("ck_stores_subdomain_format")),
        sa.CheckConstraint("theme IN ('runway', 'minimal')", name=op.f("ck_stores_theme_valid")),
        sa.CheckConstraint("published = false OR published_at IS NOT NULL", name=op.f("ck_stores_published_has_timestamp")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_stores_tenant_id_tenants"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stores")),
        sa.UniqueConstraint("subdomain", name="uq_stores_subdomain"),
        sa.UniqueConstraint("tenant_id", name="uq_stores_tenant"),
    )

    op.create_table(
        "brand_members",
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'ACTIVE'"), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "role IN ('OWNER', 'ADMIN', 'PRODUCT_MANAGER', 'ORDER_MANAGER', 'CUSTOM')",
            name=op.f("ck_brand_members_role_valid"),
        ),
        sa.CheckConstraint("status IN ('ACTIVE', 'REMOVED')", name=op.f("ck_brand_members_status_valid")),
        sa.ForeignKeyConstraint(
            ["account_id"], ["merchant_accounts.id"],
            name=op.f("fk_brand_members_account_id_merchant_accounts"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"], ["users.tenant_id", "users.id"],
            name="fk_brand_members_tenant_user", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_brand_members_tenant_id_tenants"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_brand_members")),
        sa.UniqueConstraint("tenant_id", "account_id", name="uq_brand_members_tenant_account"),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_brand_members_tenant_user"),
    )
    op.create_index("ix_brand_members_account", "brand_members", ["account_id"], unique=False)
    op.create_index(
        "uq_brand_members_one_owner", "brand_members", ["tenant_id"], unique=True,
        postgresql_where=sa.text("role = 'OWNER' AND status = 'ACTIVE'"),
    )

    # Existing domains take verified_at = now() from the server default.
    op.add_column("tenant_domains", sa.Column("verified_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True))
    op.add_column("tenant_domains", sa.Column("is_primary", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("tenant_domains", sa.Column("verification_token", sa.String(length=64), nullable=True))
    op.create_index(
        "uq_tenant_domains_one_primary", "tenant_domains", ["tenant_id"], unique=True,
        postgresql_where=sa.text("is_primary"),
    )

    op.add_column("tenants", sa.Column("status", sa.String(length=20), server_default=sa.text("'ACTIVE'"), nullable=False))
    op.add_column("tenants", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("tenants", sa.Column("logo_url", sa.String(length=2048), nullable=True))
    op.add_column("tenants", sa.Column("contact_email", sa.String(length=255), nullable=True))
    op.add_column("tenants", sa.Column("phone", sa.String(length=20), nullable=True))
    op.add_column("tenants", sa.Column("owner_account_id", sa.UUID(), nullable=True))
    op.add_column("tenants", sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tenants", sa.Column("suspension_reason", sa.String(length=500), nullable=True))
    op.create_index(op.f("ix_tenants_owner_account_id"), "tenants", ["owner_account_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_tenants_owner_account_id_merchant_accounts"), "tenants", "merchant_accounts",
        ["owner_account_id"], ["id"], ondelete="SET NULL",
    )
    op.create_check_constraint(op.f("ck_tenants_inactive_unless_active_status"), "tenants", "status = 'ACTIVE' OR is_active = false")
    op.create_check_constraint(op.f("ck_tenants_status_valid"), "tenants", "status IN ('ACTIVE', 'SUSPENDED')")

    op.drop_constraint(op.f("ck_users_phone_is_e164"), "users", type_="check")
    op.create_check_constraint(op.f("ck_users_phone_is_e164"), "users", _RELAXED_PHONE)


def _backfill() -> None:
    conn = op.get_bind()

    taken: set[str] = set()
    for tenant_id, name, slug in conn.execute(
        sa.text("SELECT id, name, slug FROM tenants ORDER BY created_at, id")
    ).all():
        conn.execute(
            sa.text(
                "INSERT INTO stores (id, tenant_id, name, subdomain, published, published_at) "
                "VALUES (:id, :tenant_id, :name, :subdomain, true, now())"
            ),
            {"id": uuid.uuid4(), "tenant_id": tenant_id, "name": name, "subdomain": _subdomain(slug, taken)},
        )

    staff = conn.execute(
        sa.text(
            "SELECT id, tenant_id, email, name, phone, password_hash, role, status "
            "FROM users "
            "WHERE role IN ('ADMIN', 'STAFF') AND email IS NOT NULL AND password_hash IS NOT NULL "
            "AND status <> 'DELETED' "
            # Active admins first, oldest first: the first per brand becomes owner.
            "ORDER BY (status <> 'ACTIVE'), (role <> 'ADMIN'), created_at, id"
        )
    ).all()

    accounts: dict[str, uuid.UUID] = {}
    owned: set[uuid.UUID] = set()
    for user_id, tenant_id, email, name, phone, password_hash, role, status in staff:
        email = email.strip().lower()
        account_id = accounts.get(email)
        if account_id is None:
            account_id = uuid.uuid4()
            accounts[email] = account_id
            conn.execute(
                sa.text(
                    "INSERT INTO merchant_accounts (id, email, name, phone, password_hash) "
                    "VALUES (:id, :email, :name, :phone, :password_hash)"
                ),
                {
                    "id": account_id,
                    "email": email,
                    "name": name,
                    "phone": phone if phone and len(phone) <= 20 else None,
                    "password_hash": password_hash,
                },
            )

        active = status == "ACTIVE"
        if role == "ADMIN" and active and tenant_id not in owned:
            member_role = "OWNER"
            owned.add(tenant_id)
            conn.execute(
                sa.text("UPDATE tenants SET owner_account_id = :account WHERE id = :tenant"),
                {"account": account_id, "tenant": tenant_id},
            )
        elif role == "ADMIN":
            member_role = "ADMIN"
        else:
            member_role = "CUSTOM"

        conn.execute(
            sa.text(
                "INSERT INTO brand_members (id, tenant_id, account_id, user_id, role, status) "
                "VALUES (:id, :tenant_id, :account_id, :user_id, :role, :status) "
                "ON CONFLICT (tenant_id, account_id) DO NOTHING"
            ),
            {
                "id": uuid.uuid4(),
                "tenant_id": tenant_id,
                "account_id": account_id,
                "user_id": user_id,
                "role": member_role,
                "status": "ACTIVE" if active else "REMOVED",
            },
        )


def upgrade() -> None:
    _create_schema()
    _backfill()


def downgrade() -> None:
    # NOT VALID: rows added under the relaxed rule stay; new rows are checked.
    op.drop_constraint(op.f("ck_users_phone_is_e164"), "users", type_="check")
    op.execute(f"ALTER TABLE users ADD CONSTRAINT ck_users_phone_is_e164 CHECK ({_STRICT_PHONE}) NOT VALID")

    op.drop_constraint(op.f("ck_tenants_status_valid"), "tenants", type_="check")
    op.drop_constraint(op.f("ck_tenants_inactive_unless_active_status"), "tenants", type_="check")
    op.drop_constraint(op.f("fk_tenants_owner_account_id_merchant_accounts"), "tenants", type_="foreignkey")
    op.drop_index(op.f("ix_tenants_owner_account_id"), table_name="tenants")
    for column in (
        "suspension_reason", "suspended_at", "owner_account_id", "phone",
        "contact_email", "logo_url", "description", "status",
    ):
        op.drop_column("tenants", column)

    op.drop_index("uq_tenant_domains_one_primary", table_name="tenant_domains", postgresql_where=sa.text("is_primary"))
    for column in ("verification_token", "is_primary", "verified_at"):
        op.drop_column("tenant_domains", column)

    op.drop_index("uq_brand_members_one_owner", table_name="brand_members", postgresql_where=sa.text("role = 'OWNER' AND status = 'ACTIVE'"))
    op.drop_index("ix_brand_members_account", table_name="brand_members")
    op.drop_table("brand_members")
    op.drop_table("stores")
    op.drop_index("ix_merchant_refresh_tokens_account", table_name="merchant_refresh_tokens")
    op.drop_table("merchant_refresh_tokens")
    op.drop_table("merchant_accounts")
