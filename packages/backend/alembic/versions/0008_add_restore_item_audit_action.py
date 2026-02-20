"""Add restore_item audit action enum value.

Revision ID: 0008_add_restore_item_audit_action
Revises: 0007_create_mfa_totp_credentials
Create Date: 2026-02-20 00:00:08
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0008_add_restore_item_audit_action"
down_revision: Union[str, None] = "0007_create_mfa_totp_credentials"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_AUDIT_LOG_ACTION_VALUES_WITH_RESTORE = (
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

_AUDIT_LOG_ACTION_VALUES_WITHOUT_RESTORE = (
    "login",
    "logout",
    "refresh_token",
    "create_item",
    "view_item",
    "edit_item",
    "delete_item",
    "share_item",
    "mfa_enable",
    "mfa_disable",
    "session_revoke",
)


def _enum_sql(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    op.execute(
        f"""
        ALTER TABLE audit_logs
        MODIFY COLUMN action ENUM({_enum_sql(_AUDIT_LOG_ACTION_VALUES_WITH_RESTORE)}) NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("UPDATE audit_logs SET action = 'edit_item' WHERE action = 'restore_item'")
    op.execute(
        f"""
        ALTER TABLE audit_logs
        MODIFY COLUMN action ENUM({_enum_sql(_AUDIT_LOG_ACTION_VALUES_WITHOUT_RESTORE)}) NOT NULL
        """
    )
