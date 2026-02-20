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
async def test_create_vault_item_endpoint_requires_auth_and_persists_item_and_audit_log() -> None:
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
                CREATE TABLE vault_items (
                    id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    org_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    encrypted_data TEXT NOT NULL,
                    encrypted_key TEXT NOT NULL,
                    name TEXT NOT NULL,
                    folder_id TEXT NULL,
                    favorite INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    deleted_at TEXT NULL
                )
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE TABLE folders (
                    id TEXT PRIMARY KEY,
                    org_id TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    parent_folder_id TEXT NULL,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    email = "vault.integration@example.com"
    token, _ = issue_access_token(
        user_id=user_id,
        org_id=org_id,
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
                    "email": email,
                    "name": "Vault Integration User",
                    "role": "MEMBER",
                    "status": "ACTIVE",
                    "public_key": "public-key",
                    "encrypted_private_key": "encrypted-private-key",
                    "auth_verifier_hash": argon2_hasher.hash("Verifier123!"),
                },
            )
            await session.commit()

        payload = {
            "type": "login",
            "encrypted_data": "QmFzZTY0RW5jcnlwdGVkQmxvYg==",
            "encrypted_key": "QmFzZTY0V3JhcHBlZEtleQ==",
            "name": "GitHub Production",
            "folder_id": None,
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            unauthorized = await client.post("/api/v1/vault/items", json=payload)
            assert unauthorized.status_code == 401

            response = await client.post(
                "/api/v1/vault/items",
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "User-Agent": "pytest-vault",
                },
            )

        assert response.status_code == 201
        body = response.json()
        assert body["type"] == "login"
        assert body["name"] == payload["name"]
        assert uuid.UUID(body["id"])
        assert body["created_at"]

        async with session_factory() as session:
            item_result = await session.execute(
                text(
                    """
                    SELECT id, owner_id, org_id, encrypted_data, encrypted_key
                    FROM vault_items
                    """
                )
            )
            item_row = item_result.first()
            assert item_row is not None
            assert _normalize_uuid(item_row.owner_id) == _normalize_uuid(user_id)
            assert _normalize_uuid(item_row.org_id) == _normalize_uuid(org_id)
            assert item_row.encrypted_data == payload["encrypted_data"]
            assert item_row.encrypted_key == payload["encrypted_key"]

            audit_result = await session.execute(
                text(
                    """
                    SELECT action, target_id, actor_id
                    FROM audit_logs
                    """
                )
            )
            audit_row = audit_result.first()
            assert audit_row is not None
            assert str(audit_row.action) == "CREATE_ITEM"
            assert _normalize_uuid(audit_row.target_id) == _normalize_uuid(item_row.id)
            assert _normalize_uuid(audit_row.actor_id) == _normalize_uuid(user_id)
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()

