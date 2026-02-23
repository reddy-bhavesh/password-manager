from __future__ import annotations

import datetime
import hashlib
import secrets
from dataclasses import dataclass

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import settings
from app.models.audit_log import AuditLog, AuditLogAction
from app.models.auth_session import Session
from app.models.folder import Collection, CollectionItem, CollectionMember, CollectionPermission
from app.models.group import Group, GroupMember
from app.models.organization import Organization
from app.models.user import User, UserRole, UserStatus
from app.models.vault_item import VaultItem
from app.schemas.org import (
    AddCollectionItemRequest,
    AddCollectionMemberRequest,
    AddOrganizationGroupMemberRequest,
    CreateCollectionRequest,
    CreateOrganizationGroupRequest,
    CreateOrganizationRequest,
    InviteUserRequest,
    UpdateOrganizationUserRoleRequest,
)
from app.security.password import argon2_hasher
from app.security.tokens import issue_invitation_token
from app.services.email import InvitationEmailSender


class OrganizationAccessError(Exception):
    pass


class InviteUserConflictError(Exception):
    pass


class OrganizationUserNotFoundError(Exception):
    pass


class OrganizationUserConflictError(Exception):
    pass


class OrganizationGroupNotFoundError(Exception):
    pass


class OrganizationGroupConflictError(Exception):
    pass


class OrganizationGroupMemberNotFoundError(Exception):
    pass


class OrganizationCollectionNotFoundError(Exception):
    pass


class OrganizationCollectionMemberConflictError(Exception):
    pass


class OrganizationCollectionMemberNotFoundError(Exception):
    pass


class OrganizationCollectionTargetNotFoundError(Exception):
    pass


class OrganizationCollectionItemConflictError(Exception):
    pass


class OrganizationVaultItemNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class OrganizationUserListPage:
    users: list[User]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True)
class OrganizationGroupListItem:
    group: Group
    member_count: int


def _normalize_uuid(value: object) -> str:
    return str(value).replace("-", "").lower()


def _uuid_match(column: object, value: object):
    return func.lower(func.replace(column, "-", "")) == _normalize_uuid(value)


def _uuid_columns_match(left_column: object, right_column: object):
    return func.lower(func.replace(left_column, "-", "")) == func.lower(func.replace(right_column, "-", ""))


def _now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _invited_placeholder_name(email: str) -> str:
    local = email.split("@", maxsplit=1)[0].strip()
    return local if local else "Invited User"


async def _append_audit_log(
    db: AsyncSession,
    *,
    org_id,
    actor_id,
    action: AuditLogAction,
    target_id,
    ip_address: str,
    user_agent: str,
) -> None:
    db.add(
        AuditLog(
            org_id=org_id,
            actor_id=actor_id,
            action=action,
            target_id=target_id,
            ip_address=ip_address,
            user_agent=user_agent,
            geo_location="unknown",
        )
    )


async def create_organization(
    db: AsyncSession,
    *,
    current_user: User,
    payload: CreateOrganizationRequest,
) -> Organization:
    organization = Organization(
        name=payload.name.strip(),
        subscription_tier=payload.subscription_tier.strip(),
        settings=dict(payload.settings),
    )
    db.add(organization)
    await db.flush()

    await db.execute(
        update(User)
        .where(_uuid_match(User.id, current_user.id))
        .values(org_id=organization.id, role=UserRole.OWNER)
    )

    await db.commit()
    await db.refresh(organization)
    return organization


async def get_current_organization(
    db: AsyncSession,
    *,
    current_user: User,
) -> Organization:
    organization = await db.get(Organization, current_user.org_id)
    if organization is None:
        raise OrganizationAccessError("organization not found for current user")
    return organization


async def invite_user(
    db: AsyncSession,
    *,
    current_user: User,
    payload: InviteUserRequest,
    email_sender: InvitationEmailSender,
    client_ip: str,
    user_agent: str,
    now: datetime.datetime | None = None,
) -> User:
    current_time = now or _now_utc()
    normalized_email = payload.email.strip().lower()
    role = UserRole(payload.role)
    invited_user = User(
        org_id=current_user.org_id,
        email=normalized_email,
        name=_invited_placeholder_name(normalized_email),
        role=role,
        status=UserStatus.INVITED,
        public_key="",
        encrypted_private_key="",
        auth_verifier_hash=argon2_hasher.hash(secrets.token_urlsafe(32)),
    )
    db.add(invited_user)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise InviteUserConflictError("user with email already exists") from exc

    invitation_token, expires_at = issue_invitation_token(
        user_id=invited_user.id,
        org_id=invited_user.org_id,
        email=invited_user.email,
        role=invited_user.role.value,
        now=current_time,
        expires_in=datetime.timedelta(days=settings.invitation_token_ttl_days),
    )
    invited_user.invitation_token_hash = hashlib.sha256(invitation_token.encode("utf-8")).hexdigest()
    invited_user.invitation_expires_at = expires_at

    await _append_audit_log(
        db,
        org_id=current_user.org_id,
        actor_id=current_user.id,
        action=AuditLogAction.INVITE_USER,
        target_id=invited_user.id,
        ip_address=client_ip,
        user_agent=user_agent,
    )
    await db.commit()
    await db.refresh(invited_user)

    invitation_link = f"{settings.invitation_link_base_url}?token={invitation_token}"
    await email_sender.send_invitation(
        recipient_email=invited_user.email,
        invitation_link=invitation_link,
    )
    return invited_user


async def list_organization_users(
    db: AsyncSession,
    *,
    current_user: User,
    limit: int = 50,
    offset: int = 0,
    role: str | None = None,
    status: str | None = None,
) -> OrganizationUserListPage:
    normalized_limit = max(1, min(limit, 100))
    normalized_offset = max(0, offset)

    filters = [_uuid_match(User.org_id, current_user.org_id)]
    if role is not None:
        filters.append(User.role == UserRole(role))
    if status is not None:
        filters.append(User.status == UserStatus(status))

    total_query = select(func.count()).select_from(User).where(*filters)
    total = int((await db.execute(total_query)).scalar_one())

    users_query = (
        select(User)
        .where(*filters)
        .order_by(User.created_at.asc(), User.email.asc())
        .limit(normalized_limit)
        .offset(normalized_offset)
    )
    users = list((await db.execute(users_query)).scalars().all())
    return OrganizationUserListPage(
        users=users,
        total=total,
        limit=normalized_limit,
        offset=normalized_offset,
    )


async def change_organization_user_role(
    db: AsyncSession,
    *,
    current_user: User,
    user_id,
    payload: UpdateOrganizationUserRoleRequest,
    client_ip: str,
    user_agent: str,
) -> User:
    target_user = await _get_org_user_or_raise(db, org_id=current_user.org_id, user_id=user_id)
    if target_user.role == UserRole.OWNER:
        raise OrganizationUserConflictError("owner role cannot be changed")
    new_role = UserRole(payload.role)
    await db.execute(
        update(User)
        .where(_uuid_match(User.id, target_user.id))
        .values(role=new_role)
    )
    await _append_audit_log(
        db,
        org_id=current_user.org_id,
        actor_id=current_user.id,
        action=AuditLogAction.CHANGE_USER_ROLE,
        target_id=target_user.id,
        ip_address=client_ip,
        user_agent=user_agent,
    )
    await db.commit()
    return await _get_org_user_or_raise(db, org_id=current_user.org_id, user_id=target_user.id)


async def offboard_organization_user(
    db: AsyncSession,
    *,
    current_user: User,
    user_id,
    client_ip: str,
    user_agent: str,
    now: datetime.datetime | None = None,
) -> None:
    current_time = now or _now_utc()
    target_user = await _get_org_user_or_raise(db, org_id=current_user.org_id, user_id=user_id)
    if target_user.role == UserRole.OWNER:
        raise OrganizationUserConflictError("owner cannot be offboarded")

    await db.execute(
        update(User)
        .where(_uuid_match(User.id, target_user.id))
        .values(status=UserStatus.SUSPENDED)
    )
    await db.execute(
        update(Session)
        .where(
            _uuid_match(Session.user_id, target_user.id),
            Session.revoked_at.is_(None),
        )
        .values(revoked_at=current_time)
    )
    await _append_audit_log(
        db,
        org_id=current_user.org_id,
        actor_id=current_user.id,
        action=AuditLogAction.OFFBOARD_USER,
        target_id=target_user.id,
        ip_address=client_ip,
        user_agent=user_agent,
    )
    await db.commit()


async def create_organization_group(
    db: AsyncSession,
    *,
    current_user: User,
    payload: CreateOrganizationGroupRequest,
    client_ip: str,
    user_agent: str,
) -> Group:
    group = Group(
        org_id=current_user.org_id,
        name=payload.name.strip(),
    )
    db.add(group)
    await db.flush()
    await _append_audit_log(
        db,
        org_id=current_user.org_id,
        actor_id=current_user.id,
        action=AuditLogAction.CREATE_GROUP,
        target_id=group.id,
        ip_address=client_ip,
        user_agent=user_agent,
    )
    await db.commit()
    await db.refresh(group)
    return group


async def list_organization_groups(
    db: AsyncSession,
    *,
    current_user: User,
) -> list[OrganizationGroupListItem]:
    rows = (
        await db.execute(
            select(
                Group,
                func.count(GroupMember.user_id).label("member_count"),
            )
            .outerjoin(GroupMember, GroupMember.group_id == Group.id)
            .where(_uuid_match(Group.org_id, current_user.org_id))
            .group_by(Group.id, Group.org_id, Group.name, Group.created_at)
            .order_by(Group.created_at.asc(), Group.name.asc())
        )
    ).all()
    return [
        OrganizationGroupListItem(group=row[0], member_count=int(row[1] or 0))
        for row in rows
    ]


async def add_organization_group_member(
    db: AsyncSession,
    *,
    current_user: User,
    group_id,
    payload: AddOrganizationGroupMemberRequest,
    client_ip: str,
    user_agent: str,
) -> GroupMember:
    group = await _get_org_group_or_raise(db, org_id=current_user.org_id, group_id=group_id)
    await _get_org_user_or_raise(db, org_id=current_user.org_id, user_id=payload.user_id)

    membership = GroupMember(group_id=group.id, user_id=payload.user_id)
    db.add(membership)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise OrganizationGroupConflictError("user is already a group member") from exc

    await _append_audit_log(
        db,
        org_id=current_user.org_id,
        actor_id=current_user.id,
        action=AuditLogAction.ADD_GROUP_MEMBER,
        target_id=group.id,
        ip_address=client_ip,
        user_agent=user_agent,
    )
    await db.commit()
    return membership


async def remove_organization_group_member(
    db: AsyncSession,
    *,
    current_user: User,
    group_id,
    user_id,
    client_ip: str,
    user_agent: str,
) -> None:
    group = await _get_org_group_or_raise(db, org_id=current_user.org_id, group_id=group_id)
    membership = (
        await db.execute(
            select(GroupMember)
            .join(Group, Group.id == GroupMember.group_id)
            .where(
                _uuid_match(Group.org_id, current_user.org_id),
                _uuid_match(GroupMember.group_id, group_id),
                _uuid_match(GroupMember.user_id, user_id),
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        raise OrganizationGroupMemberNotFoundError("group member not found")

    await db.execute(
        delete(GroupMember).where(
            _uuid_match(GroupMember.group_id, group_id),
            _uuid_match(GroupMember.user_id, user_id),
        )
    )
    await _append_audit_log(
        db,
        org_id=current_user.org_id,
        actor_id=current_user.id,
        action=AuditLogAction.REMOVE_GROUP_MEMBER,
        target_id=group.id,
        ip_address=client_ip,
        user_agent=user_agent,
    )
    await db.commit()


async def create_organization_collection(
    db: AsyncSession,
    *,
    current_user: User,
    payload: CreateCollectionRequest,
) -> Collection:
    collection = Collection(
        org_id=current_user.org_id,
        name=payload.name.strip(),
        created_by=current_user.id,
    )
    db.add(collection)
    await db.flush()

    # Creator gets manage permission by default so the collection is immediately usable.
    db.add(
        CollectionMember(
            collection_id=collection.id,
            user_or_group_id=current_user.id,
            permission=CollectionPermission.MANAGE,
        )
    )
    await db.commit()
    await db.refresh(collection)
    return collection


async def add_collection_member(
    db: AsyncSession,
    *,
    current_user: User,
    collection_id,
    payload: AddCollectionMemberRequest,
) -> CollectionMember:
    collection = await _get_org_collection_or_raise(
        db,
        org_id=current_user.org_id,
        collection_id=collection_id,
    )
    await _ensure_collection_member_target_exists(
        db,
        org_id=current_user.org_id,
        user_or_group_id=payload.user_or_group_id,
    )
    membership = CollectionMember(
        collection_id=collection.id,
        user_or_group_id=payload.user_or_group_id,
        permission=CollectionPermission(payload.permission),
    )
    db.add(membership)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise OrganizationCollectionMemberConflictError("collection member already exists") from exc
    await db.commit()
    return membership


async def remove_collection_member(
    db: AsyncSession,
    *,
    current_user: User,
    collection_id,
    member_id,
) -> None:
    await _get_org_collection_or_raise(
        db,
        org_id=current_user.org_id,
        collection_id=collection_id,
    )
    delete_result = await db.execute(
        delete(CollectionMember).where(
            _uuid_match(CollectionMember.collection_id, collection_id),
            _uuid_match(CollectionMember.user_or_group_id, member_id),
        )
    )
    if int(delete_result.rowcount or 0) == 0:
        await db.rollback()
        raise OrganizationCollectionMemberNotFoundError("collection member not found")
    await db.commit()


async def add_collection_item(
    db: AsyncSession,
    *,
    current_user: User,
    collection_id,
    payload: AddCollectionItemRequest,
) -> CollectionItem:
    collection = await _get_org_collection_or_raise(
        db,
        org_id=current_user.org_id,
        collection_id=collection_id,
    )
    await _get_org_vault_item_or_raise(
        db,
        org_id=current_user.org_id,
        item_id=payload.item_id,
    )

    collection_item = CollectionItem(
        collection_id=collection.id,
        item_id=payload.item_id,
    )
    db.add(collection_item)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise OrganizationCollectionItemConflictError("item already linked to collection") from exc
    await db.commit()
    return collection_item


async def list_collection_items(
    db: AsyncSession,
    *,
    current_user: User,
    collection_id,
) -> list[VaultItem]:
    await _require_collection_read_access(
        db,
        current_user=current_user,
        collection_id=collection_id,
    )
    rows = (
        await db.execute(
            select(VaultItem)
            .join(CollectionItem, _uuid_columns_match(CollectionItem.item_id, VaultItem.id))
            .where(
                _uuid_match(CollectionItem.collection_id, collection_id),
                _uuid_match(VaultItem.org_id, current_user.org_id),
                VaultItem.deleted_at.is_(None),
            )
            .order_by(VaultItem.created_at.asc(), VaultItem.name.asc())
        )
    ).scalars().all()
    return list(rows)


async def _get_org_user_or_raise(db: AsyncSession, *, org_id, user_id) -> User:
    query = select(User).where(
        _uuid_match(User.org_id, org_id),
        _uuid_match(User.id, user_id),
    )
    target_user = (await db.execute(query)).scalar_one_or_none()
    if target_user is None:
        raise OrganizationUserNotFoundError("user not found")
    return target_user


async def _get_org_group_or_raise(db: AsyncSession, *, org_id, group_id) -> Group:
    query = select(Group).where(
        _uuid_match(Group.org_id, org_id),
        _uuid_match(Group.id, group_id),
    )
    group = (await db.execute(query)).scalar_one_or_none()
    if group is None:
        raise OrganizationGroupNotFoundError("group not found")
    return group


async def _get_org_collection_or_raise(db: AsyncSession, *, org_id, collection_id) -> Collection:
    collection = (
        await db.execute(
            select(Collection).where(
                _uuid_match(Collection.org_id, org_id),
                _uuid_match(Collection.id, collection_id),
            )
        )
    ).scalar_one_or_none()
    if collection is None:
        raise OrganizationCollectionNotFoundError("collection not found")
    return collection


async def _ensure_collection_member_target_exists(db: AsyncSession, *, org_id, user_or_group_id) -> None:
    user_match = (
        await db.execute(
            select(User.id).where(
                _uuid_match(User.org_id, org_id),
                _uuid_match(User.id, user_or_group_id),
            )
        )
    ).scalar_one_or_none()
    if user_match is not None:
        return

    group_match = (
        await db.execute(
            select(Group.id).where(
                _uuid_match(Group.org_id, org_id),
                _uuid_match(Group.id, user_or_group_id),
            )
        )
    ).scalar_one_or_none()
    if group_match is not None:
        return
    raise OrganizationCollectionTargetNotFoundError("collection target not found")


async def _get_org_vault_item_or_raise(db: AsyncSession, *, org_id, item_id) -> VaultItem:
    item = (
        await db.execute(
            select(VaultItem).where(
                _uuid_match(VaultItem.org_id, org_id),
                _uuid_match(VaultItem.id, item_id),
                VaultItem.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if item is None:
        raise OrganizationVaultItemNotFoundError("vault item not found")
    return item


async def _require_collection_read_access(
    db: AsyncSession,
    *,
    current_user: User,
    collection_id,
) -> None:
    collection = await _get_org_collection_or_raise(
        db,
        org_id=current_user.org_id,
        collection_id=collection_id,
    )
    subject_ids = [current_user.id]
    group_ids = (
        await db.execute(
            select(GroupMember.group_id)
            .join(Group, _uuid_columns_match(Group.id, GroupMember.group_id))
            .where(
                _uuid_match(Group.org_id, current_user.org_id),
                _uuid_match(GroupMember.user_id, current_user.id),
            )
        )
    ).scalars().all()
    subject_ids.extend(group_ids)

    permission_query = select(CollectionMember.collection_id).where(
        _uuid_match(CollectionMember.collection_id, collection.id),
        or_(*[_uuid_match(CollectionMember.user_or_group_id, subject_id) for subject_id in subject_ids]),
    )
    has_permission = (await db.execute(permission_query)).scalar_one_or_none() is not None
    if not has_permission:
        raise OrganizationAccessError("insufficient collection permissions")
