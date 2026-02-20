from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.session import get_db_session
from app.main import app
from app.security.password import argon2_hasher


@pytest.mark.asyncio
async def test_register_endpoint_creates_user_and_stores_argon2_hash() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
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

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    async def override_get_db_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    org_id = str(uuid.uuid4())
    payload = {
        "email": "integration@example.com",
        "name": "Integration Test",
        "org_id": org_id,
        "auth_verifier": "VerifierForIntegrationCase123!",
        "public_key": "test-public-key",
        "encrypted_private_key": "test-encrypted-private-key",
    }

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
                    "id": org_id,
                    "name": "Test Org",
                    "subscription_tier": "enterprise",
                    "settings": "{}",
                },
            )
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/auth/register", json=payload)
        assert response.status_code == 201

        async with session_factory() as session:
            result = await session.execute(
                text(
                    """
                    SELECT email, auth_verifier_hash, role, status
                    FROM users
                    WHERE email = :email
                    """
                ),
                {"email": payload["email"]},
            )
            row = result.first()

        assert row is not None
        assert row.email == payload["email"]
        assert row.role == "MEMBER" or row.role == "member"
        assert row.status == "ACTIVE" or row.status == "active"
        assert row.auth_verifier_hash != payload["auth_verifier"]
        assert argon2_hasher.verify(row.auth_verifier_hash, payload["auth_verifier"])
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()

