from __future__ import annotations

import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user
from app.core.problems import problem_response
from app.db.session import get_db_session
from app.models.user import User
from app.schemas.vault import (
    CreateFolderRequest,
    CreateVaultItemRequest,
    FolderResponse,
    FolderTreeNode,
    RestoreVaultItemRequest,
    UpdateFolderRequest,
    UpdateVaultItemRequest,
    VaultItemCreatedResponse,
    VaultItemRevisionResponse,
    VaultItemsPageResponse,
    VaultItemResponse,
)
from app.services.vault import (
    FolderForbiddenError,
    FolderInvalidMoveError,
    FolderNoFieldsToUpdateError,
    FolderNotFoundError,
    ParentFolderNotFoundError,
    VaultItemForbiddenError,
    VaultItemNotFoundError,
    VaultItemRevisionNotFoundError,
    create_folder,
    create_vault_item,
    delete_folder,
    get_vault_revision_counter,
    list_vault_item_history,
    list_folders_tree,
    list_vault_items,
    list_vault_items_since,
    get_vault_item,
    restore_vault_item_revision,
    soft_delete_vault_item,
    update_folder,
    update_vault_item,
)


router = APIRouter(prefix="/api/v1/vault", tags=["vault"])


def _set_revision_header(response: Response, *, revision_counter: int) -> None:
    response.headers["X-Vault-Revision"] = str(max(0, revision_counter))


@router.post("/folders", response_model=FolderResponse, status_code=201)
async def create_folder_endpoint(
    payload: CreateFolderRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> FolderResponse:
    try:
        folder = await create_folder(
            db,
            current_user=current_user,
            payload=payload,
        )
    except ParentFolderNotFoundError:
        return problem_response(
            status=404,
            title="Not Found",
            detail="Parent folder not found.",
            type_="https://vaultguard.dev/errors/parent-folder-not-found",
        )
    except FolderForbiddenError:
        return problem_response(
            status=403,
            title="Forbidden",
            detail="You do not have access to the parent folder.",
            type_="https://vaultguard.dev/errors/folder-forbidden",
        )
    return FolderResponse.from_folder(folder)


@router.get("/folders", response_model=list[FolderTreeNode])
async def get_folders_endpoint(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> list[FolderTreeNode]:
    return await list_folders_tree(db, current_user=current_user)


@router.patch("/folders/{folder_id}", response_model=FolderResponse)
async def update_folder_endpoint(
    folder_id: uuid.UUID,
    payload: UpdateFolderRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> FolderResponse:
    try:
        folder = await update_folder(
            db,
            current_user=current_user,
            folder_id=folder_id,
            payload=payload,
        )
    except FolderNotFoundError:
        return problem_response(
            status=404,
            title="Not Found",
            detail="Folder not found.",
            type_="https://vaultguard.dev/errors/folder-not-found",
        )
    except ParentFolderNotFoundError:
        return problem_response(
            status=404,
            title="Not Found",
            detail="Parent folder not found.",
            type_="https://vaultguard.dev/errors/parent-folder-not-found",
        )
    except FolderForbiddenError:
        return problem_response(
            status=403,
            title="Forbidden",
            detail="You do not have access to this folder.",
            type_="https://vaultguard.dev/errors/folder-forbidden",
        )
    except FolderInvalidMoveError:
        return problem_response(
            status=400,
            title="Bad Request",
            detail="Folder move is invalid.",
            type_="https://vaultguard.dev/errors/folder-invalid-move",
        )
    except FolderNoFieldsToUpdateError:
        return problem_response(
            status=400,
            title="Bad Request",
            detail="At least one field must be provided for update.",
            type_="https://vaultguard.dev/errors/folder-empty-update",
        )
    return FolderResponse.from_folder(folder)


@router.delete("/folders/{folder_id}", status_code=204, response_class=Response)
async def delete_folder_endpoint(
    folder_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    try:
        await delete_folder(
            db,
            current_user=current_user,
            folder_id=folder_id,
        )
    except FolderNotFoundError:
        return problem_response(
            status=404,
            title="Not Found",
            detail="Folder not found.",
            type_="https://vaultguard.dev/errors/folder-not-found",
        )
    except FolderForbiddenError:
        return problem_response(
            status=403,
            title="Forbidden",
            detail="You do not have access to this folder.",
            type_="https://vaultguard.dev/errors/folder-forbidden",
        )
    return Response(status_code=204)


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


@router.get("", response_model=VaultItemsPageResponse)
async def get_vault(
    response: Response,
    limit: int = Query(default=50, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> VaultItemsPageResponse:
    items, total = await list_vault_items(
        db,
        current_user=current_user,
        limit=limit,
        offset=offset,
    )
    revision_counter = await get_vault_revision_counter(db, current_user=current_user)
    _set_revision_header(response, revision_counter=revision_counter)
    return VaultItemsPageResponse(
        items=[VaultItemResponse.from_item(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/sync", response_model=VaultItemsPageResponse)
async def sync_vault(
    response: Response,
    since: str = Query(...),
    limit: int = Query(default=50, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> VaultItemsPageResponse:
    try:
        parsed_since = since.strip().replace("Z", "+00:00")
        since_dt = datetime.datetime.fromisoformat(parsed_since)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid since parameter.") from exc

    if since_dt.tzinfo is None:
        raise HTTPException(status_code=422, detail="The since parameter must include a timezone.")

    items, total = await list_vault_items_since(
        db,
        current_user=current_user,
        since=since_dt.astimezone(datetime.UTC),
        limit=limit,
        offset=offset,
    )
    revision_counter = await get_vault_revision_counter(db, current_user=current_user)
    _set_revision_header(response, revision_counter=revision_counter)
    return VaultItemsPageResponse(
        items=[VaultItemResponse.from_item(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


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


@router.get("/items/{item_id}/history", response_model=list[VaultItemRevisionResponse])
async def get_item_history(
    item_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> list[VaultItemRevisionResponse]:
    try:
        revisions = await list_vault_item_history(
            db,
            current_user=current_user,
            item_id=item_id,
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
    return [
        VaultItemRevisionResponse(
            revision_number=revision.revision_number,
            created_at=revision.created_at,
        )
        for revision in revisions
    ]


@router.post("/items/{item_id}/restore", response_model=VaultItemResponse)
async def restore_item_revision(
    item_id: uuid.UUID,
    payload: RestoreVaultItemRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> VaultItemResponse:
    client_ip = request.client.host if request.client and request.client.host else "0.0.0.0"
    user_agent = request.headers.get("user-agent", "")
    try:
        item = await restore_vault_item_revision(
            db,
            current_user=current_user,
            item_id=item_id,
            revision_number=payload.revision_number,
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
    except VaultItemRevisionNotFoundError:
        return problem_response(
            status=404,
            title="Not Found",
            detail="Vault item revision not found.",
            type_="https://vaultguard.dev/errors/vault-item-revision-not-found",
        )
    return VaultItemResponse.from_item(item)
