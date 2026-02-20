from __future__ import annotations

import datetime
import uuid
from typing import Literal
from typing import Any

from pydantic import BaseModel, Field


class CreateOrganizationRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    subscription_tier: str = Field(default="enterprise", min_length=1, max_length=64)
    settings: dict[str, object] = Field(default_factory=dict)


class OrganizationResponse(BaseModel):
    id: uuid.UUID
    name: str
    subscription_tier: str
    settings: dict[str, object]
    created_at: datetime.datetime

    @classmethod
    def from_organization(cls, organization: Any) -> "OrganizationResponse":
        return cls(
            id=organization.id,
            name=organization.name,
            subscription_tier=organization.subscription_tier,
            settings=dict(organization.settings or {}),
            created_at=organization.created_at,
        )


class InviteUserRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: Literal["admin", "manager", "member", "viewer"]


class InviteUserResponse(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    email: str
    role: str
    status: str
    invitation_expires_at: datetime.datetime

    @classmethod
    def from_user(cls, user: Any) -> "InviteUserResponse":
        return cls(
            id=user.id,
            org_id=user.org_id,
            email=user.email,
            role=user.role.value if hasattr(user.role, "value") else str(user.role).lower(),
            status=user.status.value if hasattr(user.status, "value") else str(user.status).lower(),
            invitation_expires_at=user.invitation_expires_at,
        )
