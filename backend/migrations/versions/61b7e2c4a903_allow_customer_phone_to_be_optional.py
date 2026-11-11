"""allow customer phone numbers to be optional"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "61b7e2c4a903"
down_revision: Union[str, Sequence[str], None] = (
    "7c20f31a9d42",
    "5b09417602ed",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

E164 = r"phone ~ '^\+[1-9][0-9]{7,14}$'"
OPTIONAL_CUSTOMER_PHONE = (
    f"(phone IS NOT NULL AND {E164}) "
    "OR (role = 'CUSTOMER' AND phone IS NULL)"
)


def upgrade() -> None:
    op.alter_column("users", "phone", existing_type=sa.String(length=16), nullable=True)
    op.drop_constraint(op.f("ck_users_phone_is_e164"), "users", type_="check")
    op.create_check_constraint(
        op.f("ck_users_phone_is_e164"), "users", OPTIONAL_CUSTOMER_PHONE
    )


def downgrade() -> None:
    connection = op.get_bind()
    null_customers = connection.scalar(
        sa.text("SELECT count(*) FROM users WHERE role = 'CUSTOMER' AND phone IS NULL")
    )
    if null_customers:
        raise RuntimeError(
            "Cannot restore mandatory user phones while phone-less customers exist; "
            "assign valid phone numbers or remove those accounts before downgrading."
        )

    op.drop_constraint(op.f("ck_users_phone_is_e164"), "users", type_="check")
    op.alter_column("users", "phone", existing_type=sa.String(length=16), nullable=False)
    op.create_check_constraint(op.f("ck_users_phone_is_e164"), "users", E164)
