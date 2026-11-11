"""require a phone and drop legacy user columns"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e18d5c30ba47"
down_revision: Union[str, Sequence[str], None] = "c4f2a71b0e93"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

E164 = r"phone ~ '^\+[1-9][0-9]{7,14}$'"


def upgrade() -> None:
    op.execute("DELETE FROM users WHERE phone IS NULL")

    op.alter_column("users", "phone", existing_type=sa.String(length=16), nullable=False)
    op.drop_constraint(op.f("ck_users_phone_is_e164"), "users", type_="check")
    op.create_check_constraint(op.f("ck_users_phone_is_e164"), "users", E164)

    op.drop_column("users", "is_active")
    op.drop_column("refresh_tokens", "last_used_at")


def downgrade() -> None:
    op.add_column(
        "refresh_tokens",
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.execute("UPDATE users SET is_active = (status = 'ACTIVE')")
    op.alter_column("users", "is_active", server_default=None)

    op.drop_constraint(op.f("ck_users_phone_is_e164"), "users", type_="check")
    op.create_check_constraint(
        op.f("ck_users_phone_is_e164"), "users", f"phone IS NULL OR {E164}"
    )
    op.alter_column("users", "phone", existing_type=sa.String(length=16), nullable=True)
