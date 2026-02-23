from __future__ import annotations

import datetime
import uuid
from typing import Any

from pydantic import BaseModel


def _coerce_datetime(value: object) -> datetime.datetime:
    if isinstance(value, datetime.datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=datetime.UTC)
    if isinstance(value, str):
        text = value.strip()
        normalized = text.replace("Z", "+00:00")
        try:
            parsed = datetime.datetime.fromisoformat(normalized)
        except ValueError:
            parsed = datetime.datetime.strptime(text, "%Y-%m-%d %H:%M:%S.%f")
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=datetime.UTC)
    raise TypeError(f"Unsupported datetime value: {value!r}")


def _coerce_action(value: object) -> str:
    if hasattr(value, "value"):
        return str(getattr(value, "value")).lower()
    text = str(value).strip()
    if "." in text:
        text = text.split(".")[-1]
    return text.lower()


class AuditLogEntryResponse(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    actor_id: uuid.UUID | None
    action: str
    target_id: uuid.UUID | None
    ip_address: str
    user_agent: str
    geo_location: str
    timestamp: datetime.datetime

    @classmethod
    def from_audit_log(cls, log: Any) -> "AuditLogEntryResponse":
        return cls(
            id=log.id,
            org_id=log.org_id,
            actor_id=log.actor_id,
            action=_coerce_action(log.action),
            target_id=log.target_id,
            ip_address=log.ip_address,
            user_agent=log.user_agent,
            geo_location=log.geo_location,
            timestamp=_coerce_datetime(log.timestamp),
        )


class AuditLogsPageResponse(BaseModel):
    items: list[AuditLogEntryResponse]
    total: int
    page: int
    per_page: int


class SecurityHealthReportResponse(BaseModel):
    overall_score: int
    failed_logins_30d: int
    mfa_adoption_pct: int
    suspended_accounts: int
    over_shared_items: int
