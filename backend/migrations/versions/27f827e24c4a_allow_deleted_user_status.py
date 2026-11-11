"""allow deleted user status

Revision ID: 27f827e24c4a
Revises: 5f254952561c
Create Date: 2026-09-05 16:02:47.729309

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '27f827e24c4a'
down_revision: Union[str, Sequence[str], None] = '5f254952561c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # An erased account keeps its row so past orders still have a customer,
    # but it is neither active nor merely deactivated.
    op.drop_constraint(op.f("ck_users_status_valid"), "users", type_="check")
    op.create_check_constraint(
        "status_valid",
        "users",
        "status IN ('ACTIVE', 'INACTIVE', 'DELETED')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("UPDATE users SET status = 'INACTIVE' WHERE status = 'DELETED'")
    op.drop_constraint(op.f("ck_users_status_valid"), "users", type_="check")
    op.create_check_constraint(
        "status_valid",
        "users",
        "status IN ('ACTIVE', 'INACTIVE')",
    )
