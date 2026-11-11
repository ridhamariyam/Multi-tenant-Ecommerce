"""scope search history per shopper phrase

Revision ID: b3f7c21a9e04
Revises: c8a1d43f7b26
Create Date: 2026-09-04 18:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3f7c21a9e04'
down_revision: Union[str, Sequence[str], None] = 'c8a1d43f7b26'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        'search_history',
        'created_at',
        new_column_name='searched_at',
        type_=sa.DateTime(timezone=True),
        existing_nullable=False,
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )

    # The old table stored one row per search, so the same phrase can appear
    # many times. Keep the most recent before the uniqueness rule lands.
    op.execute(
        """
        DELETE FROM search_history a
        USING search_history b
        WHERE a.tenant_id = b.tenant_id
          AND a.user_id = b.user_id
          AND a.query = b.query
          AND (a.searched_at, a.id) < (b.searched_at, b.id)
        """
    )

    op.drop_constraint(
        op.f('fk_search_history_user_id_users'), 'search_history', type_='foreignkey'
    )
    op.create_unique_constraint(
        'uq_search_history_tenant_id_id', 'search_history', ['tenant_id', 'id']
    )
    op.create_unique_constraint(
        'uq_search_history_tenant_user_query',
        'search_history',
        ['tenant_id', 'user_id', 'query'],
    )
    op.create_foreign_key(
        'fk_search_history_tenant_user_users',
        'search_history',
        'users',
        ['tenant_id', 'user_id'],
        ['tenant_id', 'id'],
        ondelete='CASCADE',
    )
    op.create_index(
        'ix_search_history_tenant_id_user_id_searched_at',
        'search_history',
        ['tenant_id', 'user_id', 'searched_at'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        'ix_search_history_tenant_id_user_id_searched_at', table_name='search_history'
    )
    op.drop_constraint(
        'fk_search_history_tenant_user_users', 'search_history', type_='foreignkey'
    )
    op.drop_constraint(
        'uq_search_history_tenant_user_query', 'search_history', type_='unique'
    )
    op.drop_constraint(
        'uq_search_history_tenant_id_id', 'search_history', type_='unique'
    )
    op.create_foreign_key(
        op.f('fk_search_history_user_id_users'),
        'search_history',
        'users',
        ['user_id'],
        ['id'],
        ondelete='CASCADE',
    )
    op.alter_column(
        'search_history',
        'searched_at',
        new_column_name='created_at',
        type_=sa.DateTime(),
        existing_nullable=False,
    )
