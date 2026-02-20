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
async def test_folder_crud_tree_and_delete_cascade_behavior() -> None:
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

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    org_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    other_user_id = uuid.uuid4()
    owner_email = "folders.owner@example.com"
    other_email = "folders.other@example.com"

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

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            create_root = await client.post(
                "/api/v1/vault/folders",
                json={"name": "Root A"},
                headers={"Authorization": f"Bearer {owner_token}"},
            )
            assert create_root.status_code == 201
            root_a_id = create_root.json()["id"]

            create_root_b = await client.post(
                "/api/v1/vault/folders",
                json={"name": "Root B"},
                headers={"Authorization": f"Bearer {owner_token}"},
            )
            assert create_root_b.status_code == 201
            root_b_id = create_root_b.json()["id"]

            create_child = await client.post(
                "/api/v1/vault/folders",
                json={"name": "Child", "parent_folder_id": root_a_id},
                headers={"Authorization": f"Bearer {owner_token}"},
            )
            assert create_child.status_code == 201
            child_id = create_child.json()["id"]

            tree_response = await client.get(
                "/api/v1/vault/folders",
                headers={"Authorization": f"Bearer {owner_token}"},
            )
            assert tree_response.status_code == 200
            tree = tree_response.json()
            root_a = next(node for node in tree if _normalize_uuid(node["id"]) == _normalize_uuid(root_a_id))
            assert len(root_a["children"]) == 1
            assert _normalize_uuid(root_a["children"][0]["id"]) == _normalize_uuid(child_id)

            forbidden_update = await client.patch(
                f"/api/v1/vault/folders/{root_a_id}",
                json={"name": "Malicious Rename"},
                headers={"Authorization": f"Bearer {other_user_token}"},
            )
            assert forbidden_update.status_code == 403

            update_child = await client.patch(
                f"/api/v1/vault/folders/{child_id}",
                json={"name": "Child Renamed", "parent_folder_id": root_b_id},
                headers={"Authorization": f"Bearer {owner_token}"},
            )
            assert update_child.status_code == 200
            updated_child = update_child.json()
            assert updated_child["name"] == "Child Renamed"
            assert _normalize_uuid(updated_child["parent_folder_id"]) == _normalize_uuid(root_b_id)

        async with session_factory() as session:
            await session.execute(
                text(
                    """
                    INSERT INTO vault_items (
                        id, owner_id, org_id, type, encrypted_data, encrypted_key, name, folder_id
                    ) VALUES (
                        :id, :owner_id, :org_id, :type, :encrypted_data, :encrypted_key, :name, :folder_id
                    )
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "owner_id": str(owner_id),
                    "org_id": str(org_id),
                    "type": "LOGIN",
                    "encrypted_data": "blob",
                    "encrypted_key": "key",
                    "name": "Folder-bound Item",
                    "folder_id": root_b_id,
                },
            )
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            delete_root_b = await client.delete(
                f"/api/v1/vault/folders/{root_b_id}",
                headers={"Authorization": f"Bearer {owner_token}"},
            )
            assert delete_root_b.status_code == 204

        async with session_factory() as session:
            deleted_root = (
                await session.execute(
                    text(
                        """
                        SELECT id FROM folders
                        WHERE lower(replace(id, '-', '')) = :folder_id
                        """
                    ),
                    {"folder_id": _normalize_uuid(root_b_id)},
                )
            ).first()
            assert deleted_root is None

            child_folder = (
                await session.execute(
                    text(
                        """
                        SELECT parent_folder_id FROM folders
                        WHERE lower(replace(id, '-', '')) = :folder_id
                        """
                    ),
                    {"folder_id": _normalize_uuid(child_id)},
                )
            ).first()
            assert child_folder is not None
            assert child_folder.parent_folder_id is None

            item_row = (
                await session.execute(
                    text(
                        """
                        SELECT folder_id FROM vault_items
                        WHERE owner_id = :owner_id
                        """
                    ),
                    {"owner_id": str(owner_id)},
                )
            ).first()
            assert item_row is not None
            assert item_row.folder_id is None
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()

