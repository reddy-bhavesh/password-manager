from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass

import jwt
from jwt import InvalidTokenError

from app.core.settings import settings


ALGORITHM = "RS256"


class AccessTokenValidationError(Exception):
    pass


class MfaTokenValidationError(Exception):
    pass


@dataclass(frozen=True)
class AccessTokenPayload:
    sub: uuid.UUID
    org_id: uuid.UUID
    email: str
    role: str
    iat: datetime.datetime
    exp: datetime.datetime
    iss: str


@dataclass(frozen=True)
class MfaTokenPayload:
    sub: uuid.UUID
    org_id: uuid.UUID
    email: str
    role: str
    purpose: str
    iat: datetime.datetime
    exp: datetime.datetime
    iss: str


def issue_access_token(
    *,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    email: str,
    role: str,
    now: datetime.datetime | None = None,
    expires_in: datetime.timedelta | None = None,
) -> tuple[str, datetime.datetime]:
    issued_at = now or datetime.datetime.now(datetime.UTC)
    expiry = issued_at + (expires_in or datetime.timedelta(minutes=settings.jwt_access_ttl_minutes))
    payload = {
        "sub": str(user_id),
        "org_id": str(org_id),
        "email": email,
        "role": role,
        "iss": settings.jwt_issuer,
        "iat": int(issued_at.timestamp()),
        "exp": int(expiry.timestamp()),
    }
    token = jwt.encode(payload, settings.normalized_jwt_private_key, algorithm=ALGORITHM)
    return token, expiry


def issue_mfa_token(
    *,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    email: str,
    role: str,
    now: datetime.datetime | None = None,
    expires_in: datetime.timedelta | None = None,
) -> tuple[str, datetime.datetime]:
    issued_at = now or datetime.datetime.now(datetime.UTC)
    expiry = issued_at + (expires_in or datetime.timedelta(minutes=settings.mfa_challenge_ttl_minutes))
    payload = {
        "sub": str(user_id),
        "org_id": str(org_id),
        "email": email,
        "role": role,
        "purpose": "mfa",
        "iss": settings.jwt_issuer,
        "iat": int(issued_at.timestamp()),
        "exp": int(expiry.timestamp()),
    }
    token = jwt.encode(payload, settings.normalized_jwt_private_key, algorithm=ALGORITHM)
    return token, expiry


def validate_access_token(token: str) -> AccessTokenPayload:
    try:
        payload = jwt.decode(
            token,
            settings.normalized_jwt_public_key,
            algorithms=[ALGORITHM],
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "org_id", "email", "role", "iat", "exp", "iss"]},
        )
    except InvalidTokenError as exc:
        raise AccessTokenValidationError("invalid access token") from exc

    try:
        return AccessTokenPayload(
            sub=uuid.UUID(payload["sub"]),
            org_id=uuid.UUID(payload["org_id"]),
            email=str(payload["email"]),
            role=str(payload["role"]),
            iat=datetime.datetime.fromtimestamp(int(payload["iat"]), tz=datetime.UTC),
            exp=datetime.datetime.fromtimestamp(int(payload["exp"]), tz=datetime.UTC),
            iss=str(payload["iss"]),
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise AccessTokenValidationError("malformed access token payload") from exc


def validate_mfa_token(token: str) -> MfaTokenPayload:
    try:
        payload = jwt.decode(
            token,
            settings.normalized_jwt_public_key,
            algorithms=[ALGORITHM],
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "org_id", "email", "role", "purpose", "iat", "exp", "iss"]},
        )
    except InvalidTokenError as exc:
        raise MfaTokenValidationError("invalid mfa token") from exc

    try:
        decoded = MfaTokenPayload(
            sub=uuid.UUID(payload["sub"]),
            org_id=uuid.UUID(payload["org_id"]),
            email=str(payload["email"]),
            role=str(payload["role"]),
            purpose=str(payload["purpose"]),
            iat=datetime.datetime.fromtimestamp(int(payload["iat"]), tz=datetime.UTC),
            exp=datetime.datetime.fromtimestamp(int(payload["exp"]), tz=datetime.UTC),
            iss=str(payload["iss"]),
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise MfaTokenValidationError("malformed mfa token payload") from exc

    if decoded.purpose != "mfa":
        raise MfaTokenValidationError("invalid mfa token purpose")
    return decoded
