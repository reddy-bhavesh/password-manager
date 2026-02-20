from __future__ import annotations

import datetime
import enum
import uuid

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditLogAction(str, enum.Enum):
    LOGIN = "login"
    LOGOUT = "logout"
    REFRESH_TOKEN = "refresh_token"
    CREATE_ITEM = "create_item"
    VIEW_ITEM = "view_item"
    EDIT_ITEM = "edit_item"
    DELETE_ITEM = "delete_item"
    RESTORE_ITEM = "restore_item"
    SHARE_ITEM = "share_item"
    MFA_ENABLE = "mfa_enable"
    MFA_DISABLE = "mfa_disable"
    SESSION_REVOKE = "session_revoke"
    INVITE_USER = "invite_user"
    ACCEPT_INVITE = "accept_invite"


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[AuditLogAction] = mapped_column(
        Enum(AuditLogAction, name="audit_log_action", native_enum=True),
        nullable=False,
    )
    target_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    user_agent: Mapped[str] = mapped_column(Text, nullable=False)
    geo_location: Mapped[str] = mapped_column(String(255), nullable=False)
    timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
