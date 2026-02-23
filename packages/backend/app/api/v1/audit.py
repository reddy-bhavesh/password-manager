from __future__ import annotations

import csv
import io
import json
import uuid
from collections.abc import Iterator
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import require_admin
from app.core.problems import problem_response
from app.db.session import get_db_session
from app.models.audit_log import AuditLogAction
from app.models.user import User
from app.schemas.audit import AuditLogEntryResponse, AuditLogsPageResponse, SecurityHealthReportResponse
from app.services.audit import (
    AuditLogFilters,
    get_security_health_report,
    list_audit_logs,
    list_audit_logs_for_export,
)


router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


def _build_filters(
    *,
    actor_id: uuid.UUID | None,
    action: AuditLogAction | None,
    start_date: datetime | None,
    end_date: datetime | None,
) -> AuditLogFilters:
    return AuditLogFilters(
        actor_id=actor_id,
        action=action,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/logs", response_model=AuditLogsPageResponse)
async def get_audit_logs(
    actor_id: uuid.UUID | None = Query(default=None),
    action: AuditLogAction | None = Query(default=None),
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> AuditLogsPageResponse:
    try:
        results = await list_audit_logs(
            db,
            current_user=current_user,
            page=page,
            per_page=per_page,
            filters=_build_filters(
                actor_id=actor_id,
                action=action,
                start_date=start_date,
                end_date=end_date,
            ),
        )
    except ValueError as exc:
        return problem_response(
            status=400,
            title="Bad Request",
            detail=str(exc),
            type_="https://vaultguard.dev/errors/invalid-audit-filter",
        )

    return AuditLogsPageResponse(
        items=[AuditLogEntryResponse.from_audit_log(item) for item in results.items],
        total=results.total,
        page=results.page,
        per_page=results.per_page,
    )


def _csv_lines(rows: list[AuditLogEntryResponse]) -> Iterator[str]:
    header = [
        "id",
        "org_id",
        "actor_id",
        "action",
        "target_id",
        "ip_address",
        "user_agent",
        "geo_location",
        "timestamp",
    ]
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    yield buffer.getvalue()
    for row in rows:
        buffer.seek(0)
        buffer.truncate(0)
        writer.writerow(
            [
                str(row.id),
                str(row.org_id),
                str(row.actor_id) if row.actor_id is not None else "",
                row.action,
                str(row.target_id) if row.target_id is not None else "",
                row.ip_address,
                row.user_agent,
                row.geo_location,
                row.timestamp.isoformat(),
            ]
        )
        yield buffer.getvalue()


def _ndjson_lines(rows: list[AuditLogEntryResponse]) -> Iterator[str]:
    for row in rows:
        yield json.dumps(row.model_dump(mode="json"), separators=(",", ":")) + "\n"


@router.get("/logs/export")
async def export_audit_logs(
    format: str = Query(..., alias="format"),
    actor_id: uuid.UUID | None = Query(default=None),
    action: AuditLogAction | None = Query(default=None),
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> StreamingResponse:
    normalized_format = format.strip().lower()
    if normalized_format not in {"csv", "json"}:
        return problem_response(
            status=400,
            title="Bad Request",
            detail="format must be one of: csv, json",
            type_="https://vaultguard.dev/errors/invalid-export-format",
        )

    try:
        logs = await list_audit_logs_for_export(
            db,
            current_user=current_user,
            filters=_build_filters(
                actor_id=actor_id,
                action=action,
                start_date=start_date,
                end_date=end_date,
            ),
        )
    except ValueError as exc:
        return problem_response(
            status=400,
            title="Bad Request",
            detail=str(exc),
            type_="https://vaultguard.dev/errors/invalid-audit-filter",
        )

    rows = [AuditLogEntryResponse.from_audit_log(log) for log in logs]
    if normalized_format == "csv":
        return StreamingResponse(
            _csv_lines(rows),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="audit-logs.csv"'},
        )

    return StreamingResponse(
        _ndjson_lines(rows),
        media_type="application/x-ndjson; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="audit-logs.ndjson"'},
    )


@router.get("/reports/security", response_model=SecurityHealthReportResponse)
async def get_security_report(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> SecurityHealthReportResponse:
    report = await get_security_health_report(
        db,
        current_user=current_user,
    )
    return SecurityHealthReportResponse(
        overall_score=report.overall_score,
        failed_logins_30d=report.failed_logins_30d,
        mfa_adoption_pct=report.mfa_adoption_pct,
        suspended_accounts=report.suspended_accounts,
        over_shared_items=report.over_shared_items,
    )
