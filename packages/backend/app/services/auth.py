from __future__ import annotations

import asyncio
import datetime
import hashlib
import secrets
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Protocol

from argon2.exceptions import VerificationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog, AuditLogAction
from app.models.auth_session import Session
from app.models.organization import Organization  # noqa: F401
from app.models.user import User, UserStatus
from app.schemas.auth import LoginRequest, RegisterRequest
from app.security.password import argon2_hasher
from app.security.tokens import AccessTokenValidationError, issue_access_token, validate_access_token
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


class InvalidRefreshTokenError(Exception):
    pass


class InvalidAccessTokenError(Exception):
    pass


class SessionNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class LoginResult:
    access_token: str
    refresh_token: str
    user: User


@dataclass(frozen=True)
class RefreshResult:
    access_token: str
    refresh_token: str


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
    await _append_audit_log(
        db,
        org_id=user.org_id,
        actor_id=user.id,
        action=AuditLogAction.LOGIN,
        target_id=session.id,
        ip_address=client_ip,
        user_agent=user_agent,
    )
    await db.commit()
    return LoginResult(access_token=access_token, refresh_token=refresh_token, user=user)


async def refresh_tokens(
    db: AsyncSession,
    refresh_token: str,
    *,
    client_ip: str,
    user_agent: str,
    now: datetime.datetime | None = None,
) -> RefreshResult:
    current_time = now or datetime.datetime.now(datetime.UTC)
    refresh_token_hash = hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()

    session_query = select(Session).where(
        Session.refresh_token_hash == refresh_token_hash,
        Session.revoked_at.is_(None),
    )
    current_session = (await db.execute(session_query)).scalar_one_or_none()
    if current_session is None:
        raise InvalidRefreshTokenError("invalid refresh token")
    if _is_expired(current_session.expires_at, current_time):
        current_session.revoked_at = current_time
        await db.commit()
        raise InvalidRefreshTokenError("invalid refresh token")

    user = await _find_active_user_by_identifier(db, current_session.user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        raise InvalidRefreshTokenError("invalid refresh token")

    current_session.revoked_at = current_time
    next_refresh_token = secrets.token_urlsafe(48)
    next_refresh_hash = hashlib.sha256(next_refresh_token.encode("utf-8")).hexdigest()
    next_expiry = current_time + datetime.timedelta(days=settings.jwt_refresh_ttl_days)

    rotated_session = Session(
        user_id=user.id,
        refresh_token_hash=next_refresh_hash,
        device_info={"user_agent": user_agent},
        ip_address=client_ip,
        expires_at=next_expiry,
    )
    db.add(rotated_session)

    access_token, _ = issue_access_token(
        user_id=user.id,
        org_id=user.org_id,
        email=user.email,
        role=user.role.value,
        now=current_time,
    )
    await _append_audit_log(
        db,
        org_id=user.org_id,
        actor_id=user.id,
        action=AuditLogAction.REFRESH_TOKEN,
        target_id=rotated_session.id,
        ip_address=client_ip,
        user_agent=user_agent,
    )
    await db.commit()
    return RefreshResult(access_token=access_token, refresh_token=next_refresh_token)


async def revoke_session_by_refresh_token(
    db: AsyncSession,
    *,
    access_token: str,
    refresh_token: str,
    client_ip: str,
    user_agent: str,
    now: datetime.datetime | None = None,
) -> None:
    current_time = now or datetime.datetime.now(datetime.UTC)
    current_user = await get_user_from_access_token(db, access_token)
    refresh_token_hash = hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()

    session_query = select(Session).where(
        Session.refresh_token_hash == refresh_token_hash,
        Session.revoked_at.is_(None),
    )
    auth_session = (await db.execute(session_query)).scalar_one_or_none()
    if auth_session is None or not _uuids_equal(auth_session.user_id, current_user.id):
        raise SessionNotFoundError("session not found")

    auth_session.revoked_at = current_time
    await _append_audit_log(
        db,
        org_id=current_user.org_id,
        actor_id=current_user.id,
        action=AuditLogAction.LOGOUT,
        target_id=auth_session.id,
        ip_address=client_ip,
        user_agent=user_agent,
    )
    await db.commit()


async def revoke_session_by_id(
    db: AsyncSession,
    *,
    access_token: str,
    session_id: uuid.UUID,
    client_ip: str,
    user_agent: str,
    now: datetime.datetime | None = None,
) -> None:
    current_time = now or datetime.datetime.now(datetime.UTC)
    current_user = await get_user_from_access_token(db, access_token)
    target_session = await db.get(Session, session_id)
    if target_session is None or target_session.user_id != current_user.id:
        raise SessionNotFoundError("session not found")

    if target_session.revoked_at is None:
        target_session.revoked_at = current_time
    await _append_audit_log(
        db,
        org_id=current_user.org_id,
        actor_id=current_user.id,
        action=AuditLogAction.SESSION_REVOKE,
        target_id=target_session.id,
        ip_address=client_ip,
        user_agent=user_agent,
    )
    await db.commit()


async def get_user_from_access_token(db: AsyncSession, access_token: str) -> User:
    try:
        claims = validate_access_token(access_token)
    except AccessTokenValidationError as exc:
        raise InvalidAccessTokenError("invalid access token") from exc

    user = await _find_active_user_by_identifier(db, claims.sub)
    if (
        user is None
        or user.status != UserStatus.ACTIVE
        or user.email != claims.email
        or not _uuids_equal(user.org_id, claims.org_id)
    ):
        raise InvalidAccessTokenError("invalid access token")
    return user


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


def _uuids_equal(left: object, right: object) -> bool:
    return _coerce_uuid(left) == _coerce_uuid(right)


def _coerce_uuid(value: object) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    if value is None:
        return None
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


async def _find_active_user_by_identifier(db: AsyncSession, identifier: object) -> User | None:
    query = select(User).where(User.status == UserStatus.ACTIVE)
    users = (await db.execute(query)).scalars().all()
    for candidate in users:
        if _uuids_equal(candidate.id, identifier):
            return candidate
    return None


def _is_expired(expires_at: datetime.datetime, reference: datetime.datetime) -> bool:
    normalized_expiry = expires_at
    if normalized_expiry.tzinfo is None:
        normalized_expiry = normalized_expiry.replace(tzinfo=datetime.UTC)
    normalized_reference = reference
    if normalized_reference.tzinfo is None:
        normalized_reference = normalized_reference.replace(tzinfo=datetime.UTC)
    return normalized_expiry <= normalized_reference


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
