from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.models.user import User, UserRole
from app.services.auth import InvalidAccessTokenError, get_user_from_access_token


bearer_scheme = HTTPBearer(auto_error=False)

_ROLE_RANK: dict[str, int] = {
    UserRole.VIEWER.value: 0,
    UserRole.MEMBER.value: 1,
    UserRole.MANAGER.value: 2,
    UserRole.ADMIN.value: 3,
    UserRole.OWNER.value: 4,
}


def _unauthorized(detail: str = "Invalid or expired access token.") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _normalize_role(role: object) -> str | None:
    if isinstance(role, UserRole):
        return role.value
    if role is None:
        return None
    text = str(role).strip().lower()
    return text if text in _ROLE_RANK else None


async def get_access_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    if credentials is None:
        raise _unauthorized("Missing bearer token.")
    if credentials.scheme.lower() != "bearer" or not credentials.credentials.strip():
        raise _unauthorized("Invalid authorization scheme.")
    return credentials.credentials


async def get_current_user(
    access_token: str = Depends(get_access_token),
    db: AsyncSession = Depends(get_db_session),
) -> User:
    try:
        return await get_user_from_access_token(db, access_token)
    except InvalidAccessTokenError as exc:
        raise _unauthorized() from exc


def require_role(required_role: UserRole | str) -> Callable[[User], User]:
    normalized_required = _normalize_role(required_role)
    if normalized_required is None:
        raise ValueError(f"Unsupported role: {required_role!r}")

    async def role_dependency(current_user: User = Depends(get_current_user)) -> User:
        current_role = _normalize_role(current_user.role)
        if current_role is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User role is not authorized.",
            )
        if _ROLE_RANK[current_role] < _ROLE_RANK[normalized_required]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions for this resource.",
            )
        return current_user

    return role_dependency


def require_admin(current_user: User = Depends(require_role(UserRole.ADMIN))) -> User:
    return current_user

