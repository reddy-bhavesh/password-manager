from __future__ import annotations

import datetime
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog, AuditLogAction
from app.models.folder import Collection, CollectionItem, CollectionMember
from app.models.user import User
from app.models.user import UserStatus
from app.models.vault_item import VaultItem


def _normalize_uuid(value: object) -> str:
    return str(value).replace("-", "").lower()


def _uuid_match(column: object, value: object):
    return func.lower(func.replace(column, "-", "")) == _normalize_uuid(value)


def _uuid_columns_match(left_column: object, right_column: object):
    return func.lower(func.replace(left_column, "-", "")) == func.lower(func.replace(right_column, "-", ""))


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


@dataclass(frozen=True)
class SecurityHealthReport:
    overall_score: int
    failed_logins_30d: int
    mfa_adoption_pct: int
    suspended_accounts: int
    over_shared_items: int


OVER_SHARED_ITEM_MEMBERSHIP_THRESHOLD = 5


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


def calculate_security_health_score(
    *,
    failed_logins_30d: int,
    mfa_adoption_pct: int,
    suspended_accounts: int,
    over_shared_items: int,
) -> int:
    normalized_mfa_pct = max(0, min(100, int(mfa_adoption_pct)))
    deductions = 0
    deductions += min(max(failed_logins_30d, 0) * 2, 30)
    deductions += round((100 - normalized_mfa_pct) * 0.4)
    deductions += min(max(suspended_accounts, 0) * 5, 20)
    deductions += min(max(over_shared_items, 0) * 10, 20)
    return max(0, min(100, 100 - deductions))


def _now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


async def get_security_health_report(
    db: AsyncSession,
    *,
    current_user: User,
    now: datetime.datetime | None = None,
) -> SecurityHealthReport:
    current_time = now or _now_utc()
    cutoff = current_time - datetime.timedelta(days=30)
    org_clause = _uuid_match(User.org_id, current_user.org_id)

    failed_logins_30d = int(
        (
            await db.execute(
                select(func.count())
                .select_from(AuditLog)
                .where(
                    _uuid_match(AuditLog.org_id, current_user.org_id),
                    AuditLog.action == AuditLogAction.FAILED_LOGIN,
                    AuditLog.timestamp >= cutoff,
                )
            )
        ).scalar_one()
    )

    active_users = int(
        (
            await db.execute(
                select(func.count())
                .select_from(User)
                .where(
                    org_clause,
                    User.status == UserStatus.ACTIVE,
                )
            )
        ).scalar_one()
    )
    mfa_enabled_active_users = int(
        (
            await db.execute(
                select(func.count())
                .select_from(User)
                .where(
                    org_clause,
                    User.status == UserStatus.ACTIVE,
                    User.mfa_enabled.is_(True),
                )
            )
        ).scalar_one()
    )
    mfa_adoption_pct = 0 if active_users == 0 else int(round((mfa_enabled_active_users / active_users) * 100))

    suspended_accounts = int(
        (
            await db.execute(
                select(func.count())
                .select_from(User)
                .where(
                    org_clause,
                    User.status == UserStatus.SUSPENDED,
                )
            )
        ).scalar_one()
    )

    over_shared_items_subquery = (
        select(CollectionItem.item_id.label("item_id"))
        .select_from(CollectionItem)
        .join(Collection, _uuid_columns_match(Collection.id, CollectionItem.collection_id))
        .join(CollectionMember, _uuid_columns_match(CollectionMember.collection_id, Collection.id))
        .join(VaultItem, _uuid_columns_match(VaultItem.id, CollectionItem.item_id))
        .where(
            _uuid_match(Collection.org_id, current_user.org_id),
            _uuid_match(VaultItem.org_id, current_user.org_id),
            VaultItem.deleted_at.is_(None),
        )
        .group_by(CollectionItem.item_id)
        .having(func.count(CollectionMember.user_or_group_id) > OVER_SHARED_ITEM_MEMBERSHIP_THRESHOLD)
        .subquery()
    )
    over_shared_items = int(
        (
            await db.execute(
                select(func.count()).select_from(over_shared_items_subquery)
            )
        ).scalar_one()
    )

    overall_score = calculate_security_health_score(
        failed_logins_30d=failed_logins_30d,
        mfa_adoption_pct=mfa_adoption_pct,
        suspended_accounts=suspended_accounts,
        over_shared_items=over_shared_items,
    )
    return SecurityHealthReport(
        overall_score=overall_score,
        failed_logins_30d=failed_logins_30d,
        mfa_adoption_pct=mfa_adoption_pct,
        suspended_accounts=suspended_accounts,
        over_shared_items=over_shared_items,
    )
