from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user
from app.db.session import get_db_session
from app.models.user import User
from app.schemas.vault import CreateVaultItemRequest, VaultItemCreatedResponse
from app.services.vault import create_vault_item


router = APIRouter(prefix="/api/v1/vault", tags=["vault"])


@router.post("/items", response_model=VaultItemCreatedResponse, status_code=201)
async def create_item(
    payload: CreateVaultItemRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> VaultItemCreatedResponse:
    client_ip = request.client.host if request.client and request.client.host else "0.0.0.0"
    user_agent = request.headers.get("user-agent", "")
    item = await create_vault_item(
        db,
        current_user=current_user,
        payload=payload,
        client_ip=client_ip,
        user_agent=user_agent,
    )
    return VaultItemCreatedResponse.from_item(item)
