from __future__ import annotations

import datetime
import uuid

from sqlalchemy import JSON, DateTime, ForeignKey, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MfaTotpCredential(Base):
    __tablename__ = "mfa_totp_credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    totp_secret: Mapped[str] = mapped_column(String(64), nullable=False)
    backup_code_hashes: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        server_default=text("(JSON_ARRAY())"),
    )
    confirmed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
