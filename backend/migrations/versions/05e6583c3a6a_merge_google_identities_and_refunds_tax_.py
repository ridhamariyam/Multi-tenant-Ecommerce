"""merge google identities and refunds tax heads

Revision ID: 05e6583c3a6a
Revises: 7f2c9b1a4d63, abcba7c33ae1
Create Date: 2026-10-20 17:42:24.908000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '05e6583c3a6a'
down_revision: Union[str, Sequence[str], None] = ('7f2c9b1a4d63', 'abcba7c33ae1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
