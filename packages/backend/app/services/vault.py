from __future__ import annotations

import datetime
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog, AuditLogAction
from app.models.user import User
from app.models.vault_item import VaultItem
from app.schemas.vault import CreateVaultItemRequest


async def create_vault_item(
    db: AsyncSession,
    *,
    current_user: User,
    payload: CreateVaultItemRequest,
    client_ip: str,
    user_agent: str,
    now: datetime.datetime | None = None,
) -> VaultItem:
    created_at = now or datetime.datetime.now(datetime.UTC)
    item = VaultItem(
        owner_id=current_user.id,
        org_id=current_user.org_id,
        type=payload.type,
        encrypted_data=payload.encrypted_data,
        encrypted_key=payload.encrypted_key,
        name=payload.name.strip(),
        folder_id=payload.folder_id,
    )
    db.add(item)
    await db.flush()
    db.add(
        AuditLog(
            org_id=current_user.org_id,
            actor_id=current_user.id,
            action=AuditLogAction.CREATE_ITEM,
            target_id=item.id,
            ip_address=client_ip,
            user_agent=user_agent,
            geo_location="unknown",
            timestamp=created_at,
        )
    )
    await db.commit()
    await db.refresh(item)
    return item
