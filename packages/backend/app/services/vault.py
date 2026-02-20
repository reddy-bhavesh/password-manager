from __future__ import annotations

import datetime
import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog, AuditLogAction
from app.models.user import User
from app.models.vault_item import VaultItem, VaultItemRevision
from app.schemas.vault import CreateVaultItemRequest, UpdateVaultItemRequest


class VaultItemNotFoundError(Exception):
    pass


class VaultItemForbiddenError(Exception):
    pass


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _normalize_uuid(value: object) -> str:
    return str(value).replace("-", "").lower()


async def _get_active_item_in_org(
    db: AsyncSession,
    *,
    item_id: uuid.UUID,
    org_id: uuid.UUID,
) -> VaultItem | None:
    result = await db.execute(
        select(VaultItem).where(
            VaultItem.id == item_id,
            VaultItem.org_id == org_id,
            VaultItem.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


def _ensure_owner_access(item: VaultItem, *, user_id: uuid.UUID) -> None:
    if _normalize_uuid(item.owner_id) != _normalize_uuid(user_id):
        raise VaultItemForbiddenError


async def _create_audit_log(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    actor_id: uuid.UUID,
    action: AuditLogAction,
    target_id: uuid.UUID,
    client_ip: str,
    user_agent: str,
    now: datetime.datetime,
) -> None:
    db.add(
        AuditLog(
            org_id=org_id,
            actor_id=actor_id,
            action=action,
            target_id=target_id,
            ip_address=client_ip,
            user_agent=user_agent,
            geo_location="unknown",
            timestamp=now,
        )
    )


async def create_vault_item(
    db: AsyncSession,
    *,
    current_user: User,
    payload: CreateVaultItemRequest,
    client_ip: str,
    user_agent: str,
    now: datetime.datetime | None = None,
) -> VaultItem:
    created_at = now or _utc_now()
    item = VaultItem(
        owner_id=current_user.id,
        org_id=current_user.org_id,
        type=payload.type,
        encrypted_data=payload.encrypted_data,
        encrypted_key=payload.encrypted_key,
        name=payload.name.strip(),
        folder_id=payload.folder_id,
    )
    db.add(item)
    await db.flush()
    await _create_audit_log(
        db,
        org_id=current_user.org_id,
        actor_id=current_user.id,
        action=AuditLogAction.CREATE_ITEM,
        target_id=item.id,
        client_ip=client_ip,
        user_agent=user_agent,
        now=created_at,
    )
    await db.commit()
    await db.refresh(item)
    return item


async def get_vault_item(
    db: AsyncSession,
    *,
    current_user: User,
    item_id: uuid.UUID,
    client_ip: str,
    user_agent: str,
    now: datetime.datetime | None = None,
) -> VaultItem:
    viewed_at = now or _utc_now()
    item = await _get_active_item_in_org(db, item_id=item_id, org_id=current_user.org_id)
    if item is None:
        raise VaultItemNotFoundError
    _ensure_owner_access(item, user_id=current_user.id)
    await _create_audit_log(
        db,
        org_id=current_user.org_id,
        actor_id=current_user.id,
        action=AuditLogAction.VIEW_ITEM,
        target_id=item.id,
        client_ip=client_ip,
        user_agent=user_agent,
        now=viewed_at,
    )
    await db.commit()
    await db.refresh(item)
    return item


async def update_vault_item(
    db: AsyncSession,
    *,
    current_user: User,
    item_id: uuid.UUID,
    payload: UpdateVaultItemRequest,
    client_ip: str,
    user_agent: str,
    now: datetime.datetime | None = None,
) -> VaultItem:
    updated_at = now or _utc_now()
    item = await _get_active_item_in_org(db, item_id=item_id, org_id=current_user.org_id)
    if item is None:
        raise VaultItemNotFoundError
    _ensure_owner_access(item, user_id=current_user.id)

    revision_number_result = await db.execute(
        select(func.max(VaultItemRevision.revision_number)).where(VaultItemRevision.item_id == item.id)
    )
    max_revision_number = revision_number_result.scalar_one_or_none()
    next_revision_number = 1 if max_revision_number is None else int(max_revision_number) + 1

    db.add(
        VaultItemRevision(
            item_id=item.id,
            encrypted_data=item.encrypted_data,
            encrypted_key=item.encrypted_key,
            revision_number=next_revision_number,
            created_at=updated_at,
        )
    )
    await db.flush()

    item.type = payload.type
    item.encrypted_data = payload.encrypted_data
    item.encrypted_key = payload.encrypted_key
    item.name = payload.name.strip()
    item.folder_id = payload.folder_id
    item.updated_at = updated_at

    prune_result = await db.execute(
        select(VaultItemRevision.id)
        .where(VaultItemRevision.item_id == item.id)
        .order_by(VaultItemRevision.revision_number.desc())
        .offset(10)
    )
    stale_revision_ids = list(prune_result.scalars().all())
    if stale_revision_ids:
        await db.execute(delete(VaultItemRevision).where(VaultItemRevision.id.in_(stale_revision_ids)))

    await _create_audit_log(
        db,
        org_id=current_user.org_id,
        actor_id=current_user.id,
        action=AuditLogAction.EDIT_ITEM,
        target_id=item.id,
        client_ip=client_ip,
        user_agent=user_agent,
        now=updated_at,
    )
    await db.commit()
    await db.refresh(item)
    return item


async def soft_delete_vault_item(
    db: AsyncSession,
    *,
    current_user: User,
    item_id: uuid.UUID,
    client_ip: str,
    user_agent: str,
    now: datetime.datetime | None = None,
) -> None:
    deleted_at = now or _utc_now()
    item = await _get_active_item_in_org(db, item_id=item_id, org_id=current_user.org_id)
    if item is None:
        raise VaultItemNotFoundError
    _ensure_owner_access(item, user_id=current_user.id)

    item.deleted_at = deleted_at
    item.updated_at = deleted_at
    await _create_audit_log(
        db,
        org_id=current_user.org_id,
        actor_id=current_user.id,
        action=AuditLogAction.DELETE_ITEM,
        target_id=item.id,
        client_ip=client_ip,
        user_agent=user_agent,
        now=deleted_at,
    )
    await db.commit()
