from __future__ import annotations

import datetime
import uuid
from typing import Any

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    name: str = Field(min_length=1, max_length=255)
    org_id: uuid.UUID
    auth_verifier: str = Field(min_length=8, max_length=4096)
    public_key: str = Field(min_length=1)
    encrypted_private_key: str = Field(min_length=1)


class RegisterUserResponse(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    email: str
    name: str
    created_at: datetime.datetime

    @classmethod
    def from_user(cls, user: Any) -> "RegisterUserResponse":
        return cls(
            id=user.id,
            org_id=user.org_id,
            email=user.email,
            name=user.name,
            created_at=user.created_at,
        )


class PreauthRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class Argon2Params(BaseModel):
    memory_kib: int
    iterations: int
    parallelism: int
    hash_len: int
    salt_len: int
    type: str


class PreauthResponse(BaseModel):
    argon2_params: Argon2Params


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    auth_verifier: str = Field(min_length=8, max_length=4096)


class AuthenticatedUserResponse(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    email: str
    name: str
    role: str
    status: str
    mfa_enabled: bool

    @classmethod
    def from_user(cls, user: Any) -> "AuthenticatedUserResponse":
        return cls(
            id=user.id,
            org_id=user.org_id,
            email=user.email,
            name=user.name,
            role=user.role.value if hasattr(user.role, "value") else str(user.role),
            status=user.status.value if hasattr(user.status, "value") else str(user.status),
            mfa_enabled=user.mfa_enabled,
        )


class LoginResponse(BaseModel):
    access_token: str | None = None
    refresh_token: str | None = None
    user: AuthenticatedUserResponse | None = None
    mfa_required: bool = False
    mfa_token: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=16, max_length=4096)


class RefreshResponse(BaseModel):
    access_token: str
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=16, max_length=4096)


class MfaTotpEnrollResponse(BaseModel):
    otpauth_uri: str
    backup_codes: list[str]


class MfaTotpConfirmRequest(BaseModel):
    code: str = Field(min_length=6, max_length=64)


class MfaTotpConfirmResponse(BaseModel):
    mfa_enabled: bool


class MfaVerifyRequest(BaseModel):
    mfa_token: str = Field(min_length=32, max_length=4096)
    code: str = Field(min_length=6, max_length=64)
