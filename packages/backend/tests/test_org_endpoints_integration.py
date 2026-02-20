from __future__ import annotations

import uuid
from typing import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.session import get_db_session
from app.main import app
from app.security.password import argon2_hasher
from app.security.tokens import issue_access_token


def _normalize_uuid(value: object) -> str:
    return str(value).replace("-", "").lower()


@pytest.mark.asyncio
async def test_org_create_and_get_promotes_calling_user_to_owner() -> None:
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
                    master_password_hint TEXT NULL,
                    mfa_enabled INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    user_id = uuid.uuid4()
    initial_org_id = uuid.uuid4()
    email = "org.owner@example.com"
    token, _ = issue_access_token(
        user_id=user_id,
        org_id=initial_org_id,
        email=email,
        role="member",
    )

    try:
        async with session_factory() as session:
            await session.execute(
                text(
                    """
                    INSERT INTO organizations (id, name, subscription_tier, settings)
                    VALUES (:id, :name, :subscription_tier, :settings)
                    """
                ),
                {
                    "id": str(initial_org_id),
                    "name": "Bootstrap Org",
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
                    "org_id": str(initial_org_id),
                    "email": email,
                    "name": "Org Creator",
                    "role": "MEMBER",
                    "status": "ACTIVE",
                    "public_key": "public-key",
                    "encrypted_private_key": "encrypted-private-key",
                    "auth_verifier_hash": argon2_hasher.hash("Verifier123!"),
                },
            )
            await session.commit()

        create_payload = {
            "name": "Acme Security",
            "subscription_tier": "enterprise",
            "settings": {"region": "us"},
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            create_response = await client.post(
                "/api/v1/org",
                json=create_payload,
                headers={"Authorization": f"Bearer {token}"},
            )
            assert create_response.status_code == 201
            created_org = create_response.json()
            assert created_org["name"] == create_payload["name"]
            assert created_org["subscription_tier"] == "enterprise"
            assert created_org["settings"] == {"region": "us"}
            assert created_org["created_at"]

            access_token_for_new_org, _ = issue_access_token(
                user_id=user_id,
                org_id=uuid.UUID(created_org["id"]),
                email=email,
                role="owner",
            )
            get_response = await client.get(
                "/api/v1/org",
                headers={"Authorization": f"Bearer {access_token_for_new_org}"},
            )

        assert get_response.status_code == 200
        fetched_org = get_response.json()
        assert fetched_org["id"] == created_org["id"]
        assert fetched_org["name"] == "Acme Security"
        assert fetched_org["subscription_tier"] == "enterprise"
        assert fetched_org["settings"] == {"region": "us"}

        async with session_factory() as session:
            user_row = (
                await session.execute(
                    text(
                        """
                        SELECT org_id, role
                        FROM users
                        WHERE id = :id
                        """
                    ),
                    {"id": str(user_id)},
                )
            ).first()
            assert user_row is not None
            assert _normalize_uuid(user_row.org_id) == _normalize_uuid(created_org["id"])
            assert str(user_row.role) == "OWNER"
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


@pytest.mark.asyncio
async def test_get_org_for_user_without_existing_org_returns_403() -> None:
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
                    master_password_hint TEXT NULL,
                    mfa_enabled INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    user_id = uuid.uuid4()
    missing_org_id = uuid.uuid4()
    email = "org.missing@example.com"
    token, _ = issue_access_token(
        user_id=user_id,
        org_id=missing_org_id,
        email=email,
        role="member",
    )

    try:
        async with session_factory() as session:
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
                    "org_id": str(missing_org_id),
                    "email": email,
                    "name": "Missing Org User",
                    "role": "MEMBER",
                    "status": "ACTIVE",
                    "public_key": "public-key",
                    "encrypted_private_key": "encrypted-private-key",
                    "auth_verifier_hash": argon2_hasher.hash("Verifier123!"),
                },
            )
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/org",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
