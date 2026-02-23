from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user, require_admin
from app.core.problems import problem_response
from app.db.session import get_db_session
from app.models.user import User
from app.schemas.org import (
    AddOrganizationGroupMemberRequest,
    CreateOrganizationGroupRequest,
    CreateOrganizationRequest,
    InviteUserRequest,
    InviteUserResponse,
    OrganizationGroupMemberResponse,
    OrganizationGroupResponse,
    OrganizationGroupsListResponse,
    OrganizationResponse,
    OrganizationUserResponse,
    OrganizationUsersPageResponse,
    UpdateOrganizationUserRoleRequest,
)
from app.services.email import InvitationEmailSender, StubInvitationEmailSender
from app.services.org import (
    InviteUserConflictError,
    OrganizationAccessError,
    OrganizationGroupConflictError,
    OrganizationGroupMemberNotFoundError,
    OrganizationGroupNotFoundError,
    OrganizationUserConflictError,
    OrganizationUserNotFoundError,
    add_organization_group_member,
    change_organization_user_role,
    create_organization,
    create_organization_group,
    get_current_organization,
    invite_user,
    list_organization_groups,
    list_organization_users,
    offboard_organization_user,
    remove_organization_group_member,
)


router = APIRouter(prefix="/api/v1/org", tags=["org"])


def get_invitation_email_sender() -> InvitationEmailSender:
    return StubInvitationEmailSender()


@router.post("", response_model=OrganizationResponse, status_code=201)
async def create_org(
    payload: CreateOrganizationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> OrganizationResponse:
    organization = await create_organization(
        db,
        current_user=current_user,
        payload=payload,
    )
    return OrganizationResponse.from_organization(organization)


@router.post("/groups", response_model=OrganizationGroupResponse, status_code=201)
async def create_org_group(
    payload: CreateOrganizationGroupRequest,
    request: Request,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> OrganizationGroupResponse:
    client_ip = request.client.host if request.client and request.client.host else "0.0.0.0"
    user_agent = request.headers.get("user-agent", "")
    group = await create_organization_group(
        db,
        current_user=current_user,
        payload=payload,
        client_ip=client_ip,
        user_agent=user_agent,
    )
    return OrganizationGroupResponse.from_group(group)


@router.get("/groups", response_model=OrganizationGroupsListResponse)
async def list_org_groups(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> OrganizationGroupsListResponse:
    groups = await list_organization_groups(
        db,
        current_user=current_user,
    )
    return OrganizationGroupsListResponse(
        items=[
            OrganizationGroupResponse.from_group(item.group, member_count=item.member_count)
            for item in groups
        ]
    )


@router.post("/groups/{group_id}/members", response_model=OrganizationGroupMemberResponse, status_code=201)
async def add_org_group_member(
    group_id: uuid.UUID,
    payload: AddOrganizationGroupMemberRequest,
    request: Request,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> OrganizationGroupMemberResponse:
    client_ip = request.client.host if request.client and request.client.host else "0.0.0.0"
    user_agent = request.headers.get("user-agent", "")
    try:
        membership = await add_organization_group_member(
            db,
            current_user=current_user,
            group_id=group_id,
            payload=payload,
            client_ip=client_ip,
            user_agent=user_agent,
        )
    except OrganizationGroupNotFoundError:
        return problem_response(
            status=404,
            title="Not Found",
            detail="Group not found.",
            type_="https://vaultguard.dev/errors/group-not-found",
        )
    except OrganizationUserNotFoundError:
        return problem_response(
            status=404,
            title="Not Found",
            detail="User not found.",
            type_="https://vaultguard.dev/errors/user-not-found",
        )
    except OrganizationGroupConflictError:
        return problem_response(
            status=409,
            title="Conflict",
            detail="User is already a member of this group.",
            type_="https://vaultguard.dev/errors/group-member-conflict",
        )
    return OrganizationGroupMemberResponse.from_membership(membership)


@router.delete("/groups/{group_id}/members/{user_id}", status_code=204, response_class=Response, response_model=None)
async def remove_org_group_member(
    group_id: uuid.UUID,
    user_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> None:
    client_ip = request.client.host if request.client and request.client.host else "0.0.0.0"
    user_agent = request.headers.get("user-agent", "")
    try:
        await remove_organization_group_member(
            db,
            current_user=current_user,
            group_id=group_id,
            user_id=user_id,
            client_ip=client_ip,
            user_agent=user_agent,
        )
    except OrganizationGroupNotFoundError:
        return problem_response(
            status=404,
            title="Not Found",
            detail="Group not found.",
            type_="https://vaultguard.dev/errors/group-not-found",
        )
    except OrganizationGroupMemberNotFoundError:
        return problem_response(
            status=404,
            title="Not Found",
            detail="Group member not found.",
            type_="https://vaultguard.dev/errors/group-member-not-found",
        )
    return None


@router.post("/users/invite", response_model=InviteUserResponse, status_code=201)
async def invite_org_user(
    payload: InviteUserRequest,
    request: Request,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
    email_sender: InvitationEmailSender = Depends(get_invitation_email_sender),
) -> InviteUserResponse:
    client_ip = request.client.host if request.client and request.client.host else "0.0.0.0"
    user_agent = request.headers.get("user-agent", "")
    try:
        invited_user = await invite_user(
            db,
            current_user=current_user,
            payload=payload,
            email_sender=email_sender,
            client_ip=client_ip,
            user_agent=user_agent,
        )
    except InviteUserConflictError:
        return problem_response(
            status=409,
            title="Conflict",
            detail="A user with this email already exists.",
            type_="https://vaultguard.dev/errors/duplicate-email",
        )
    return InviteUserResponse.from_user(invited_user)


@router.get("", response_model=OrganizationResponse)
async def get_org(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> OrganizationResponse:
    try:
        organization = await get_current_organization(
            db,
            current_user=current_user,
        )
    except OrganizationAccessError:
        return problem_response(
            status=403,
            title="Forbidden",
            detail="You do not have access to this organization.",
            type_="https://vaultguard.dev/errors/org-forbidden",
        )
    return OrganizationResponse.from_organization(organization)


@router.get("/users", response_model=OrganizationUsersPageResponse)
async def list_org_users(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    role: str | None = Query(default=None, pattern="^(owner|admin|manager|member|viewer)$"),
    status: str | None = Query(default=None, pattern="^(active|suspended|invited)$"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> OrganizationUsersPageResponse:
    page = await list_organization_users(
        db,
        current_user=current_user,
        limit=limit,
        offset=offset,
        role=role,
        status=status,
    )
    return OrganizationUsersPageResponse(
        items=[OrganizationUserResponse.from_user(user) for user in page.users],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.patch("/users/{user_id}/role", response_model=OrganizationUserResponse)
async def update_org_user_role(
    user_id: uuid.UUID,
    payload: UpdateOrganizationUserRoleRequest,
    request: Request,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> OrganizationUserResponse:
    client_ip = request.client.host if request.client and request.client.host else "0.0.0.0"
    user_agent = request.headers.get("user-agent", "")
    try:
        updated_user = await change_organization_user_role(
            db,
            current_user=current_user,
            user_id=user_id,
            payload=payload,
            client_ip=client_ip,
            user_agent=user_agent,
        )
    except OrganizationUserNotFoundError:
        return problem_response(
            status=404,
            title="Not Found",
            detail="User not found.",
            type_="https://vaultguard.dev/errors/user-not-found",
        )
    except OrganizationUserConflictError:
        return problem_response(
            status=409,
            title="Conflict",
            detail="Owner role cannot be changed.",
            type_="https://vaultguard.dev/errors/owner-role-change-forbidden",
        )
    return OrganizationUserResponse.from_user(updated_user)


@router.delete("/users/{user_id}", status_code=204, response_class=Response, response_model=None)
async def offboard_org_user(
    user_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> None:
    client_ip = request.client.host if request.client and request.client.host else "0.0.0.0"
    user_agent = request.headers.get("user-agent", "")
    try:
        await offboard_organization_user(
            db,
            current_user=current_user,
            user_id=user_id,
            client_ip=client_ip,
            user_agent=user_agent,
        )
    except OrganizationUserNotFoundError:
        return problem_response(
            status=404,
            title="Not Found",
            detail="User not found.",
            type_="https://vaultguard.dev/errors/user-not-found",
        )
    except OrganizationUserConflictError:
        return problem_response(
            status=409,
            title="Conflict",
            detail="Owner cannot be deleted.",
            type_="https://vaultguard.dev/errors/owner-delete-forbidden",
        )
    return None
