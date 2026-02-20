from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user
from app.core.problems import problem_response
from app.db.session import get_db_session
from app.models.user import User
from app.schemas.vault import (
    CreateVaultItemRequest,
    UpdateVaultItemRequest,
    VaultItemCreatedResponse,
    VaultItemResponse,
)
from app.services.vault import (
    VaultItemForbiddenError,
    VaultItemNotFoundError,
    create_vault_item,
    get_vault_item,
    soft_delete_vault_item,
    update_vault_item,
)


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


@router.get("/items/{item_id}", response_model=VaultItemResponse)
async def get_item(
    item_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> VaultItemResponse:
    client_ip = request.client.host if request.client and request.client.host else "0.0.0.0"
    user_agent = request.headers.get("user-agent", "")
    try:
        item = await get_vault_item(
            db,
            current_user=current_user,
            item_id=item_id,
            client_ip=client_ip,
            user_agent=user_agent,
        )
    except VaultItemNotFoundError:
        return problem_response(
            status=404,
            title="Not Found",
            detail="Vault item not found.",
            type_="https://vaultguard.dev/errors/vault-item-not-found",
        )
    except VaultItemForbiddenError:
        return problem_response(
            status=403,
            title="Forbidden",
            detail="You do not have access to this vault item.",
            type_="https://vaultguard.dev/errors/vault-item-forbidden",
        )
    return VaultItemResponse.from_item(item)


@router.put("/items/{item_id}", response_model=VaultItemResponse)
async def update_item(
    item_id: uuid.UUID,
    payload: UpdateVaultItemRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> VaultItemResponse:
    client_ip = request.client.host if request.client and request.client.host else "0.0.0.0"
    user_agent = request.headers.get("user-agent", "")
    try:
        item = await update_vault_item(
            db,
            current_user=current_user,
            item_id=item_id,
            payload=payload,
            client_ip=client_ip,
            user_agent=user_agent,
        )
    except VaultItemNotFoundError:
        return problem_response(
            status=404,
            title="Not Found",
            detail="Vault item not found.",
            type_="https://vaultguard.dev/errors/vault-item-not-found",
        )
    except VaultItemForbiddenError:
        return problem_response(
            status=403,
            title="Forbidden",
            detail="You do not have access to this vault item.",
            type_="https://vaultguard.dev/errors/vault-item-forbidden",
        )
    return VaultItemResponse.from_item(item)


@router.delete("/items/{item_id}", status_code=204, response_class=Response)
async def delete_item(
    item_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    client_ip = request.client.host if request.client and request.client.host else "0.0.0.0"
    user_agent = request.headers.get("user-agent", "")
    try:
        await soft_delete_vault_item(
            db,
            current_user=current_user,
            item_id=item_id,
            client_ip=client_ip,
            user_agent=user_agent,
        )
    except VaultItemNotFoundError:
        return problem_response(
            status=404,
            title="Not Found",
            detail="Vault item not found.",
            type_="https://vaultguard.dev/errors/vault-item-not-found",
        )
    except VaultItemForbiddenError:
        return problem_response(
            status=403,
            title="Forbidden",
            detail="You do not have access to this vault item.",
            type_="https://vaultguard.dev/errors/vault-item-forbidden",
        )
    return Response(status_code=204)
