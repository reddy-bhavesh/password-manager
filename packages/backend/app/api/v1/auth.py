import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user
from app.core.problems import problem_response
from app.db.session import get_db_session
from app.models.user import User
from app.schemas.auth import (
    Argon2Params,
    AuthenticatedUserResponse,
    LoginRequest,
    LoginResponse,
    MfaTotpConfirmRequest,
    MfaTotpConfirmResponse,
    MfaTotpEnrollResponse,
    MfaVerifyRequest,
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
    InvalidMfaCodeError,
    InvalidMfaTokenError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    MfaNotEnrolledError,
    SessionNotFoundError,
    TooManyAttemptsError,
    confirm_totp_mfa,
    enroll_totp_mfa,
    verify_mfa_and_issue_tokens,
    refresh_tokens,
    login_user,
    register_user,
    revoke_session_by_id,
    revoke_session_by_refresh_token,
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
        user=AuthenticatedUserResponse.from_user(result.user) if result.user is not None else None,
        mfa_required=result.mfa_required,
        mfa_token=result.mfa_token,
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> None:
    client_ip = request.client.host if request.client and request.client.host else "0.0.0.0"
    user_agent = request.headers.get("user-agent", "")
    try:
        await revoke_session_by_refresh_token(
            db,
            current_user=current_user,
            refresh_token=payload.refresh_token,
            client_ip=client_ip,
            user_agent=user_agent,
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> None:
    client_ip = request.client.host if request.client and request.client.host else "0.0.0.0"
    user_agent = request.headers.get("user-agent", "")
    try:
        await revoke_session_by_id(
            db,
            current_user=current_user,
            session_id=session_id,
            client_ip=client_ip,
            user_agent=user_agent,
        )
    except SessionNotFoundError:
        return problem_response(
            status=404,
            title="Not Found",
            detail="Session not found.",
            type_="https://vaultguard.dev/errors/session-not-found",
        )
    return None


@router.post("/mfa/totp/enroll", response_model=MfaTotpEnrollResponse)
async def enroll_mfa_totp(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> MfaTotpEnrollResponse:
    result = await enroll_totp_mfa(db, current_user=current_user)

    return MfaTotpEnrollResponse(otpauth_uri=result.otpauth_uri, backup_codes=result.backup_codes)


@router.post("/mfa/totp/confirm", response_model=MfaTotpConfirmResponse)
async def confirm_mfa_totp(
    payload: MfaTotpConfirmRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> MfaTotpConfirmResponse:
    client_ip = request.client.host if request.client and request.client.host else "0.0.0.0"
    user_agent = request.headers.get("user-agent", "")
    try:
        await confirm_totp_mfa(
            db,
            current_user=current_user,
            code=payload.code,
            client_ip=client_ip,
            user_agent=user_agent,
        )
    except MfaNotEnrolledError:
        return problem_response(
            status=404,
            title="Not Found",
            detail="MFA enrollment not found.",
            type_="https://vaultguard.dev/errors/mfa-not-enrolled",
        )
    except InvalidMfaCodeError:
        return problem_response(
            status=401,
            title="Unauthorized",
            detail="Invalid or expired MFA code.",
            type_="https://vaultguard.dev/errors/invalid-mfa-code",
        )
    return MfaTotpConfirmResponse(mfa_enabled=True)


@router.post("/mfa/verify", response_model=LoginResponse)
async def verify_mfa(
    payload: MfaVerifyRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> LoginResponse:
    client_ip = request.client.host if request.client and request.client.host else "0.0.0.0"
    user_agent = request.headers.get("user-agent", "")
    try:
        result = await verify_mfa_and_issue_tokens(
            db,
            mfa_token=payload.mfa_token,
            code=payload.code,
            client_ip=client_ip,
            user_agent=user_agent,
        )
    except InvalidMfaTokenError:
        return problem_response(
            status=401,
            title="Unauthorized",
            detail="Invalid or expired MFA challenge token.",
            type_="https://vaultguard.dev/errors/invalid-mfa-token",
        )
    except MfaNotEnrolledError:
        return problem_response(
            status=401,
            title="Unauthorized",
            detail="MFA is not enabled for this account.",
            type_="https://vaultguard.dev/errors/mfa-not-enabled",
        )
    except InvalidMfaCodeError:
        return problem_response(
            status=401,
            title="Unauthorized",
            detail="Invalid or expired MFA code.",
            type_="https://vaultguard.dev/errors/invalid-mfa-code",
        )

    return LoginResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        user=AuthenticatedUserResponse.from_user(result.user) if result.user is not None else None,
        mfa_required=False,
        mfa_token=None,
    )
