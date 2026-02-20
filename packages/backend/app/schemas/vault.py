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


class UpdateVaultItemRequest(BaseModel):
    type: VaultItemType
    encrypted_data: str = Field(min_length=1)
    encrypted_key: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=255)
    folder_id: uuid.UUID | None = None


class RestoreVaultItemRequest(BaseModel):
    revision_number: int = Field(ge=1)


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


class VaultItemResponse(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    org_id: uuid.UUID
    type: str
    encrypted_data: str
    encrypted_key: str
    name: str
    folder_id: uuid.UUID | None
    favorite: bool
    created_at: datetime.datetime
    updated_at: datetime.datetime
    deleted_at: datetime.datetime | None

    @classmethod
    def from_item(cls, item: Any) -> "VaultItemResponse":
        item_type = item.type.value if hasattr(item.type, "value") else str(item.type)
        return cls(
            id=item.id,
            owner_id=item.owner_id,
            org_id=item.org_id,
            type=item_type,
            encrypted_data=item.encrypted_data,
            encrypted_key=item.encrypted_key,
            name=item.name,
            folder_id=item.folder_id,
            favorite=item.favorite,
            created_at=item.created_at,
            updated_at=item.updated_at,
            deleted_at=item.deleted_at,
        )


class VaultItemsPageResponse(BaseModel):
    items: list[VaultItemResponse]
    total: int
    limit: int
    offset: int


class VaultItemRevisionResponse(BaseModel):
    revision_number: int
    created_at: datetime.datetime
