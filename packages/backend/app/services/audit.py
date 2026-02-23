from __future__ import annotations

import datetime
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog, AuditLogAction
from app.models.user import User


def _normalize_uuid(value: object) -> str:
    return str(value).replace("-", "").lower()


def _uuid_match(column: object, value: object):
    return func.lower(func.replace(column, "-", "")) == _normalize_uuid(value)


def _normalize_dt(value: datetime.datetime | None) -> datetime.datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=datetime.UTC)


@dataclass(frozen=True)
class AuditLogFilters:
    actor_id: object | None = None
    action: AuditLogAction | None = None
    start_date: datetime.datetime | None = None
    end_date: datetime.datetime | None = None


@dataclass(frozen=True)
class AuditLogPage:
    items: list[AuditLog]
    total: int
    page: int
    per_page: int


def _build_filters(*, current_user: User, filters: AuditLogFilters) -> list[object]:
    start_date = _normalize_dt(filters.start_date)
    end_date = _normalize_dt(filters.end_date)
    if start_date and end_date and start_date > end_date:
        raise ValueError("start_date must be less than or equal to end_date")

    clauses: list[object] = [_uuid_match(AuditLog.org_id, current_user.org_id)]
    if filters.actor_id is not None:
        clauses.append(_uuid_match(AuditLog.actor_id, filters.actor_id))
    if filters.action is not None:
        clauses.append(AuditLog.action == filters.action)
    if start_date is not None:
        clauses.append(AuditLog.timestamp >= start_date)
    if end_date is not None:
        clauses.append(AuditLog.timestamp <= end_date)
    return clauses


async def list_audit_logs(
    db: AsyncSession,
    *,
    current_user: User,
    page: int = 1,
    per_page: int = 50,
    filters: AuditLogFilters | None = None,
) -> AuditLogPage:
    normalized_page = max(1, page)
    normalized_per_page = max(1, min(per_page, 100))
    resolved_filters = filters or AuditLogFilters()
    where_clauses = _build_filters(current_user=current_user, filters=resolved_filters)

    total = int(
        (await db.execute(select(func.count()).select_from(AuditLog).where(*where_clauses))).scalar_one()
    )
    offset = (normalized_page - 1) * normalized_per_page

    items = list(
        (
            await db.execute(
                select(AuditLog)
                .where(*where_clauses)
                .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
                .limit(normalized_per_page)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return AuditLogPage(
        items=items,
        total=total,
        page=normalized_page,
        per_page=normalized_per_page,
    )


async def list_audit_logs_for_export(
    db: AsyncSession,
    *,
    current_user: User,
    filters: AuditLogFilters | None = None,
) -> list[AuditLog]:
    resolved_filters = filters or AuditLogFilters()
    where_clauses = _build_filters(current_user=current_user, filters=resolved_filters)
    rows = (
        await db.execute(
            select(AuditLog)
            .where(*where_clauses)
            .order_by(AuditLog.timestamp.asc(), AuditLog.id.asc())
        )
    ).scalars().all()
    return list(rows)

