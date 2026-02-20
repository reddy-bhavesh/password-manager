from __future__ import annotations

import datetime
import uuid
from typing import Any

from pydantic import BaseModel, Field

from app.models.vault_item import VaultItemType


class CreateVaultItemRequest(BaseModel):
    type: VaultItemType
    encrypted_data: str = Field(min_length=1)
    encrypted_key: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=255)
    folder_id: uuid.UUID | None = None


class VaultItemCreatedResponse(BaseModel):
    id: uuid.UUID
    type: str
    name: str
    created_at: datetime.datetime

    @classmethod
    def from_item(cls, item: Any) -> "VaultItemCreatedResponse":
        item_type = item.type.value if hasattr(item.type, "value") else str(item.type)
        return cls(
            id=item.id,
            type=item_type,
            name=item.name,
            created_at=item.created_at,
        )
