from __future__ import annotations

import json
import uuid

import bcrypt
import pyotp
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
async def test_mfa_enroll_confirm_and_verify_login_with_backup_code() -> None:
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
        await conn.execute(
            text(
                """
                CREATE TABLE mfa_totp_credentials (
                    user_id TEXT PRIMARY KEY,
                    org_id TEXT NOT NULL,
                    totp_secret TEXT NOT NULL,
                    backup_code_hashes JSON NOT NULL DEFAULT '[]',
                    confirmed_at TEXT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )

    async def override_get_db_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    org_id = uuid.uuid4().hex
    user_id = uuid.uuid4().hex
    email = "mfa-user@example.com"
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
                    "name": "MFA User",
                    "role": "MEMBER",
                    "status": "ACTIVE",
                    "public_key": "public-key",
                    "encrypted_private_key": "encrypted-private-key",
                    "auth_verifier_hash": argon2_hasher.hash(auth_verifier),
                },
            )
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            initial_login = await client.post(
                "/api/v1/auth/login",
                json={"email": email, "auth_verifier": auth_verifier},
            )
            assert initial_login.status_code == 200
            access_token = initial_login.json()["access_token"]
            assert access_token is not None

            enroll_response = await client.post(
                "/api/v1/auth/mfa/totp/enroll",
                headers={"authorization": f"Bearer {access_token}"},
            )
            assert enroll_response.status_code == 200
            enroll_body = enroll_response.json()
            assert enroll_body["otpauth_uri"].startswith("otpauth://totp/VaultGuard:")
            assert len(enroll_body["backup_codes"]) == 8

        async with session_factory() as session:
            mfa_row_result = await session.execute(
                text(
                    """
                    SELECT totp_secret, backup_code_hashes
                    FROM mfa_totp_credentials
                    WHERE user_id = :user_id
                    """
                ),
                {"user_id": user_id},
            )
            mfa_row = mfa_row_result.first()
        assert mfa_row is not None
        backup_hashes = (
            json.loads(mfa_row.backup_code_hashes)
            if isinstance(mfa_row.backup_code_hashes, str)
            else mfa_row.backup_code_hashes
        )
        assert backup_hashes[0] != enroll_body["backup_codes"][0]
        assert bcrypt.checkpw(
            enroll_body["backup_codes"][0].replace("-", "").encode("utf-8"),
            backup_hashes[0].encode("utf-8"),
        )

        first_totp_code = pyotp.TOTP(mfa_row.totp_secret).now()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            confirm_response = await client.post(
                "/api/v1/auth/mfa/totp/confirm",
                json={"code": first_totp_code},
                headers={"authorization": f"Bearer {access_token}", "user-agent": "pytest-mfa"},
            )
            assert confirm_response.status_code == 200
            assert confirm_response.json()["mfa_enabled"] is True

            mfa_login_response = await client.post(
                "/api/v1/auth/login",
                json={"email": email, "auth_verifier": auth_verifier},
            )
            assert mfa_login_response.status_code == 200
            mfa_login_body = mfa_login_response.json()
            assert mfa_login_body["mfa_required"] is True
            assert mfa_login_body["mfa_token"] is not None
            assert mfa_login_body["access_token"] is None

            invalid_code_response = await client.post(
                "/api/v1/auth/mfa/verify",
                json={"mfa_token": mfa_login_body["mfa_token"], "code": "000000"},
            )
            assert invalid_code_response.status_code == 401

            verify_response = await client.post(
                "/api/v1/auth/mfa/verify",
                json={"mfa_token": mfa_login_body["mfa_token"], "code": enroll_body["backup_codes"][0]},
                headers={"user-agent": "pytest-mfa"},
            )
            assert verify_response.status_code == 200
            verify_body = verify_response.json()
            assert verify_body["access_token"] is not None
            assert verify_body["refresh_token"] is not None
            assert verify_body["mfa_required"] is False

            replay_backup_response = await client.post(
                "/api/v1/auth/mfa/verify",
                json={"mfa_token": mfa_login_body["mfa_token"], "code": enroll_body["backup_codes"][0]},
            )
            assert replay_backup_response.status_code == 401

        async with session_factory() as session:
            user_result = await session.execute(
                text(
                    """
                    SELECT mfa_enabled
                    FROM users
                    WHERE id = :user_id
                    """
                ),
                {"user_id": user_id},
            )
            user_row = user_result.first()
            assert user_row is not None
            assert user_row.mfa_enabled == 1

            audit_result = await session.execute(
                text(
                    """
                    SELECT action
                    FROM audit_logs
                    """
                )
            )
            actions = {str(row.action) for row in audit_result.fetchall()}
            assert "MFA_ENABLE" in actions
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
