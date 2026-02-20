from __future__ import annotations

import datetime
import uuid

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog, AuditLogAction
from app.models.folder import Folder
from app.models.user import User
from app.models.vault_item import VaultItem, VaultItemRevision
from app.schemas.vault import (
    CreateFolderRequest,
    CreateVaultItemRequest,
    FolderTreeNode,
    UpdateFolderRequest,
    UpdateVaultItemRequest,
)


class VaultItemNotFoundError(Exception):
    pass


class VaultItemForbiddenError(Exception):
    pass


class VaultItemRevisionNotFoundError(Exception):
    pass


class FolderNotFoundError(Exception):
    pass


class FolderForbiddenError(Exception):
    pass


class ParentFolderNotFoundError(Exception):
    pass


class FolderInvalidMoveError(Exception):
    pass


class FolderNoFieldsToUpdateError(Exception):
    pass


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _normalize_uuid(value: object) -> str:
    return str(value).replace("-", "").lower()


def _uuid_match(column: object, value: object):
    return func.lower(func.replace(column, "-", "")) == _normalize_uuid(value)


def _to_utc_datetime(value: object) -> datetime.datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=datetime.UTC)
        return value.astimezone(datetime.UTC)
    if isinstance(value, str):
        normalized = value.strip().replace("Z", "+00:00")
        parsed = datetime.datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=datetime.UTC)
        return parsed.astimezone(datetime.UTC)
    raise TypeError("Unsupported datetime value for vault revision counter.")


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


async def _get_folder_in_org(
    db: AsyncSession,
    *,
    folder_id: uuid.UUID,
    org_id: uuid.UUID,
) -> Folder | None:
    result = await db.execute(
        select(Folder).where(
            Folder.id == folder_id,
            Folder.org_id == org_id,
        )
    )
    return result.scalar_one_or_none()


def _ensure_owner_access(item: VaultItem, *, user_id: uuid.UUID) -> None:
    if _normalize_uuid(item.owner_id) != _normalize_uuid(user_id):
        raise VaultItemForbiddenError


def _ensure_folder_owner_access(folder: Folder, *, user_id: uuid.UUID) -> None:
    if _normalize_uuid(folder.owner_id) != _normalize_uuid(user_id):
        raise FolderForbiddenError


def _build_folder_tree(folders: list[Folder]) -> list[FolderTreeNode]:
    nodes_by_id: dict[str, FolderTreeNode] = {}
    child_ids_by_parent: dict[str, list[str]] = {}
    root_ids: list[str] = []

    def _key(folder_id: uuid.UUID) -> str:
        return _normalize_uuid(folder_id)

    for folder in sorted(folders, key=lambda value: (value.name.lower(), str(value.id))):
        folder_key = _key(folder.id)
        node = FolderTreeNode(
            id=folder.id,
            name=folder.name,
            parent_folder_id=folder.parent_folder_id,
            created_at=folder.created_at,
            children=[],
        )
        nodes_by_id[folder_key] = node
        if folder.parent_folder_id is None:
            root_ids.append(folder_key)
            continue
        parent_key = _key(folder.parent_folder_id)
        child_ids_by_parent.setdefault(parent_key, []).append(folder_key)

    for parent_key, child_keys in child_ids_by_parent.items():
        parent_node = nodes_by_id.get(parent_key)
        if parent_node is None:
            root_ids.extend(child_keys)
            continue
        for child_key in child_keys:
            child_node = nodes_by_id.get(child_key)
            if child_node is not None:
                parent_node.children.append(child_node)

    seen: set[str] = set()
    ordered_roots: list[FolderTreeNode] = []
    for root_key in root_ids:
        if root_key in seen:
            continue
        root_node = nodes_by_id.get(root_key)
        if root_node is not None:
            seen.add(root_key)
            ordered_roots.append(root_node)
    return ordered_roots


async def create_folder(
    db: AsyncSession,
    *,
    current_user: User,
    payload: CreateFolderRequest,
) -> Folder:
    parent_folder_id = payload.parent_folder_id
    if parent_folder_id is not None:
        parent_folder = await _get_folder_in_org(
            db,
            folder_id=parent_folder_id,
            org_id=current_user.org_id,
        )
        if parent_folder is None:
            raise ParentFolderNotFoundError
        _ensure_folder_owner_access(parent_folder, user_id=current_user.id)

    folder = Folder(
        org_id=current_user.org_id,
        owner_id=current_user.id,
        parent_folder_id=parent_folder_id,
        name=payload.name.strip(),
    )
    db.add(folder)
    await db.commit()
    await db.refresh(folder)
    return folder


async def list_folders_tree(
    db: AsyncSession,
    *,
    current_user: User,
) -> list[FolderTreeNode]:
    result = await db.execute(
        select(Folder)
        .where(
            _uuid_match(Folder.owner_id, current_user.id),
            _uuid_match(Folder.org_id, current_user.org_id),
        )
        .order_by(Folder.created_at.asc(), Folder.id.asc())
    )
    folders = list(result.scalars().all())
    return _build_folder_tree(folders)


async def update_folder(
    db: AsyncSession,
    *,
    current_user: User,
    folder_id: uuid.UUID,
    payload: UpdateFolderRequest,
) -> Folder:
    folder = await _get_folder_in_org(db, folder_id=folder_id, org_id=current_user.org_id)
    if folder is None:
        raise FolderNotFoundError
    _ensure_folder_owner_access(folder, user_id=current_user.id)

    has_name_update = "name" in payload.model_fields_set
    has_parent_update = "parent_folder_id" in payload.model_fields_set
    if not has_name_update and not has_parent_update:
        raise FolderNoFieldsToUpdateError

    if has_name_update and payload.name is not None:
        next_name = payload.name.strip()
    else:
        next_name = None

    if has_parent_update:
        next_parent_id = payload.parent_folder_id
        if next_parent_id is not None:
            if _normalize_uuid(next_parent_id) == _normalize_uuid(folder.id):
                raise FolderInvalidMoveError
            parent_folder = await _get_folder_in_org(
                db,
                folder_id=next_parent_id,
                org_id=current_user.org_id,
            )
            if parent_folder is None:
                raise ParentFolderNotFoundError
            _ensure_folder_owner_access(parent_folder, user_id=current_user.id)
            ancestor_id = parent_folder.parent_folder_id
            while ancestor_id is not None:
                if _normalize_uuid(ancestor_id) == _normalize_uuid(folder.id):
                    raise FolderInvalidMoveError
                ancestor_folder = await _get_folder_in_org(
                    db,
                    folder_id=ancestor_id,
                    org_id=current_user.org_id,
                )
                if ancestor_folder is None:
                    break
                ancestor_id = ancestor_folder.parent_folder_id
    else:
        next_parent_id = folder.parent_folder_id

    if next_name is not None:
        folder.name = next_name
    if has_parent_update:
        folder.parent_folder_id = next_parent_id

    await db.commit()
    await db.refresh(folder)
    return folder


async def delete_folder(
    db: AsyncSession,
    *,
    current_user: User,
    folder_id: uuid.UUID,
) -> None:
    folder = await _get_folder_in_org(db, folder_id=folder_id, org_id=current_user.org_id)
    if folder is None:
        raise FolderNotFoundError
    _ensure_folder_owner_access(folder, user_id=current_user.id)

    await db.execute(
        update(Folder)
        .where(
            _uuid_match(Folder.parent_folder_id, folder.id),
            _uuid_match(Folder.owner_id, current_user.id),
            _uuid_match(Folder.org_id, current_user.org_id),
        )
        .values(parent_folder_id=None)
    )

    await db.execute(
        update(VaultItem)
        .where(
            _uuid_match(VaultItem.folder_id, folder.id),
            _uuid_match(VaultItem.owner_id, current_user.id),
            _uuid_match(VaultItem.org_id, current_user.org_id),
        )
        .values(folder_id=None)
    )

    await db.delete(folder)
    await db.commit()


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

    await _prune_item_revisions(db, item_id=item.id, keep_last=10)

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


async def list_vault_item_history(
    db: AsyncSession,
    *,
    current_user: User,
    item_id: uuid.UUID,
) -> list[VaultItemRevision]:
    item = await _get_active_item_in_org(db, item_id=item_id, org_id=current_user.org_id)
    if item is None:
        raise VaultItemNotFoundError
    _ensure_owner_access(item, user_id=current_user.id)

    revisions_result = await db.execute(
        select(VaultItemRevision)
        .where(VaultItemRevision.item_id == item.id)
        .order_by(VaultItemRevision.revision_number.asc())
    )
    return list(revisions_result.scalars().all())


async def restore_vault_item_revision(
    db: AsyncSession,
    *,
    current_user: User,
    item_id: uuid.UUID,
    revision_number: int,
    client_ip: str,
    user_agent: str,
    now: datetime.datetime | None = None,
) -> VaultItem:
    restored_at = now or _utc_now()
    item = await _get_active_item_in_org(db, item_id=item_id, org_id=current_user.org_id)
    if item is None:
        raise VaultItemNotFoundError
    _ensure_owner_access(item, user_id=current_user.id)

    target_revision_result = await db.execute(
        select(VaultItemRevision).where(
            VaultItemRevision.item_id == item.id,
            VaultItemRevision.revision_number == revision_number,
        )
    )
    target_revision = target_revision_result.scalar_one_or_none()
    if target_revision is None:
        raise VaultItemRevisionNotFoundError

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
            created_at=restored_at,
        )
    )
    await db.flush()

    item.encrypted_data = target_revision.encrypted_data
    item.encrypted_key = target_revision.encrypted_key
    item.updated_at = restored_at

    await _prune_item_revisions(db, item_id=item.id, keep_last=10)
    await _create_audit_log(
        db,
        org_id=current_user.org_id,
        actor_id=current_user.id,
        action=AuditLogAction.RESTORE_ITEM,
        target_id=item.id,
        client_ip=client_ip,
        user_agent=user_agent,
        now=restored_at,
    )
    await db.commit()
    await db.refresh(item)
    return item


async def list_vault_items(
    db: AsyncSession,
    *,
    current_user: User,
    limit: int,
    offset: int,
) -> tuple[list[VaultItem], int]:
    total_result = await db.execute(
        select(func.count(VaultItem.id)).where(
            _uuid_match(VaultItem.owner_id, current_user.id),
            _uuid_match(VaultItem.org_id, current_user.org_id),
            VaultItem.deleted_at.is_(None),
        )
    )
    total = int(total_result.scalar_one() or 0)

    result = await db.execute(
        select(VaultItem)
        .where(
            _uuid_match(VaultItem.owner_id, current_user.id),
            _uuid_match(VaultItem.org_id, current_user.org_id),
            VaultItem.deleted_at.is_(None),
        )
        .order_by(VaultItem.updated_at.desc(), VaultItem.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all()), total


async def list_vault_items_since(
    db: AsyncSession,
    *,
    current_user: User,
    since: datetime.datetime,
    limit: int,
    offset: int,
) -> tuple[list[VaultItem], int]:
    result = await db.execute(
        select(VaultItem)
        .where(
            _uuid_match(VaultItem.owner_id, current_user.id),
            _uuid_match(VaultItem.org_id, current_user.org_id),
            VaultItem.deleted_at.is_(None),
        )
        .order_by(VaultItem.updated_at.asc(), VaultItem.id.asc())
    )
    filtered_items: list[VaultItem] = []
    for item in result.scalars().all():
        updated_at = _to_utc_datetime(item.updated_at)
        if updated_at is not None and updated_at > since:
            filtered_items.append(item)
    total = len(filtered_items)
    return filtered_items[offset : offset + limit], total


async def get_vault_revision_counter(
    db: AsyncSession,
    *,
    current_user: User,
) -> int:
    result = await db.execute(
        select(func.max(VaultItem.updated_at)).where(
            _uuid_match(VaultItem.owner_id, current_user.id),
            _uuid_match(VaultItem.org_id, current_user.org_id),
        )
    )
    latest_update = _to_utc_datetime(result.scalar_one_or_none())
    if latest_update is None:
        return 0
    return int(latest_update.timestamp() * 1_000_000)


async def _prune_item_revisions(
    db: AsyncSession,
    *,
    item_id: uuid.UUID,
    keep_last: int,
) -> None:
    prune_result = await db.execute(
        select(VaultItemRevision.id)
        .where(VaultItemRevision.item_id == item_id)
        .order_by(VaultItemRevision.revision_number.desc())
        .offset(keep_last)
    )
    stale_revision_ids = list(prune_result.scalars().all())
    if stale_revision_ids:
        await db.execute(delete(VaultItemRevision).where(VaultItemRevision.id.in_(stale_revision_ids)))
