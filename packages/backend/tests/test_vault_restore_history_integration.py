from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

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
async def test_vault_item_history_and_restore_creates_revision_and_audit_log() -> None:
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
                CREATE TABLE vault_item_revisions (
                    id TEXT PRIMARY KEY,
                    item_id TEXT NOT NULL,
                    encrypted_data TEXT NOT NULL,
                    encrypted_key TEXT NOT NULL,
                    revision_number INTEGER NOT NULL,
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
    email = "restore.owner@example.com"
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
                    "name": "Restore Org",
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
                    "name": "Restore Owner",
                    "role": "MEMBER",
                    "status": "ACTIVE",
                    "public_key": "public-key",
                    "encrypted_private_key": "encrypted-private-key",
                    "auth_verifier_hash": argon2_hasher.hash("Verifier123!"),
                },
            )
            await session.commit()

        create_payload = {
            "type": "login",
            "encrypted_data": "revision-zero-data",
            "encrypted_key": "revision-zero-key",
            "name": "Internal Admin",
            "folder_id": None,
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            create_response = await client.post(
                "/api/v1/vault/items",
                json=create_payload,
                headers={"Authorization": f"Bearer {token}", "User-Agent": "pytest-vault"},
            )
            assert create_response.status_code == 201
            item_id = create_response.json()["id"]

            update_one = await client.put(
                f"/api/v1/vault/items/{item_id}",
                json={
                    "type": "login",
                    "encrypted_data": "revision-one-data",
                    "encrypted_key": "revision-one-key",
                    "name": "Internal Admin",
                    "folder_id": None,
                },
                headers={"Authorization": f"Bearer {token}", "User-Agent": "pytest-vault"},
            )
            assert update_one.status_code == 200

            update_two = await client.put(
                f"/api/v1/vault/items/{item_id}",
                json={
                    "type": "login",
                    "encrypted_data": "revision-two-data",
                    "encrypted_key": "revision-two-key",
                    "name": "Internal Admin",
                    "folder_id": None,
                },
                headers={"Authorization": f"Bearer {token}", "User-Agent": "pytest-vault"},
            )
            assert update_two.status_code == 200

            history_before = await client.get(
                f"/api/v1/vault/items/{item_id}/history",
                headers={"Authorization": f"Bearer {token}", "User-Agent": "pytest-vault"},
            )
            assert history_before.status_code == 200
            history_before_body = history_before.json()
            assert [entry["revision_number"] for entry in history_before_body] == [1, 2]

            restore_response = await client.post(
                f"/api/v1/vault/items/{item_id}/restore",
                json={"revision_number": 1},
                headers={"Authorization": f"Bearer {token}", "User-Agent": "pytest-vault"},
            )
            assert restore_response.status_code == 200
            restore_body = restore_response.json()
            assert restore_body["encrypted_data"] == "revision-zero-data"
            assert restore_body["encrypted_key"] == "revision-zero-key"

            history_after = await client.get(
                f"/api/v1/vault/items/{item_id}/history",
                headers={"Authorization": f"Bearer {token}", "User-Agent": "pytest-vault"},
            )
            assert history_after.status_code == 200
            history_after_body = history_after.json()
            assert [entry["revision_number"] for entry in history_after_body] == [1, 2, 3]

        async with session_factory() as session:
            normalized_item_id = _normalize_uuid(item_id)
            revision_rows = (
                await session.execute(
                    text(
                        """
                        SELECT revision_number, encrypted_data, encrypted_key
                        FROM vault_item_revisions
                        WHERE lower(replace(item_id, '-', '')) = :item_id
                        ORDER BY revision_number ASC
                        """
                    ),
                    {"item_id": normalized_item_id},
                )
            ).all()
            assert len(revision_rows) == 3
            assert int(revision_rows[2].revision_number) == 3
            assert str(revision_rows[2].encrypted_data) == "revision-two-data"
            assert str(revision_rows[2].encrypted_key) == "revision-two-key"

            audit_rows = (
                await session.execute(
                    text(
                        """
                        SELECT action, target_id, actor_id
                        FROM audit_logs
                        WHERE lower(replace(target_id, '-', '')) = :target_id
                        ORDER BY timestamp ASC
                        """
                    ),
                    {"target_id": normalized_item_id},
                )
            ).all()
            assert any(str(row.action).lower() == "restore_item" for row in audit_rows)
            assert all(_normalize_uuid(row.target_id) == normalized_item_id for row in audit_rows)
            assert all(_normalize_uuid(row.actor_id) == _normalize_uuid(user_id) for row in audit_rows)
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()

