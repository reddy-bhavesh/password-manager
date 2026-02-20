from __future__ import annotations

import datetime
import uuid
from unittest.mock import AsyncMock, Mock

import pytest

from app.models.auth_session import Session
from app.models.user import User, UserRole, UserStatus
from app.security.tokens import issue_access_token
from app.services.auth import (
    InvalidRefreshTokenError,
    SessionNotFoundError,
    refresh_tokens,
    revoke_session_by_id,
    revoke_session_by_refresh_token,
)


class _FakeResult:
    def __init__(self, value) -> None:
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeScalars:
    def __init__(self, values) -> None:
        self._values = values

    def all(self):
        return self._values


class _FakeUserListResult:
    def __init__(self, users) -> None:
        self._users = users

    def scalars(self):
        return _FakeScalars(self._users)


def _make_user() -> User:
    return User(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        email="unit@example.com",
        name="Unit User",
        role=UserRole.MEMBER,
        status=UserStatus.ACTIVE,
        public_key="pk",
        encrypted_private_key="enc-pk",
        auth_verifier_hash="hash",
    )


@pytest.mark.asyncio
async def test_refresh_tokens_rejects_invalid_token() -> None:
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_FakeResult(None))

    with pytest.raises(InvalidRefreshTokenError):
        await refresh_tokens(
            db,
            "invalid-refresh-token",
            client_ip="127.0.0.1",
            user_agent="pytest",
        )


@pytest.mark.asyncio
async def test_revoke_session_by_refresh_token_marks_session_revoked() -> None:
    user = _make_user()
    now = datetime.datetime.now(datetime.UTC)
    access_token, _ = issue_access_token(
        user_id=user.id,
        org_id=user.org_id,
        email=user.email,
        role=user.role.value,
        now=now,
    )
    target_session = Session(
        id=uuid.uuid4(),
        user_id=user.id,
        refresh_token_hash="abc",
        device_info={},
        ip_address="127.0.0.1",
        expires_at=now + datetime.timedelta(days=1),
    )

    db = AsyncMock()
    db.add = Mock()
    db.get = AsyncMock(return_value=user)
    db.execute = AsyncMock(
        side_effect=[
            _FakeUserListResult([user]),
            _FakeResult(target_session),
        ]
    )
    db.commit = AsyncMock()

    await revoke_session_by_refresh_token(
        db,
        access_token=access_token,
        refresh_token="example",
        client_ip="127.0.0.1",
        user_agent="pytest",
        now=now,
    )

    assert target_session.revoked_at == now
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_revoke_session_by_id_marks_target_session_revoked() -> None:
    user = _make_user()
    now = datetime.datetime.now(datetime.UTC)
    access_token, _ = issue_access_token(
        user_id=user.id,
        org_id=user.org_id,
        email=user.email,
        role=user.role.value,
        now=now,
    )
    target_session = Session(
        id=uuid.uuid4(),
        user_id=user.id,
        refresh_token_hash="hash",
        device_info={},
        ip_address="127.0.0.1",
        expires_at=now + datetime.timedelta(days=1),
    )

    db = AsyncMock()
    db.add = Mock()
    db.execute = AsyncMock(return_value=_FakeUserListResult([user]))
    db.get = AsyncMock(return_value=target_session)
    db.commit = AsyncMock()

    await revoke_session_by_id(
        db,
        access_token=access_token,
        session_id=target_session.id,
        client_ip="127.0.0.1",
        user_agent="pytest",
        now=now,
    )

    assert target_session.revoked_at == now
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_revoke_session_by_id_raises_when_session_missing() -> None:
    user = _make_user()
    access_token, _ = issue_access_token(
        user_id=user.id,
        org_id=user.org_id,
        email=user.email,
        role=user.role.value,
    )
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_FakeUserListResult([user]))
    db.get = AsyncMock(return_value=None)

    with pytest.raises(SessionNotFoundError):
        await revoke_session_by_id(
            db,
            access_token=access_token,
            session_id=uuid.uuid4(),
            client_ip="127.0.0.1",
            user_agent="pytest",
        )
