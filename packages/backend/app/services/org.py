from __future__ import annotations

import datetime
import hashlib
import secrets
from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import settings
from app.models.audit_log import AuditLog, AuditLogAction
from app.models.organization import Organization
from app.models.user import User, UserRole, UserStatus
from app.schemas.org import CreateOrganizationRequest, InviteUserRequest
from app.security.password import argon2_hasher
from app.security.tokens import issue_invitation_token
from app.services.email import InvitationEmailSender


class OrganizationAccessError(Exception):
    pass


class InviteUserConflictError(Exception):
    pass


def _normalize_uuid(value: object) -> str:
    return str(value).replace("-", "").lower()


def _uuid_match(column: object, value: object):
    return func.lower(func.replace(column, "-", "")) == _normalize_uuid(value)


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
