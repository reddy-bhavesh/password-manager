"""Create mfa_totp_credentials table.

Revision ID: 0007_create_mfa_totp_credentials
Revises: 0006_add_auth_verifier_hash_to_users
Create Date: 2026-02-20 00:00:06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0007_create_mfa_totp_credentials"
down_revision: Union[str, None] = "0006_add_auth_verifier_hash_to_users"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mfa_totp_credentials",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, nullable=False),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("totp_secret", sa.String(length=64), nullable=False),
        sa.Column("backup_code_hashes", sa.JSON(), nullable=False, server_default=sa.text("(JSON_ARRAY())")),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_mfa_totp_credentials_org_id", "mfa_totp_credentials", ["org_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_mfa_totp_credentials_org_id", table_name="mfa_totp_credentials")
    op.drop_table("mfa_totp_credentials")
