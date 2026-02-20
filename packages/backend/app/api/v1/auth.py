from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.problems import problem_response
from app.db.session import get_db_session
from app.schemas.auth import (
    Argon2Params,
    AuthenticatedUserResponse,
    LoginRequest,
    LoginResponse,
    PreauthRequest,
    PreauthResponse,
    RegisterRequest,
    RegisterUserResponse,
)
from app.services.auth import (
    DuplicateEmailError,
    InvalidCredentialsError,
    TooManyAttemptsError,
    login_user,
    register_user,
)


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


@router.post("/preauth", response_model=PreauthResponse)
async def preauth(_: PreauthRequest) -> PreauthResponse:
    return PreauthResponse(
        argon2_params=Argon2Params(
            memory_kib=65536,
            iterations=3,
            parallelism=4,
            hash_len=32,
            salt_len=16,
            type="argon2id",
        )
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> LoginResponse:
    client_ip = request.client.host if request.client and request.client.host else "0.0.0.0"
    user_agent = request.headers.get("user-agent", "")
    try:
        result = await login_user(
            db,
            payload,
            client_ip=client_ip,
            user_agent=user_agent,
        )
    except TooManyAttemptsError:
        return problem_response(
            status=429,
            title="Too Many Requests",
            detail="Too many failed login attempts from this IP address.",
            type_="https://vaultguard.dev/errors/rate-limit-exceeded",
        )
    except InvalidCredentialsError:
        return problem_response(
            status=401,
            title="Unauthorized",
            detail="Invalid email or credentials.",
            type_="https://vaultguard.dev/errors/invalid-credentials",
        )

    return LoginResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        user=AuthenticatedUserResponse.from_user(result.user),
    )
