"""Create folders, collections, and collection members tables.

Revision ID: 0004_create_folders_collections_and_members
Revises: 0003_create_vault_items_and_revisions
Create Date: 2026-02-20 00:00:03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0004_create_folders_collections_and_members"
down_revision: Union[str, None] = "0003_create_vault_items_and_revisions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


collection_permission_enum = sa.Enum(
    "view",
    "edit",
    "share",
    "manage",
    name="collection_permission",
)


def upgrade() -> None:
    op.create_table(
        "folders",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_folder_id", sa.Uuid(), sa.ForeignKey("folders.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_folders_org_id", "folders", ["org_id"], unique=False)
    op.create_index("ix_folders_owner_id", "folders", ["owner_id"], unique=False)
    op.create_index("ix_folders_parent_folder_id", "folders", ["parent_folder_id"], unique=False)

    op.create_table(
        "collections",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_collections_org_id", "collections", ["org_id"], unique=False)
    op.create_index("ix_collections_created_by", "collections", ["created_by"], unique=False)

    op.create_table(
        "collection_members",
        sa.Column(
            "collection_id",
            sa.Uuid(),
            sa.ForeignKey("collections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_or_group_id", sa.Uuid(), nullable=False),
        sa.Column("permission", collection_permission_enum, nullable=False),
        sa.PrimaryKeyConstraint("collection_id", "user_or_group_id", name="pk_collection_members"),
    )
    op.create_index("ix_collection_members_user_or_group_id", "collection_members", ["user_or_group_id"], unique=False)

    op.create_foreign_key(
        "fk_vault_items_folder_id_folders",
        "vault_items",
        "folders",
        ["folder_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_vault_items_folder_id_folders", "vault_items", type_="foreignkey")
    op.drop_index("ix_collection_members_user_or_group_id", table_name="collection_members")
    op.drop_table("collection_members")
    op.drop_index("ix_collections_created_by", table_name="collections")
    op.drop_index("ix_collections_org_id", table_name="collections")
    op.drop_table("collections")
    op.drop_index("ix_folders_parent_folder_id", table_name="folders")
    op.drop_index("ix_folders_owner_id", table_name="folders")
    op.drop_index("ix_folders_org_id", table_name="folders")
    op.drop_table("folders")
