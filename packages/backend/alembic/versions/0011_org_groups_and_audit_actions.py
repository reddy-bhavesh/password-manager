"""Create org groups tables and add audit actions.

Revision ID: 0011_org_groups_and_audit_actions
Revises: 0010_org_user_management_audit_actions
Create Date: 2026-02-23 00:00:11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0011_org_groups_and_audit_actions"
down_revision: Union[str, None] = "0010_org_user_management_audit_actions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_AUDIT_LOG_ACTION_VALUES_WITH_GROUPS = (
    "login",
    "logout",
    "refresh_token",
    "create_item",
    "view_item",
    "edit_item",
    "delete_item",
    "restore_item",
    "share_item",
    "mfa_enable",
    "mfa_disable",
    "session_revoke",
    "invite_user",
    "accept_invite",
    "change_user_role",
    "offboard_user",
    "create_group",
    "add_group_member",
    "remove_group_member",
)

_AUDIT_LOG_ACTION_VALUES_WITHOUT_GROUPS = (
    "login",
    "logout",
    "refresh_token",
    "create_item",
    "view_item",
    "edit_item",
    "delete_item",
    "restore_item",
    "share_item",
    "mfa_enable",
    "mfa_disable",
    "session_revoke",
    "invite_user",
    "accept_invite",
    "change_user_role",
    "offboard_user",
)


def _enum_sql(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    op.create_table(
        "groups",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_groups_org_id", "groups", ["org_id"], unique=False)

    op.create_table(
        "group_members",
        sa.Column("group_id", sa.Uuid(), sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.PrimaryKeyConstraint("group_id", "user_id", name="pk_group_members"),
    )
    op.create_index("ix_group_members_user_id", "group_members", ["user_id"], unique=False)

    op.execute(
        f"""
        ALTER TABLE audit_logs
        MODIFY COLUMN action ENUM({_enum_sql(_AUDIT_LOG_ACTION_VALUES_WITH_GROUPS)}) NOT NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE audit_logs
        SET action = 'session_revoke'
        WHERE action IN ('create_group', 'add_group_member', 'remove_group_member')
        """
    )
    op.execute(
        f"""
        ALTER TABLE audit_logs
        MODIFY COLUMN action ENUM({_enum_sql(_AUDIT_LOG_ACTION_VALUES_WITHOUT_GROUPS)}) NOT NULL
        """
    )

    op.drop_index("ix_group_members_user_id", table_name="group_members")
    op.drop_table("group_members")
    op.drop_index("ix_groups_org_id", table_name="groups")
    op.drop_table("groups")
