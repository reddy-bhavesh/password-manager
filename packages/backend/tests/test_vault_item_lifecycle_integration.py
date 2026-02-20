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
async def test_vault_item_get_update_delete_lifecycle_with_revisions_and_access_control() -> None:
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
    owner_id = uuid.uuid4()
    other_user_id = uuid.uuid4()
    owner_email = "vault.owner@example.com"
    other_email = "vault.other@example.com"

    owner_token, _ = issue_access_token(
        user_id=owner_id,
        org_id=org_id,
        email=owner_email,
        role="member",
    )
    other_user_token, _ = issue_access_token(
        user_id=other_user_id,
        org_id=org_id,
        email=other_email,
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
            for user_id, email, display_name in (
                (owner_id, owner_email, "Owner User"),
                (other_user_id, other_email, "Other User"),
            ):
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
                        "name": display_name,
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
            "encrypted_data": "Y3JlYXRlLWJsb2I=",
            "encrypted_key": "Y3JlYXRlLWtleQ==",
            "name": "Prod Login",
            "folder_id": None,
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            create_response = await client.post(
                "/api/v1/vault/items",
                json=create_payload,
                headers={"Authorization": f"Bearer {owner_token}", "User-Agent": "pytest-vault"},
            )
            assert create_response.status_code == 201
            item_id = create_response.json()["id"]

            own_get = await client.get(
                f"/api/v1/vault/items/{item_id}",
                headers={"Authorization": f"Bearer {owner_token}", "User-Agent": "pytest-vault"},
            )
            assert own_get.status_code == 200
            own_get_body = own_get.json()
            assert own_get_body["id"] == item_id
            assert own_get_body["encrypted_data"] == create_payload["encrypted_data"]
            assert own_get_body["encrypted_key"] == create_payload["encrypted_key"]

            forbidden_get = await client.get(
                f"/api/v1/vault/items/{item_id}",
                headers={"Authorization": f"Bearer {other_user_token}", "User-Agent": "pytest-vault"},
            )
            assert forbidden_get.status_code == 403

            for index in range(1, 13):
                update_payload = {
                    "type": "login",
                    "encrypted_data": f"ZW5jcnlwdGVkLWRhdGEt{index}",
                    "encrypted_key": f"ZW5jcnlwdGVkLWtleS0{index}",
                    "name": f"Prod Login v{index}",
                    "folder_id": None,
                }
                update_response = await client.put(
                    f"/api/v1/vault/items/{item_id}",
                    json=update_payload,
                    headers={"Authorization": f"Bearer {owner_token}", "User-Agent": "pytest-vault"},
                )
                assert update_response.status_code == 200
                update_body = update_response.json()
                assert update_body["encrypted_data"] == update_payload["encrypted_data"]
                assert update_body["encrypted_key"] == update_payload["encrypted_key"]
                assert update_body["name"] == update_payload["name"]

            delete_response = await client.delete(
                f"/api/v1/vault/items/{item_id}",
                headers={"Authorization": f"Bearer {owner_token}", "User-Agent": "pytest-vault"},
            )
            assert delete_response.status_code == 204

            deleted_get = await client.get(
                f"/api/v1/vault/items/{item_id}",
                headers={"Authorization": f"Bearer {owner_token}", "User-Agent": "pytest-vault"},
            )
            assert deleted_get.status_code == 404

        async with session_factory() as session:
            normalized_item_id = _normalize_uuid(item_id)
            item_row = (
                await session.execute(
                    text(
                        """
                        SELECT owner_id, deleted_at, encrypted_data, encrypted_key
                        FROM vault_items
                        WHERE lower(replace(id, '-', '')) = :item_id
                        """
                    ),
                    {"item_id": normalized_item_id},
                )
            ).first()
            assert item_row is not None
            assert _normalize_uuid(item_row.owner_id) == _normalize_uuid(owner_id)
            assert item_row.deleted_at is not None
            assert item_row.encrypted_data == "ZW5jcnlwdGVkLWRhdGEt12"
            assert item_row.encrypted_key == "ZW5jcnlwdGVkLWtleS012"

            revisions = (
                await session.execute(
                    text(
                        """
                        SELECT revision_number
                        FROM vault_item_revisions
                        WHERE lower(replace(item_id, '-', '')) = :item_id
                        ORDER BY revision_number ASC
                        """
                    ),
                    {"item_id": normalized_item_id},
                )
            ).all()
            revision_numbers = [int(row.revision_number) for row in revisions]
            assert len(revision_numbers) == 10
            assert revision_numbers == list(range(3, 13))

            audit_rows = (
                await session.execute(
                    text(
                        """
                        SELECT action, actor_id, target_id
                        FROM audit_logs
                        WHERE lower(replace(target_id, '-', '')) = :target_id
                        ORDER BY timestamp ASC
                        """
                    ),
                    {"target_id": normalized_item_id},
                )
            ).all()
            audit_actions = [str(row.action).lower() for row in audit_rows]
            assert audit_actions.count("create_item") == 1
            assert audit_actions.count("view_item") == 1
            assert audit_actions.count("edit_item") == 12
            assert audit_actions.count("delete_item") == 1
            for row in audit_rows:
                assert _normalize_uuid(row.actor_id) == _normalize_uuid(owner_id)
                assert _normalize_uuid(row.target_id) == _normalize_uuid(item_id)
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()

