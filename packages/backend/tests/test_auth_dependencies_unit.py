from __future__ import annotations

import datetime
import uuid
from typing import AsyncIterator

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.dependencies.auth import get_current_user, require_admin
from app.db.session import get_db_session
from app.models.user import User
from app.security.password import argon2_hasher
from app.security.tokens import issue_access_token


def _build_test_app() -> FastAPI:
    app = FastAPI()

    @app.get("/protected")
    async def protected(user: User = Depends(get_current_user)) -> dict[str, str]:
        return {"email": user.email}

    @app.get("/admin")
    async def admin_only(_: User = Depends(require_admin)) -> dict[str, bool]:
        return {"ok": True}

    return app


@pytest.mark.asyncio
async def test_get_current_user_allows_valid_access_token() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE organizations (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    subscription_tier TEXT NOT NULL,
                    settings TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE TABLE users (
                    id TEXT PRIMARY KEY,
                    org_id TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    status TEXT NOT NULL,
                    public_key TEXT NOT NULL,
                    encrypted_private_key TEXT NOT NULL,
                    auth_verifier_hash TEXT NOT NULL,
                    invitation_token_hash TEXT NULL,
                    invitation_expires_at TEXT NULL,
                    master_password_hint TEXT NULL,
                    mfa_enabled INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )

    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    async with session_factory() as session:
        await session.execute(
            text(
                """
                INSERT INTO organizations (id, name, subscription_tier, settings)
                VALUES (:id, :name, :subscription_tier, :settings)
                """
            ),
            {
                "id": str(org_id),
                "name": "Org",
                "subscription_tier": "enterprise",
                "settings": "{}",
            },
        )
        await session.execute(
            text(
                """
                INSERT INTO users (
                    id, org_id, email, name, role, status, public_key, encrypted_private_key, auth_verifier_hash
                ) VALUES (
                    :id, :org_id, :email, :name, :role, :status, :public_key, :encrypted_private_key, :auth_verifier_hash
                )
                """
            ),
            {
                "id": str(user_id),
                "org_id": str(org_id),
                "email": "dep@example.com",
                "name": "Dependency User",
                "role": "MEMBER",
                "status": "ACTIVE",
                "public_key": "pk",
                "encrypted_private_key": "enc",
                "auth_verifier_hash": argon2_hasher.hash("Verifier123!"),
            },
        )
        await session.commit()

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app = _build_test_app()
    app.dependency_overrides[get_db_session] = override_get_db_session
    token, _ = issue_access_token(
        user_id=user_id,
        org_id=org_id,
        email="dep@example.com",
        role="member",
    )

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/protected",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert response.status_code == 200
        assert response.json()["email"] == "dep@example.com"
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


@pytest.mark.asyncio
async def test_get_current_user_rejects_expired_token_with_www_authenticate_header() -> None:
    app = _build_test_app()
    expired_token, _ = issue_access_token(
        user_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        email="expired@example.com",
        role="member",
        now=datetime.datetime.now(datetime.UTC),
        expires_in=datetime.timedelta(seconds=-1),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/protected",
            headers={"Authorization": f"Bearer {expired_token}"},
        )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.asyncio
async def test_require_admin_returns_403_for_non_admin_user() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE organizations (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    subscription_tier TEXT NOT NULL,
                    settings TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE TABLE users (
                    id TEXT PRIMARY KEY,
                    org_id TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    status TEXT NOT NULL,
                    public_key TEXT NOT NULL,
                    encrypted_private_key TEXT NOT NULL,
                    auth_verifier_hash TEXT NOT NULL,
                    invitation_token_hash TEXT NULL,
                    invitation_expires_at TEXT NULL,
                    master_password_hint TEXT NULL,
                    mfa_enabled INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )

    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    async with session_factory() as session:
        await session.execute(
            text(
                """
                INSERT INTO organizations (id, name, subscription_tier, settings)
                VALUES (:id, :name, :subscription_tier, :settings)
                """
            ),
            {
                "id": str(org_id),
                "name": "Org",
                "subscription_tier": "enterprise",
                "settings": "{}",
            },
        )
        await session.execute(
            text(
                """
                INSERT INTO users (
                    id, org_id, email, name, role, status, public_key, encrypted_private_key, auth_verifier_hash
                ) VALUES (
                    :id, :org_id, :email, :name, :role, :status, :public_key, :encrypted_private_key, :auth_verifier_hash
                )
                """
            ),
            {
                "id": str(user_id),
                "org_id": str(org_id),
                "email": "member@example.com",
                "name": "Member User",
                "role": "MEMBER",
                "status": "ACTIVE",
                "public_key": "pk",
                "encrypted_private_key": "enc",
                "auth_verifier_hash": argon2_hasher.hash("Verifier123!"),
            },
        )
        await session.commit()

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app = _build_test_app()
    app.dependency_overrides[get_db_session] = override_get_db_session
    token, _ = issue_access_token(
        user_id=user_id,
        org_id=org_id,
        email="member@example.com",
        role="member",
    )

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/admin",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


