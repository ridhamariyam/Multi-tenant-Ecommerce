"""merge coupons and search history heads

Revision ID: 0e00dd896659
Revises: 957a306ffa94, b3f7c21a9e04
Create Date: 2026-09-05 04:24:34.077905

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0e00dd896659'
down_revision: Union[str, Sequence[str], None] = ('957a306ffa94', 'b3f7c21a9e04')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
