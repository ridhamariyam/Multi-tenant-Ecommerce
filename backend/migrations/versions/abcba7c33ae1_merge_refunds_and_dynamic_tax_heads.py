"""merge refunds and dynamic tax heads

Revision ID: abcba7c33ae1
Revises: 5b09417602ed, 7c20f31a9d42
Create Date: 2026-10-16 18:29:00.816625

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'abcba7c33ae1'
down_revision: Union[str, Sequence[str], None] = ('5b09417602ed', '7c20f31a9d42')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
