"""constrain user role and drop redundant tenant index"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '018a1e9dbd22'
down_revision: Union[str, Sequence[str], None] = 'd0721ebac024'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(op.f('ix_users_tenant_id'), table_name='users')

    op.create_check_constraint(op.f('ck_users_role_valid'), 'users', "role IN ('PLATFORM_ADMIN', 'TENANT_ADMIN', 'STAFF', 'CUSTOMER')")


def downgrade() -> None:
    op.drop_constraint(op.f('ck_users_role_valid'), 'users', type_='check')
    op.create_index(op.f('ix_users_tenant_id'), 'users', ['tenant_id'], unique=False)
