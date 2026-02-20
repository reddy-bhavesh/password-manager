from __future__ import annotations

import datetime
import uuid
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
