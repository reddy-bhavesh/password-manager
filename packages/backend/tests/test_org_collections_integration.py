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


async def _setup_org_collection_tables(engine) -> None:
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
                CREATE TABLE groups (
                    id TEXT PRIMARY KEY,
                    org_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE TABLE group_members (
                    group_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    PRIMARY KEY (group_id, user_id)
                )
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE TABLE collections (
                    id TEXT PRIMARY KEY,
                    org_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE TABLE collection_members (
                    collection_id TEXT NOT NULL,
                    user_or_group_id TEXT NOT NULL,
                    permission TEXT NOT NULL,
                    PRIMARY KEY (collection_id, user_or_group_id)
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
                CREATE TABLE collection_items (
                    collection_id TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (collection_id, item_id)
                )
                """
            )
        )


@pytest.mark.asyncio
async def test_org_collections_flow_and_permission_enforcement() -> None:
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
    await _setup_org_collection_tables(engine)

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    org_id = str(uuid.uuid4())
    other_org_id = str(uuid.uuid4())
    admin_id = uuid.uuid4()
    direct_user_id = uuid.uuid4()
    grouped_user_id = uuid.uuid4()
    outsider_user_id = uuid.uuid4()
    item_id = uuid.uuid4()
    group_id = uuid.uuid4()

    admin_token, _ = issue_access_token(
        user_id=admin_id,
        org_id=uuid.UUID(org_id),
        email="admin@acme.test",
        role="admin",
    )
    direct_user_token, _ = issue_access_token(
        user_id=direct_user_id,
        org_id=uuid.UUID(org_id),
        email="direct@acme.test",
        role="member",
    )
    grouped_user_token, _ = issue_access_token(
        user_id=grouped_user_id,
        org_id=uuid.UUID(org_id),
        email="grouped@acme.test",
        role="member",
    )
    outsider_user_token, _ = issue_access_token(
        user_id=outsider_user_id,
        org_id=uuid.UUID(org_id),
        email="outsider@acme.test",
        role="member",
    )

    try:
        async with session_factory() as session:
            await session.execute(
                text(
                    """
                    INSERT INTO organizations (id, name, subscription_tier, settings)
                    VALUES (:id1, 'Acme', 'enterprise', '{}'),
                           (:id2, 'Other', 'enterprise', '{}')
                    """
                ),
                {"id1": org_id, "id2": other_org_id},
            )
            for row in (
                {
                    "id": str(admin_id),
                    "org_id": org_id,
                    "email": "admin@acme.test",
                    "name": "Admin",
                    "role": "ADMIN",
                },
                {
                    "id": str(direct_user_id),
                    "org_id": org_id,
                    "email": "direct@acme.test",
                    "name": "Direct User",
                    "role": "MEMBER",
                },
                {
                    "id": str(grouped_user_id),
                    "org_id": org_id,
                    "email": "grouped@acme.test",
                    "name": "Grouped User",
                    "role": "MEMBER",
                },
                {
                    "id": str(outsider_user_id),
                    "org_id": org_id,
                    "email": "outsider@acme.test",
                    "name": "Outsider User",
                    "role": "MEMBER",
                },
            ):
                await session.execute(
                    text(
                        """
                        INSERT INTO users (
                            id, org_id, email, name, role, status, public_key, encrypted_private_key, auth_verifier_hash
                        ) VALUES (
                            :id, :org_id, :email, :name, :role, 'ACTIVE', 'pub', 'enc-priv', :auth_verifier_hash
                        )
                        """
                    ),
                    {**row, "auth_verifier_hash": argon2_hasher.hash("Verifier123!")},
                )

            await session.execute(
                text(
                    """
                    INSERT INTO groups (id, org_id, name)
                    VALUES (:id, :org_id, 'Engineering')
                    """
                ),
                {"id": str(group_id), "org_id": org_id},
            )
            await session.execute(
                text(
                    """
                    INSERT INTO group_members (group_id, user_id)
                    VALUES (:group_id, :user_id)
                    """
                ),
                {"group_id": str(group_id), "user_id": str(grouped_user_id)},
            )
            await session.execute(
                text(
                    """
                    INSERT INTO vault_items (
                        id, owner_id, org_id, type, encrypted_data, encrypted_key, name, folder_id, favorite
                    ) VALUES (
                        :id, :owner_id, :org_id, :type, :encrypted_data, :encrypted_key, :name, NULL, 0
                    )
                    """
                ),
                {
                    "id": str(item_id),
                    "owner_id": str(admin_id),
                    "org_id": org_id,
                    "type": "LOGIN",
                    "encrypted_data": "ciphertext-1",
                    "encrypted_key": "wrapped-key-1",
                    "name": "Shared Admin Credential",
                },
            )
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            create_collection_response = await client.post(
                "/api/v1/org/collections",
                json={"name": "Engineering Shared"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert create_collection_response.status_code == 201
            collection_body = create_collection_response.json()
            collection_id = collection_body["id"]
            assert collection_body["name"] == "Engineering Shared"
            assert _normalize_uuid(collection_body["org_id"]) == _normalize_uuid(org_id)
            assert _normalize_uuid(collection_body["created_by"]) == _normalize_uuid(admin_id)

            grant_direct_response = await client.post(
                f"/api/v1/org/collections/{collection_id}/members",
                json={"user_or_group_id": str(direct_user_id), "permission": "view"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert grant_direct_response.status_code == 201
            assert grant_direct_response.json()["permission"] == "view"

            grant_group_response = await client.post(
                f"/api/v1/org/collections/{collection_id}/members",
                json={"user_or_group_id": str(group_id), "permission": "edit"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert grant_group_response.status_code == 201
            assert _normalize_uuid(grant_group_response.json()["user_or_group_id"]) == _normalize_uuid(group_id)

            add_item_response = await client.post(
                f"/api/v1/org/collections/{collection_id}/items",
                json={"item_id": str(item_id)},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert add_item_response.status_code == 201
            add_item_body = add_item_response.json()
            assert _normalize_uuid(add_item_body["collection_id"]) == _normalize_uuid(collection_id)
            assert _normalize_uuid(add_item_body["item_id"]) == _normalize_uuid(item_id)

            direct_read_response = await client.get(
                f"/api/v1/org/collections/{collection_id}/items",
                headers={"Authorization": f"Bearer {direct_user_token}"},
            )
            assert direct_read_response.status_code == 200
            direct_items = direct_read_response.json()["items"]
            assert len(direct_items) == 1
            assert _normalize_uuid(direct_items[0]["id"]) == _normalize_uuid(item_id)
            assert direct_items[0]["encrypted_data"] == "ciphertext-1"

            grouped_read_response = await client.get(
                f"/api/v1/org/collections/{collection_id}/items",
                headers={"Authorization": f"Bearer {grouped_user_token}"},
            )
            assert grouped_read_response.status_code == 200
            grouped_items = grouped_read_response.json()["items"]
            assert len(grouped_items) == 1
            assert _normalize_uuid(grouped_items[0]["id"]) == _normalize_uuid(item_id)

            denied_read_response = await client.get(
                f"/api/v1/org/collections/{collection_id}/items",
                headers={"Authorization": f"Bearer {outsider_user_token}"},
            )
            assert denied_read_response.status_code == 403
            assert denied_read_response.headers["content-type"].startswith("application/problem+json")

            revoke_response = await client.delete(
                f"/api/v1/org/collections/{collection_id}/members/{direct_user_id}",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert revoke_response.status_code == 204

            denied_after_revoke = await client.get(
                f"/api/v1/org/collections/{collection_id}/items",
                headers={"Authorization": f"Bearer {direct_user_token}"},
            )
            assert denied_after_revoke.status_code == 403

        async with session_factory() as session:
            collection_rows = (
                await session.execute(
                    text("SELECT id, org_id, name, created_by FROM collections")
                )
            ).all()
            assert len(collection_rows) == 1
            assert _normalize_uuid(collection_rows[0].org_id) == _normalize_uuid(org_id)

            collection_item_rows = (
                await session.execute(
                    text("SELECT collection_id, item_id FROM collection_items")
                )
            ).all()
            assert len(collection_item_rows) == 1
            assert _normalize_uuid(collection_item_rows[0].collection_id) == _normalize_uuid(collection_id)
            assert _normalize_uuid(collection_item_rows[0].item_id) == _normalize_uuid(item_id)
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
