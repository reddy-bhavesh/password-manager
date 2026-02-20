"""Add org invitation fields to users and audit enum actions.

Revision ID: 0009_org_invitations_and_audit_actions
Revises: 0008_add_restore_item_audit_action
Create Date: 2026-02-20 00:00:09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0009_org_invitations_and_audit_actions"
down_revision: Union[str, None] = "0008_add_restore_item_audit_action"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_AUDIT_LOG_ACTION_VALUES_WITH_INVITES = (
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

_AUDIT_LOG_ACTION_VALUES_WITHOUT_INVITES = (
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
)


def _enum_sql(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    op.add_column("users", sa.Column("invitation_token_hash", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("invitation_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        f"""
        ALTER TABLE audit_logs
        MODIFY COLUMN action ENUM({_enum_sql(_AUDIT_LOG_ACTION_VALUES_WITH_INVITES)}) NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("UPDATE audit_logs SET action = 'session_revoke' WHERE action IN ('invite_user', 'accept_invite')")
    op.execute(
        f"""
        ALTER TABLE audit_logs
        MODIFY COLUMN action ENUM({_enum_sql(_AUDIT_LOG_ACTION_VALUES_WITHOUT_INVITES)}) NOT NULL
        """
    )
    op.drop_column("users", "invitation_expires_at")
    op.drop_column("users", "invitation_token_hash")
