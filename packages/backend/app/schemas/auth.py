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
