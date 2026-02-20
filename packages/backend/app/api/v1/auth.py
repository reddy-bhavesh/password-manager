from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.problems import problem_response
from app.db.session import get_db_session
from app.schemas.auth import RegisterRequest, RegisterUserResponse
from app.services.auth import DuplicateEmailError, register_user


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=RegisterUserResponse, status_code=201)
async def register(
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db_session),
) -> RegisterUserResponse:
    try:
        user = await register_user(db, payload)
    except DuplicateEmailError:
        return problem_response(
            status=409,
            title="Conflict",
            detail="A user with this email already exists.",
            type_="https://vaultguard.dev/errors/duplicate-email",
        )
    return RegisterUserResponse.from_user(user)
