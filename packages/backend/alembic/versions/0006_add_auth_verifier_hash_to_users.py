"""Add auth_verifier_hash to users.

Revision ID: 0006_add_auth_verifier_hash_to_users
Revises: 0005_create_audit_logs_and_sessions
Create Date: 2026-02-20 00:00:05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0006_add_auth_verifier_hash_to_users"
down_revision: Union[str, None] = "0005_create_audit_logs_and_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("auth_verifier_hash", sa.Text(), nullable=False, server_default=""),
    )
    op.alter_column("users", "auth_verifier_hash", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "auth_verifier_hash")
