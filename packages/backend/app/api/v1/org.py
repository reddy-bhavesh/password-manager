from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user, require_admin
from app.core.problems import problem_response
from app.db.session import get_db_session
from app.models.user import User
from app.schemas.org import CreateOrganizationRequest, InviteUserRequest, InviteUserResponse, OrganizationResponse
from app.services.email import InvitationEmailSender, StubInvitationEmailSender
from app.services.org import (
    InviteUserConflictError,
    OrganizationAccessError,
    create_organization,
    get_current_organization,
    invite_user,
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
