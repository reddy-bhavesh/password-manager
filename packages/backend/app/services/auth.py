from __future__ import annotations

from typing import Protocol

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.auth import RegisterRequest
from app.security.password import argon2_hasher


class Hasher(Protocol):
    def hash(self, value: str) -> str: ...


class DuplicateEmailError(Exception):
    pass


def _is_duplicate_email_error(exc: IntegrityError) -> bool:
    if exc.orig is None:
        return False
    message = str(exc.orig).lower()
    return (
        "uq_users_email" in message
        or "duplicate entry" in message
        or "unique constraint failed: users.email" in message
    )


async def register_user(
    db: AsyncSession,
    payload: RegisterRequest,
    hasher: Hasher = argon2_hasher,
) -> User:
    from app.models.organization import Organization  # noqa: F401
    from app.models.user import User, UserRole, UserStatus

    user = User(
        org_id=payload.org_id,
        email=payload.email.strip().lower(),
        name=payload.name.strip(),
        role=UserRole.MEMBER,
        status=UserStatus.ACTIVE,
        public_key=payload.public_key,
        encrypted_private_key=payload.encrypted_private_key,
        auth_verifier_hash=hasher.hash(payload.auth_verifier),
    )

    db.add(user)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if _is_duplicate_email_error(exc):
            raise DuplicateEmailError("email already exists") from exc
        raise

    await db.refresh(user)
    return user
