from __future__ import annotations

import asyncio
import datetime
import hashlib
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Protocol

from argon2.exceptions import VerificationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth_session import Session
from app.models.user import User, UserStatus
from app.schemas.auth import LoginRequest, RegisterRequest
from app.security.password import argon2_hasher
from app.security.tokens import issue_access_token
from app.core.settings import settings


class Hasher(Protocol):
    def hash(self, value: str) -> str: ...

    def verify(self, hash: str, value: str) -> bool: ...


class DuplicateEmailError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class TooManyAttemptsError(Exception):
    pass


@dataclass(frozen=True)
class LoginResult:
    access_token: str
    refresh_token: str
    user: User


MAX_FAILED_ATTEMPTS = 5
FAILED_ATTEMPTS_WINDOW_SECONDS = 60 * 15
MIN_FAILED_LOGIN_RESPONSE_SECONDS = 0.2
DUMMY_AUTH_VERIFIER_HASH = argon2_hasher.hash("vaultguard-dummy-auth-verifier")


class LoginRateLimiter:
    def __init__(self) -> None:
        self._failed_attempts: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def is_rate_limited(self, ip: str, now: float | None = None) -> bool:
        async with self._lock:
            failures = self._prune_and_get(ip, now)
            return len(failures) > MAX_FAILED_ATTEMPTS

    async def register_failure(self, ip: str, now: float | None = None) -> bool:
        async with self._lock:
            failures = self._prune_and_get(ip, now)
            failures.append(now if now is not None else time.monotonic())
            return len(failures) > MAX_FAILED_ATTEMPTS

    async def reset(self, ip: str) -> None:
        async with self._lock:
            self._failed_attempts.pop(ip, None)

    def _prune_and_get(self, ip: str, now: float | None = None) -> deque[float]:
        current = now if now is not None else time.monotonic()
        threshold = current - FAILED_ATTEMPTS_WINDOW_SECONDS
        failures = self._failed_attempts[ip]
        while failures and failures[0] < threshold:
            failures.popleft()
        return failures


login_rate_limiter = LoginRateLimiter()


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
    from app.models.user import UserRole

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


async def login_user(
    db: AsyncSession,
    payload: LoginRequest,
    *,
    client_ip: str,
    user_agent: str,
    hasher: Hasher = argon2_hasher,
    now: datetime.datetime | None = None,
) -> LoginResult:
    if await login_rate_limiter.is_rate_limited(client_ip):
        raise TooManyAttemptsError("too many failed attempts")

    started = time.monotonic()
    normalized_email = payload.email.strip().lower()
    query = select(User).where(User.email == normalized_email)
    user = (await db.execute(query)).scalar_one_or_none()

    if user is None:
        await _verify_dummy_auth_verifier(payload.auth_verifier, hasher)
        await _sleep_to_minimum_failed_duration(started)
        rate_limited = await login_rate_limiter.register_failure(client_ip)
        if rate_limited:
            raise TooManyAttemptsError("too many failed attempts")
        raise InvalidCredentialsError("invalid email or password")

    try:
        is_valid_verifier = hasher.verify(user.auth_verifier_hash, payload.auth_verifier)
    except VerificationError:
        is_valid_verifier = False
    if not is_valid_verifier or user.status != UserStatus.ACTIVE:
        await _sleep_to_minimum_failed_duration(started)
        rate_limited = await login_rate_limiter.register_failure(client_ip)
        if rate_limited:
            raise TooManyAttemptsError("too many failed attempts")
        raise InvalidCredentialsError("invalid email or password")

    await login_rate_limiter.reset(client_ip)
    current_time = now or datetime.datetime.now(datetime.UTC)
    access_token, _ = issue_access_token(
        user_id=user.id,
        org_id=user.org_id,
        email=user.email,
        role=user.role.value,
        now=current_time,
    )
    refresh_token = secrets.token_urlsafe(48)
    refresh_token_hash = hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()
    expires_at = current_time + datetime.timedelta(days=settings.jwt_refresh_ttl_days)

    session = Session(
        user_id=user.id,
        refresh_token_hash=refresh_token_hash,
        device_info={"user_agent": user_agent},
        ip_address=client_ip,
        expires_at=expires_at,
    )
    db.add(session)
    await db.commit()
    return LoginResult(access_token=access_token, refresh_token=refresh_token, user=user)


async def _sleep_to_minimum_failed_duration(started: float) -> None:
    elapsed = time.monotonic() - started
    remaining = MIN_FAILED_LOGIN_RESPONSE_SECONDS - elapsed
    if remaining > 0:
        await asyncio.sleep(remaining)


async def _verify_dummy_auth_verifier(auth_verifier: str, hasher: Hasher) -> None:
    try:
        hasher.verify(DUMMY_AUTH_VERIFIER_HASH, auth_verifier)
    except Exception:
        return
