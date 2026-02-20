from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.exc import IntegrityError

from app.schemas.auth import RegisterRequest
from app.services.auth import DuplicateEmailError, register_user


class FakeHasher:
    def hash(self, value: str) -> str:
        return f"hashed::{value}"


@pytest.mark.asyncio
async def test_register_user_happy_path() -> None:
    session = AsyncMock()
    session.add = Mock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()

    payload = RegisterRequest(
        email="user@example.com",
        name="Test User",
        org_id=uuid.uuid4(),
        auth_verifier="SuperSecretVerifier",
        public_key="public-key",
        encrypted_private_key="encrypted-private-key",
    )

    user = await register_user(session, payload, hasher=FakeHasher())

    session.add.assert_called_once()
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(user)
    assert user.email == "user@example.com"
    assert user.auth_verifier_hash == "hashed::SuperSecretVerifier"


@pytest.mark.asyncio
async def test_register_user_duplicate_email_raises_conflict_error() -> None:
    session = AsyncMock()
    session.add = Mock()
    session.commit = AsyncMock(
        side_effect=IntegrityError(
            statement="INSERT INTO users (...) VALUES (...)",
            params={},
            orig=Exception("UNIQUE constraint failed: users.email"),
        )
    )
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()

    payload = RegisterRequest(
        email="duplicate@example.com",
        name="Duplicate",
        org_id=uuid.uuid4(),
        auth_verifier="AnotherSecretVerifier",
        public_key="public-key",
        encrypted_private_key="encrypted-private-key",
    )

    with pytest.raises(DuplicateEmailError):
        await register_user(session, payload, hasher=FakeHasher())

    session.rollback.assert_awaited_once()
