from __future__ import annotations

import hashlib
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.session import get_db_session
from app.main import app
from app.security.password import argon2_hasher
from app.services.auth import login_rate_limiter


@pytest.mark.asyncio
async def test_refresh_logout_and_delete_session_revoke_and_audit() -> None:
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
    email = "sessionflow@example.com"
    auth_verifier = "CorrectVerifier123!"

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
                    "name": "Session User",
                    "role": "MEMBER",
                    "status": "ACTIVE",
                    "public_key": "public-key",
                    "encrypted_private_key": "encrypted-private-key",
                    "auth_verifier_hash": argon2_hasher.hash(auth_verifier),
                },
            )
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            login_response = await client.post(
                "/api/v1/auth/login",
                json={"email": email, "auth_verifier": auth_verifier},
                headers={"user-agent": "pytest-auth3"},
            )
            assert login_response.status_code == 200
            login_body = login_response.json()
            initial_access = login_body["access_token"]
            initial_refresh = login_body["refresh_token"]

            refresh_response = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": initial_refresh},
                headers={"user-agent": "pytest-auth3"},
            )
            assert refresh_response.status_code == 200
            refresh_body = refresh_response.json()
            rotated_access = refresh_body["access_token"]
            rotated_refresh = refresh_body["refresh_token"]
            assert rotated_refresh != initial_refresh

            replay_response = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": initial_refresh},
                headers={"user-agent": "pytest-auth3"},
            )
            assert replay_response.status_code == 401

            logout_response = await client.post(
                "/api/v1/auth/logout",
                json={"refresh_token": rotated_refresh},
                headers={
                    "authorization": f"Bearer {rotated_access}",
                    "user-agent": "pytest-auth3",
                },
            )
            assert logout_response.status_code == 204

            second_login = await client.post(
                "/api/v1/auth/login",
                json={"email": email, "auth_verifier": auth_verifier},
                headers={"user-agent": "pytest-auth3"},
            )
            assert second_login.status_code == 200
            second_access = second_login.json()["access_token"]
            second_refresh = second_login.json()["refresh_token"]

        second_refresh_hash = hashlib.sha256(second_refresh.encode("utf-8")).hexdigest()
        async with session_factory() as session:
            second_session_result = await session.execute(
                text(
                    """
                    SELECT id
                    FROM sessions
                    WHERE refresh_token_hash = :refresh_hash
                    """
                ),
                {"refresh_hash": second_refresh_hash},
            )
            second_session_row = second_session_result.first()
        assert second_session_row is not None
        second_session_id = str(second_session_row.id)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            revoke_response = await client.delete(
                f"/api/v1/auth/sessions/{second_session_id}",
                headers={
                    "authorization": f"Bearer {second_access}",
                    "user-agent": "pytest-auth3",
                },
            )
            assert revoke_response.status_code == 204

        initial_refresh_hash = hashlib.sha256(initial_refresh.encode("utf-8")).hexdigest()
        rotated_refresh_hash = hashlib.sha256(rotated_refresh.encode("utf-8")).hexdigest()
        async with session_factory() as session:
            session_rows = await session.execute(
                text(
                    """
                    SELECT refresh_token_hash, revoked_at
                    FROM sessions
                    WHERE refresh_token_hash IN (:initial_hash, :rotated_hash, :second_hash)
                    """
                ),
                {
                    "initial_hash": initial_refresh_hash,
                    "rotated_hash": rotated_refresh_hash,
                    "second_hash": second_refresh_hash,
                },
            )
            rows = {str(row.refresh_token_hash): row.revoked_at for row in session_rows.fetchall()}
            assert rows[initial_refresh_hash] is not None
            assert rows[rotated_refresh_hash] is not None
            assert rows[second_refresh_hash] is not None

            audit_rows = await session.execute(
                text(
                    """
                    SELECT action
                    FROM audit_logs
                    """
                )
            )
            actions = {str(row.action) for row in audit_rows.fetchall()}

        assert "REFRESH_TOKEN" in actions
        assert "LOGOUT" in actions
        assert "SESSION_REVOKE" in actions
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()

