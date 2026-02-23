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


async def _setup_org_groups_tables(engine) -> None:
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


@pytest.mark.asyncio
async def test_org_groups_crud_membership_flow_and_audit_logs() -> None:
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
    await _setup_org_groups_tables(engine)

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    org_id = str(uuid.uuid4())
    other_org_id = str(uuid.uuid4())
    admin_id = uuid.uuid4()
    member_id = uuid.uuid4()
    other_org_user_id = uuid.uuid4()
    admin_token, _ = issue_access_token(
        user_id=admin_id,
        org_id=uuid.UUID(org_id),
        email="admin@acme.test",
        role="admin",
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
                    "status": "ACTIVE",
                },
                {
                    "id": str(member_id),
                    "org_id": org_id,
                    "email": "member@acme.test",
                    "name": "Member",
                    "role": "MEMBER",
                    "status": "ACTIVE",
                },
                {
                    "id": str(other_org_user_id),
                    "org_id": other_org_id,
                    "email": "other@other.test",
                    "name": "Other",
                    "role": "MEMBER",
                    "status": "ACTIVE",
                },
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
                        **row,
                        "public_key": "pub",
                        "encrypted_private_key": "enc-priv",
                        "auth_verifier_hash": argon2_hasher.hash("Verifier123!"),
                    },
                )
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            create_response = await client.post(
                "/api/v1/org/groups",
                json={"name": "Engineering"},
                headers={"Authorization": f"Bearer {admin_token}", "user-agent": "pytest-org-groups"},
            )
            assert create_response.status_code == 201
            create_body = create_response.json()
            group_id = create_body["id"]
            assert create_body["name"] == "Engineering"
            assert create_body["member_count"] == 0

            add_member_response = await client.post(
                f"/api/v1/org/groups/{group_id}/members",
                json={"user_id": str(member_id)},
                headers={"Authorization": f"Bearer {admin_token}", "user-agent": "pytest-org-groups"},
            )
            assert add_member_response.status_code == 201
            add_member_body = add_member_response.json()
            assert _normalize_uuid(add_member_body["group_id"]) == _normalize_uuid(group_id)
            assert _normalize_uuid(add_member_body["user_id"]) == _normalize_uuid(member_id)

            list_response = await client.get(
                "/api/v1/org/groups",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert list_response.status_code == 200
            list_body = list_response.json()
            assert len(list_body["items"]) == 1
            assert list_body["items"][0]["name"] == "Engineering"
            assert list_body["items"][0]["member_count"] == 1

            delete_response = await client.delete(
                f"/api/v1/org/groups/{group_id}/members/{member_id}",
                headers={"Authorization": f"Bearer {admin_token}", "user-agent": "pytest-org-groups"},
            )
            assert delete_response.status_code == 204

            list_after_remove_response = await client.get(
                "/api/v1/org/groups",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert list_after_remove_response.status_code == 200
            assert list_after_remove_response.json()["items"][0]["member_count"] == 0

        async with session_factory() as session:
            group_rows = (await session.execute(text("SELECT id, org_id, name FROM groups"))).all()
            assert len(group_rows) == 1
            assert _normalize_uuid(group_rows[0].org_id) == _normalize_uuid(org_id)
            assert group_rows[0].name == "Engineering"

            member_rows = (await session.execute(text("SELECT group_id, user_id FROM group_members"))).all()
            assert member_rows == []

            audit_rows = (
                await session.execute(
                    text(
                        """
                        SELECT action, actor_id, target_id
                        FROM audit_logs
                        ORDER BY timestamp ASC
                        """
                    )
                )
            ).all()
            assert len(audit_rows) == 3
            audit_actions = [str(row.action).lower() for row in audit_rows]
            assert "create_group" in audit_actions or "auditlogaction.create_group" in audit_actions
            assert "add_group_member" in audit_actions or "auditlogaction.add_group_member" in audit_actions
            assert "remove_group_member" in audit_actions or "auditlogaction.remove_group_member" in audit_actions
            for row in audit_rows:
                assert _normalize_uuid(row.actor_id) == _normalize_uuid(admin_id)
                assert _normalize_uuid(row.target_id) == _normalize_uuid(group_id)
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


@pytest.mark.asyncio
async def test_org_groups_endpoints_require_admin_role() -> None:
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
    await _setup_org_groups_tables(engine)

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    org_id = str(uuid.uuid4())
    member_id = uuid.uuid4()
    member_token, _ = issue_access_token(
        user_id=member_id,
        org_id=uuid.UUID(org_id),
        email="member@acme.test",
        role="member",
    )

    try:
        async with session_factory() as session:
            await session.execute(
                text(
                    """
                    INSERT INTO organizations (id, name, subscription_tier, settings)
                    VALUES (:id, 'Acme', 'enterprise', '{}')
                    """
                ),
                {"id": org_id},
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
                    "id": str(member_id),
                    "org_id": org_id,
                    "email": "member@acme.test",
                    "name": "Member",
                    "role": "MEMBER",
                    "status": "ACTIVE",
                    "public_key": "pub",
                    "encrypted_private_key": "enc-priv",
                    "auth_verifier_hash": argon2_hasher.hash("Verifier123!"),
                },
            )
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/org/groups",
                json={"name": "Forbidden Group"},
                headers={"Authorization": f"Bearer {member_token}"},
            )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
