import uuid

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.problems import problem_response
from app.db.session import get_db_session
from app.schemas.auth import (
    Argon2Params,
    AuthenticatedUserResponse,
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    PreauthRequest,
    PreauthResponse,
    RefreshRequest,
    RefreshResponse,
    RegisterRequest,
    RegisterUserResponse,
)
from app.services.auth import (
    DuplicateEmailError,
    InvalidAccessTokenError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    SessionNotFoundError,
    TooManyAttemptsError,
    refresh_tokens,
    login_user,
    register_user,
    revoke_session_by_id,
    revoke_session_by_refresh_token,
)


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _extract_bearer_token(authorization: str | None) -> str:
    if authorization is None:
        raise InvalidAccessTokenError("missing authorization header")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise InvalidAccessTokenError("invalid authorization header")
    return token


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


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(
    payload: RefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> RefreshResponse:
    client_ip = request.client.host if request.client and request.client.host else "0.0.0.0"
    user_agent = request.headers.get("user-agent", "")
    try:
        result = await refresh_tokens(
            db,
            payload.refresh_token,
            client_ip=client_ip,
            user_agent=user_agent,
        )
    except InvalidRefreshTokenError:
        return problem_response(
            status=401,
            title="Unauthorized",
            detail="Invalid or expired refresh token.",
            type_="https://vaultguard.dev/errors/invalid-refresh-token",
        )

    return RefreshResponse(access_token=result.access_token, refresh_token=result.refresh_token)


@router.post("/logout", status_code=204)
async def logout(
    payload: LogoutRequest,
    request: Request,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db_session),
) -> None:
    client_ip = request.client.host if request.client and request.client.host else "0.0.0.0"
    user_agent = request.headers.get("user-agent", "")
    try:
        access_token = _extract_bearer_token(authorization)
        await revoke_session_by_refresh_token(
            db,
            access_token=access_token,
            refresh_token=payload.refresh_token,
            client_ip=client_ip,
            user_agent=user_agent,
        )
    except InvalidAccessTokenError:
        return problem_response(
            status=401,
            title="Unauthorized",
            detail="Invalid access token.",
            type_="https://vaultguard.dev/errors/invalid-access-token",
        )
    except SessionNotFoundError:
        return problem_response(
            status=404,
            title="Not Found",
            detail="Session not found.",
            type_="https://vaultguard.dev/errors/session-not-found",
        )
    return None


@router.delete("/sessions/{session_id}", status_code=204)
async def revoke_session(
    session_id: uuid.UUID,
    request: Request,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db_session),
) -> None:
    client_ip = request.client.host if request.client and request.client.host else "0.0.0.0"
    user_agent = request.headers.get("user-agent", "")
    try:
        access_token = _extract_bearer_token(authorization)
        await revoke_session_by_id(
            db,
            access_token=access_token,
            session_id=session_id,
            client_ip=client_ip,
            user_agent=user_agent,
        )
    except InvalidAccessTokenError:
        return problem_response(
            status=401,
            title="Unauthorized",
            detail="Invalid access token.",
            type_="https://vaultguard.dev/errors/invalid-access-token",
        )
    except SessionNotFoundError:
        return problem_response(
            status=404,
            title="Not Found",
            detail="Session not found.",
            type_="https://vaultguard.dev/errors/session-not-found",
        )
    return None
