"""Backend skeleton baseline revision.

Revision ID: 0001_backend_skeleton
Revises:
Create Date: 2026-02-20 00:00:00
"""

from typing import Sequence, Union


from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0001_backend_skeleton"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

