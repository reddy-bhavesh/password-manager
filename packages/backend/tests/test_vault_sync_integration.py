from __future__ import annotations

import datetime
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


@pytest.mark.asyncio
async def test_vault_full_and_delta_sync_paginated_and_excludes_deleted_items() -> None:
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
    owner_email = "sync.owner@example.com"
    other_email = "sync.other@example.com"

    owner_token, _ = issue_access_token(
        user_id=owner_id,
        org_id=org_id,
        email=owner_email,
        role="member",
    )

    base_time = datetime.datetime(2026, 2, 20, 12, 0, 0, tzinfo=datetime.UTC)
    deleted_indexes = {5, 9, 33, 90, 121}
    expected_active_ids: list[str] = []
    expected_delta_ids: list[str] = []
    delta_since = base_time + datetime.timedelta(seconds=80)

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
                    "name": "Sync Org",
                    "subscription_tier": "enterprise",
                    "settings": "{}",
                },
            )
            for user_id, email, display_name in (
                (owner_id, owner_email, "Sync Owner"),
                (other_user_id, other_email, "Sync Other"),
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

            for index in range(1, 126):
                item_id = str(uuid.uuid4())
                updated_at = base_time + datetime.timedelta(seconds=index)
                deleted_at = updated_at if index in deleted_indexes else None
                if deleted_at is None:
                    expected_active_ids.append(item_id)
                    if updated_at > delta_since:
                        expected_delta_ids.append(item_id)
                await session.execute(
                    text(
                        """
                        INSERT INTO vault_items (
                            id,
                            owner_id,
                            org_id,
                            type,
                            encrypted_data,
                            encrypted_key,
                            name,
                            folder_id,
                            favorite,
                            created_at,
                            updated_at,
                            deleted_at
                        ) VALUES (
                            :id,
                            :owner_id,
                            :org_id,
                            :type,
                            :encrypted_data,
                            :encrypted_key,
                            :name,
                            :folder_id,
                            :favorite,
                            :created_at,
                            :updated_at,
                            :deleted_at
                        )
                        """
                    ),
                    {
                        "id": item_id,
                        "owner_id": str(owner_id),
                        "org_id": str(org_id),
                        "type": "LOGIN",
                        "encrypted_data": f"encrypted-data-{index}",
                        "encrypted_key": f"encrypted-key-{index}",
                        "name": f"Item {index}",
                        "folder_id": None,
                        "favorite": 0,
                        "created_at": updated_at.isoformat(),
                        "updated_at": updated_at.isoformat(),
                        "deleted_at": deleted_at.isoformat() if deleted_at else None,
                    },
                )

            for index in range(1, 11):
                updated_at = base_time + datetime.timedelta(seconds=200 + index)
                await session.execute(
                    text(
                        """
                        INSERT INTO vault_items (
                            id,
                            owner_id,
                            org_id,
                            type,
                            encrypted_data,
                            encrypted_key,
                            name,
                            folder_id,
                            favorite,
                            created_at,
                            updated_at,
                            deleted_at
                        ) VALUES (
                            :id,
                            :owner_id,
                            :org_id,
                            :type,
                            :encrypted_data,
                            :encrypted_key,
                            :name,
                            :folder_id,
                            :favorite,
                            :created_at,
                            :updated_at,
                            :deleted_at
                        )
                        """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "owner_id": str(other_user_id),
                        "org_id": str(org_id),
                        "type": "LOGIN",
                        "encrypted_data": f"other-data-{index}",
                        "encrypted_key": f"other-key-{index}",
                        "name": f"Other {index}",
                        "folder_id": None,
                        "favorite": 0,
                        "created_at": updated_at.isoformat(),
                        "updated_at": updated_at.isoformat(),
                        "deleted_at": None,
                    },
                )
            await session.commit()

        assert len(expected_active_ids) == 120
        assert len(expected_delta_ids) > 0

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            page_one = await client.get(
                "/api/v1/vault?limit=50&offset=0",
                headers={"Authorization": f"Bearer {owner_token}"},
            )
            assert page_one.status_code == 200
            assert page_one.headers.get("x-vault-revision")
            page_one_body = page_one.json()
            assert page_one_body["total"] == 120
            assert page_one_body["limit"] == 50
            assert page_one_body["offset"] == 0
            assert len(page_one_body["items"]) == 50

            page_three = await client.get(
                "/api/v1/vault?limit=50&offset=100",
                headers={"Authorization": f"Bearer {owner_token}"},
            )
            assert page_three.status_code == 200
            page_three_body = page_three.json()
            assert page_three_body["total"] == 120
            assert len(page_three_body["items"]) == 20

            delta = await client.get(
                f"/api/v1/vault/sync?since={delta_since.isoformat().replace('+00:00', 'Z')}&limit=200&offset=0",
                headers={"Authorization": f"Bearer {owner_token}"},
            )
            assert delta.status_code == 200
            assert delta.headers.get("x-vault-revision")
            delta_body = delta.json()
            returned_delta_ids = {item["id"] for item in delta_body["items"]}
            assert returned_delta_ids == set(expected_delta_ids)
            assert delta_body["total"] == len(expected_delta_ids)
            assert len(delta_body["items"]) == len(expected_delta_ids)
            for item in delta_body["items"]:
                assert item["deleted_at"] is None
                updated_at = datetime.datetime.fromisoformat(item["updated_at"].replace("Z", "+00:00"))
                assert updated_at > delta_since
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()

