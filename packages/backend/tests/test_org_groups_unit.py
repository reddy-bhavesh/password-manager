from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.group import Group
from app.models.user import User, UserRole, UserStatus
from app.schemas.org import AddOrganizationGroupMemberRequest
from app.services.org import (
    OrganizationGroupConflictError,
    OrganizationGroupMemberNotFoundError,
    add_organization_group_member,
    remove_organization_group_member,
)


class _FakeScalarResult:
    def __init__(self, value) -> None:
        self._value = value

    def scalar_one_or_none(self):
        return self._value


def _make_user(*, org_id: uuid.UUID | None = None) -> User:
    return User(
        id=uuid.uuid4(),
        org_id=org_id or uuid.uuid4(),
        email="unit@example.com",
        name="Unit User",
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
        public_key="pk",
        encrypted_private_key="enc",
        auth_verifier_hash="hash",
    )


def _make_group(*, org_id: uuid.UUID) -> Group:
    return Group(
        id=uuid.uuid4(),
        org_id=org_id,
        name="Engineering",
    )


@pytest.mark.asyncio
async def test_add_group_member_raises_conflict_on_duplicate_membership() -> None:
    current_user = _make_user()
    target_user = _make_user(org_id=current_user.org_id)
    group = _make_group(org_id=current_user.org_id)

    db = AsyncMock()
    db.add = Mock()
    db.execute = AsyncMock(
        side_effect=[
            _FakeScalarResult(group),
            _FakeScalarResult(target_user),
        ]
    )
    db.flush = AsyncMock(side_effect=IntegrityError("insert", {}, Exception("duplicate")))
    db.rollback = AsyncMock()

    with pytest.raises(OrganizationGroupConflictError):
        await add_organization_group_member(
            db,
            current_user=current_user,
            group_id=group.id,
            payload=AddOrganizationGroupMemberRequest(user_id=target_user.id),
            client_ip="127.0.0.1",
            user_agent="pytest",
        )

    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_remove_group_member_raises_when_membership_missing() -> None:
    current_user = _make_user()
    group = _make_group(org_id=current_user.org_id)
    missing_user_id = uuid.uuid4()

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _FakeScalarResult(group),
            _FakeScalarResult(None),
        ]
    )

    with pytest.raises(OrganizationGroupMemberNotFoundError):
        await remove_organization_group_member(
            db,
            current_user=current_user,
            group_id=group.id,
            user_id=missing_user_id,
            client_ip="127.0.0.1",
            user_agent="pytest",
        )
