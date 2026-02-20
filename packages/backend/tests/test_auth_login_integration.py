from __future__ import annotations

import hashlib
import uuid

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.settings import settings
from app.db.session import get_db_session
from app.main import app
from app.security.password import argon2_hasher
from app.services.auth import login_rate_limiter


@pytest.mark.asyncio
async def test_preauth_and_login_issue_tokens_and_store_refresh_hash() -> None:
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
        await conn.execute(
            text(
                """
                CREATE TABLE sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    refresh_token_hash TEXT NOT NULL,
                    device_info TEXT NOT NULL DEFAULT '{}',
                    ip_address TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    expires_at TEXT NOT NULL,
                    revoked_at TEXT NULL
                )
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE TABLE audit_logs (
                    id TEXT PRIMARY KEY,
                    org_id TEXT NOT NULL,
                    actor_id TEXT NULL,
                    action TEXT NOT NULL,
                    target_id TEXT NULL,
                    ip_address TEXT NOT NULL,
                    user_agent TEXT NOT NULL,
                    geo_location TEXT NOT NULL,
                    timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )

    async def override_get_db_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    org_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    email = "login@example.com"
    auth_verifier = "ValidVerifier123!"

    try:
        await login_rate_limiter.reset("127.0.0.1")
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
                    "id": user_id,
                    "org_id": org_id,
                    "email": email,
                    "name": "Login User",
                    "role": "MEMBER",
                    "status": "ACTIVE",
                    "public_key": "public-key",
                    "encrypted_private_key": "encrypted-private-key",
                    "auth_verifier_hash": argon2_hasher.hash(auth_verifier),
                },
            )
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            preauth_response = await client.post("/api/v1/auth/preauth", json={"email": email})
            assert preauth_response.status_code == 200
            assert preauth_response.json()["argon2_params"] == {
                "memory_kib": 65536,
                "iterations": 3,
                "parallelism": 4,
                "hash_len": 32,
                "salt_len": 16,
                "type": "argon2id",
            }

            login_response = await client.post(
                "/api/v1/auth/login",
                json={"email": email, "auth_verifier": auth_verifier},
                headers={"user-agent": "pytest"},
            )

        assert login_response.status_code == 200
        body = login_response.json()
        assert body["user"]["email"] == email
        assert body["user"]["role"] == "member"

        decoded = jwt.decode(
            body["access_token"],
            settings.normalized_jwt_public_key,
            algorithms=["RS256"],
            issuer=settings.jwt_issuer,
        )
        assert decoded["sub"] == user_id
        assert decoded["org_id"] == org_id
        assert decoded["exp"] - decoded["iat"] == 15 * 60

        expected_refresh_hash = hashlib.sha256(body["refresh_token"].encode("utf-8")).hexdigest()
        async with session_factory() as session:
            result = await session.execute(
                text(
                    """
                    SELECT user_id, refresh_token_hash
                    FROM sessions
                    """
                )
            )
            row = result.first()

        assert row is not None
        assert str(row.user_id) == user_id.replace("-", "")
        assert row.refresh_token_hash == expected_refresh_hash
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


@pytest.mark.asyncio
async def test_login_rate_limiting_after_more_than_five_failures_from_same_ip() -> None:
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
        await conn.execute(
            text(
                """
                CREATE TABLE sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    refresh_token_hash TEXT NOT NULL,
                    device_info TEXT NOT NULL DEFAULT '{}',
                    ip_address TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    expires_at TEXT NOT NULL,
                    revoked_at TEXT NULL
                )
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE TABLE audit_logs (
                    id TEXT PRIMARY KEY,
                    org_id TEXT NOT NULL,
                    actor_id TEXT NULL,
                    action TEXT NOT NULL,
                    target_id TEXT NULL,
                    ip_address TEXT NOT NULL,
                    user_agent TEXT NOT NULL,
                    geo_location TEXT NOT NULL,
                    timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )

    async def override_get_db_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    org_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    email = "ratelimit@example.com"

    try:
        await login_rate_limiter.reset("127.0.0.1")
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
                    "id": user_id,
                    "org_id": org_id,
                    "email": email,
                    "name": "Rate User",
                    "role": "MEMBER",
                    "status": "ACTIVE",
                    "public_key": "public-key",
                    "encrypted_private_key": "encrypted-private-key",
                    "auth_verifier_hash": argon2_hasher.hash("CorrectVerifier123!"),
                },
            )
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for _ in range(5):
                response = await client.post(
                    "/api/v1/auth/login",
                    json={"email": email, "auth_verifier": "wrong-verifier"},
                )
                assert response.status_code == 401

            response = await client.post(
                "/api/v1/auth/login",
                json={"email": email, "auth_verifier": "wrong-verifier"},
            )

        assert response.status_code == 429
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
