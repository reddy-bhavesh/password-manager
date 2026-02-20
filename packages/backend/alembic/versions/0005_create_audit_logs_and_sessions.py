"""Create audit_logs and sessions tables.

Revision ID: 0005_create_audit_logs_and_sessions
Revises: 0004_create_folders_collections_and_members
Create Date: 2026-02-20 00:00:04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0005_create_audit_logs_and_sessions"
down_revision: Union[str, None] = "0004_create_folders_collections_and_members"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


audit_log_action_enum = sa.Enum(
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
    name="audit_log_action",
)


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", audit_log_action_enum, nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=False),
        sa.Column("user_agent", sa.Text(), nullable=False),
        sa.Column("geo_location", sa.String(length=255), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_audit_logs_org_id_timestamp", "audit_logs", ["org_id", "timestamp"], unique=False)
    op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"], unique=False)
    op.execute(
        """
        CREATE TRIGGER trg_audit_logs_prevent_update
        BEFORE UPDATE ON audit_logs
        FOR EACH ROW
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'audit_logs is append-only'
        """
    )

    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=255), nullable=False),
        sa.Column("device_info", sa.JSON(), nullable=False, server_default=sa.text("(JSON_OBJECT())")),
        sa.Column("ip_address", sa.String(length=45), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"], unique=False)
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_sessions_expires_at", table_name="sessions")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_prevent_update")
    op.drop_index("ix_audit_logs_actor_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_org_id_timestamp", table_name="audit_logs")
    op.drop_table("audit_logs")
