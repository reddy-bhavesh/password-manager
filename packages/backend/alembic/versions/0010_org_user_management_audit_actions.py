"""Add org user management audit actions.

Revision ID: 0010_org_user_management_audit_actions
Revises: 0009_org_invitations_and_audit_actions
Create Date: 2026-02-23 00:00:10
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0010_org_user_management_audit_actions"
down_revision: Union[str, None] = "0009_org_invitations_and_audit_actions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_AUDIT_LOG_ACTION_VALUES_WITH_ORG_USER_MGMT = (
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

_AUDIT_LOG_ACTION_VALUES_WITHOUT_ORG_USER_MGMT = (
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
)


def _enum_sql(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    op.execute(
        f"""
        ALTER TABLE audit_logs
        MODIFY COLUMN action ENUM({_enum_sql(_AUDIT_LOG_ACTION_VALUES_WITH_ORG_USER_MGMT)}) NOT NULL
        """
    )


def downgrade() -> None:
    op.execute(
        "UPDATE audit_logs SET action = 'session_revoke' WHERE action IN ('change_user_role', 'offboard_user')"
    )
    op.execute(
        f"""
        ALTER TABLE audit_logs
        MODIFY COLUMN action ENUM({_enum_sql(_AUDIT_LOG_ACTION_VALUES_WITHOUT_ORG_USER_MGMT)}) NOT NULL
        """
    )
