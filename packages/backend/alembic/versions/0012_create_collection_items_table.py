"""Create collection_items join table.

Revision ID: 0012_create_collection_items_table
Revises: 0011_org_groups_and_audit_actions
Create Date: 2026-02-23 00:10:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0012_create_collection_items_table"
down_revision: Union[str, None] = "0011_org_groups_and_audit_actions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "collection_items",
        sa.Column(
            "collection_id",
            sa.Uuid(),
            sa.ForeignKey("collections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "item_id",
            sa.Uuid(),
            sa.ForeignKey("vault_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("collection_id", "item_id", name="pk_collection_items"),
    )
    op.create_index("ix_collection_items_item_id", "collection_items", ["item_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_collection_items_item_id", table_name="collection_items")
    op.drop_table("collection_items")
