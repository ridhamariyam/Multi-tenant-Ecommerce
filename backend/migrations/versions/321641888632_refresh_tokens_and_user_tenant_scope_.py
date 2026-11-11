"""refresh tokens and user tenant scope invariants"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '321641888632'
down_revision: Union[str, Sequence[str], None] = '018a1e9dbd22'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('refresh_tokens',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_refresh_tokens_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_refresh_tokens')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_refresh_tokens_token_hash'))
    )
    op.create_index(op.f('ix_refresh_tokens_user_id'), 'refresh_tokens', ['user_id'], unique=False)
    op.drop_index(op.f('ix_users_email'), table_name='users')

    op.create_index('uq_users_platform_email', 'users', ['email'], unique=True, postgresql_where=sa.text('tenant_id IS NULL'))

    op.execute("UPDATE users SET email = lower(email) WHERE email <> lower(email)")
    op.create_check_constraint(op.f('ck_users_email_is_lowercase'), 'users', 'email = lower(email)')

    op.create_check_constraint(op.f('ck_users_role_matches_tenant_scope'), 'users', "(role = 'PLATFORM_ADMIN') = (tenant_id IS NULL)")


def downgrade() -> None:
    op.drop_constraint(op.f('ck_users_role_matches_tenant_scope'), 'users', type_='check')
    op.drop_constraint(op.f('ck_users_email_is_lowercase'), 'users', type_='check')
    op.drop_index('uq_users_platform_email', table_name='users', postgresql_where=sa.text('tenant_id IS NULL'))
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=False)
    op.drop_index(op.f('ix_refresh_tokens_user_id'), table_name='refresh_tokens')
    op.drop_table('refresh_tokens')
