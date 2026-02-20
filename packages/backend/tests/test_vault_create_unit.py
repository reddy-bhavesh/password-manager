from __future__ import annotations

import datetime
import uuid
from unittest.mock import AsyncMock, Mock

import pytest

from app.models.audit_log import AuditLog, AuditLogAction
from app.models.user import User, UserRole, UserStatus
from app.models.vault_item import VaultItem, VaultItemType
from app.schemas.vault import CreateVaultItemRequest
from app.services.vault import create_vault_item


def _make_user() -> User:
    return User(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        email="vault-unit@example.com",
        name="Vault Unit User",
        role=UserRole.MEMBER,
        status=UserStatus.ACTIVE,
        public_key="pk",
        encrypted_private_key="enc",
        auth_verifier_hash="hash",
    )


@pytest.mark.asyncio
async def test_create_vault_item_stores_encrypted_blobs_and_writes_audit_log() -> None:
    user = _make_user()
    payload = CreateVaultItemRequest(
        type=VaultItemType.LOGIN,
        encrypted_data="Q2lwaGVydGV4dEJsb2I=",
        encrypted_key="V3JhcHBlZERFSw==",
        name="  Production VPN  ",
        folder_id=None,
    )
    now = datetime.datetime.now(datetime.UTC)

    added_entities: list[object] = []
    db = AsyncMock()
    db.add = Mock(side_effect=added_entities.append)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    created = await create_vault_item(
        db,
        current_user=user,
        payload=payload,
        client_ip="127.0.0.1",
        user_agent="pytest",
        now=now,
    )

    assert isinstance(created, VaultItem)
    assert created.encrypted_data == payload.encrypted_data
    assert created.encrypted_key == payload.encrypted_key
    assert created.name == "Production VPN"
    assert created.type == VaultItemType.LOGIN
    assert created.owner_id == user.id
    assert created.org_id == user.org_id

    assert len(added_entities) == 2
    assert isinstance(added_entities[0], VaultItem)
    assert isinstance(added_entities[1], AuditLog)
    audit_log = added_entities[1]
    assert audit_log.action == AuditLogAction.CREATE_ITEM
    assert audit_log.target_id == created.id
    assert audit_log.actor_id == user.id
    assert audit_log.timestamp == now

    db.flush.assert_awaited_once()
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(created)
