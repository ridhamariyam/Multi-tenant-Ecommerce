"""merge wishlist and coupons heads

Revision ID: 27009d937698
Revises: 50a8b75ce593, 8cb4b3a96b1f
Create Date: 2026-09-05 13:25:51.515227

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '27009d937698'
down_revision: Union[str, Sequence[str], None] = ('50a8b75ce593', '8cb4b3a96b1f')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
