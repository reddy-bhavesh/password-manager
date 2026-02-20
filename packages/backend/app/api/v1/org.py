from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user
from app.core.problems import problem_response
from app.db.session import get_db_session
from app.models.user import User
from app.schemas.org import CreateOrganizationRequest, OrganizationResponse
from app.services.org import OrganizationAccessError, create_organization, get_current_organization


router = APIRouter(prefix="/api/v1/org", tags=["org"])


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
