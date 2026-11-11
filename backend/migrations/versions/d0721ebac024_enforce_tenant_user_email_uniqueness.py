"""enforce tenant user email uniqueness"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd0721ebac024'
down_revision: Union[str, Sequence[str], None] = 'a2c1c42eefa3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint('uq_users_tenant_email', 'users', ['tenant_id', 'email'])


def downgrade() -> None:
    op.drop_constraint('uq_users_tenant_email', 'users', type_='unique')
