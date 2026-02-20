"""Create vault items and vault item revisions tables.

Revision ID: 0003_create_vault_items_and_revisions
Revises: 0002_create_organizations_and_users
Create Date: 2026-02-20 00:00:02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0003_create_vault_items_and_revisions"
down_revision: Union[str, None] = "0002_create_organizations_and_users"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


vault_item_type_enum = sa.Enum(
    "login",
    "secure_note",
    "credit_card",
    "identity",
    "ssh_key",
    "api_key",
    name="vault_item_type",
)


def upgrade() -> None:
    op.create_table(
        "vault_items",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", vault_item_type_enum, nullable=False),
        sa.Column("encrypted_data", sa.Text(), nullable=False),
        sa.Column("encrypted_key", sa.Text(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("folder_id", sa.Uuid(), nullable=True),
        sa.Column("favorite", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_vault_items_owner_id", "vault_items", ["owner_id"], unique=False)
    op.create_index("ix_vault_items_org_id", "vault_items", ["org_id"], unique=False)

    op.create_table(
        "vault_item_revisions",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("item_id", sa.Uuid(), sa.ForeignKey("vault_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("encrypted_data", sa.Text(), nullable=False),
        sa.Column("encrypted_key", sa.Text(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("item_id", "revision_number", name="uq_vault_item_revisions_item_revision"),
    )
    op.create_index("ix_vault_item_revisions_item_id", "vault_item_revisions", ["item_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_vault_item_revisions_item_id", table_name="vault_item_revisions")
    op.drop_table("vault_item_revisions")
    op.drop_index("ix_vault_items_org_id", table_name="vault_items")
    op.drop_index("ix_vault_items_owner_id", table_name="vault_items")
    op.drop_table("vault_items")
