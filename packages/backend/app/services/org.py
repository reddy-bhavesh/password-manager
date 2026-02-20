from __future__ import annotations

from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.models.user import User, UserRole
from app.schemas.org import CreateOrganizationRequest


class OrganizationAccessError(Exception):
    pass


def _normalize_uuid(value: object) -> str:
    return str(value).replace("-", "").lower()


def _uuid_match(column: object, value: object):
    return func.lower(func.replace(column, "-", "")) == _normalize_uuid(value)


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
