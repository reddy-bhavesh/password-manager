from __future__ import annotations

import datetime
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


async def _setup_org_user_management_tables(engine) -> None:
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


@pytest.mark.asyncio
async def test_org_user_management_list_role_change_and_offboard_flow() -> None:
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
    await _setup_org_user_management_tables(engine)

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    org_id = str(uuid.uuid4())
    other_org_id = str(uuid.uuid4())
    admin_id = uuid.uuid4()
    target_user_id = uuid.uuid4()
    invited_user_id = uuid.uuid4()
    foreign_user_id = uuid.uuid4()
    admin_token, _ = issue_access_token(
        user_id=admin_id,
        org_id=uuid.UUID(org_id),
        email="admin@acme.test",
        role="admin",
    )

    active_session_1 = uuid.uuid4()
    active_session_2 = uuid.uuid4()
    already_revoked_session = uuid.uuid4()
    now_plus_week = (datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=7)).isoformat()
    pre_revoked_at = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)).isoformat()

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
            users_payload = [
                {
                    "id": str(admin_id),
                    "org_id": org_id,
                    "email": "admin@acme.test",
                    "name": "Admin User",
                    "role": "ADMIN",
                    "status": "ACTIVE",
                    "mfa_enabled": 1,
                },
                {
                    "id": str(target_user_id),
                    "org_id": org_id,
                    "email": "member@acme.test",
                    "name": "Member User",
                    "role": "MEMBER",
                    "status": "ACTIVE",
                    "mfa_enabled": 0,
                },
                {
                    "id": str(invited_user_id),
                    "org_id": org_id,
                    "email": "invited@acme.test",
                    "name": "Invited User",
                    "role": "VIEWER",
                    "status": "INVITED",
                    "mfa_enabled": 0,
                },
                {
                    "id": str(foreign_user_id),
                    "org_id": other_org_id,
                    "email": "foreign@other.test",
                    "name": "Foreign User",
                    "role": "MEMBER",
                    "status": "ACTIVE",
                    "mfa_enabled": 0,
                },
            ]
            for user in users_payload:
                await session.execute(
                    text(
                        """
                        INSERT INTO users (
                            id, org_id, email, name, role, status, public_key, encrypted_private_key,
                            auth_verifier_hash, mfa_enabled
                        ) VALUES (
                            :id, :org_id, :email, :name, :role, :status, :public_key, :encrypted_private_key,
                            :auth_verifier_hash, :mfa_enabled
                        )
                        """
                    ),
                    {
                        **user,
                        "public_key": "pub",
                        "encrypted_private_key": "enc-priv",
                        "auth_verifier_hash": argon2_hasher.hash("Verifier123!"),
                    },
                )

            for session_row in (
                {"id": str(active_session_1), "revoked_at": None},
                {"id": str(active_session_2), "revoked_at": None},
                {"id": str(already_revoked_session), "revoked_at": pre_revoked_at},
            ):
                await session.execute(
                    text(
                        """
                        INSERT INTO sessions (
                            id, user_id, refresh_token_hash, device_info, ip_address, expires_at, revoked_at
                        ) VALUES (
                            :id, :user_id, :refresh_token_hash, :device_info, :ip_address, :expires_at, :revoked_at
                        )
                        """
                    ),
                    {
                        "id": session_row["id"],
                        "user_id": str(target_user_id),
                        "refresh_token_hash": f"hash-{session_row['id']}",
                        "device_info": "{}",
                        "ip_address": "127.0.0.1",
                        "expires_at": now_plus_week,
                        "revoked_at": session_row["revoked_at"],
                    },
                )
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            list_response = await client.get(
                "/api/v1/org/users",
                params={"limit": 10, "offset": 0, "role": "member", "status": "active"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert list_response.status_code == 200
            list_body = list_response.json()
            assert list_body["limit"] == 10
            assert list_body["offset"] == 0
            assert list_body["total"] == 1
            assert [row["email"] for row in list_body["items"]] == ["member@acme.test"]

            patch_response = await client.patch(
                f"/api/v1/org/users/{target_user_id}/role",
                json={"role": "manager"},
                headers={"Authorization": f"Bearer {admin_token}", "user-agent": "pytest-org-mgmt"},
            )
            assert patch_response.status_code == 200
            assert patch_response.json()["role"] == "manager"

            delete_response = await client.delete(
                f"/api/v1/org/users/{target_user_id}",
                headers={"Authorization": f"Bearer {admin_token}", "user-agent": "pytest-org-mgmt"},
            )
            assert delete_response.status_code == 204

        async with session_factory() as session:
            target_user_row = (
                await session.execute(
                    text("SELECT role, status FROM users WHERE id = :id"),
                    {"id": str(target_user_id)},
                )
            ).first()
            assert target_user_row is not None
            assert str(target_user_row.role).lower() in {"manager", "userrole.manager"}
            assert str(target_user_row.status).lower() in {"suspended", "userstatus.suspended"}

            session_rows = (
                await session.execute(
                    text("SELECT id, revoked_at FROM sessions WHERE user_id = :user_id"),
                    {"user_id": str(target_user_id)},
                )
            ).all()
            assert len(session_rows) == 3
            revoked_map = {row.id: row.revoked_at for row in session_rows}
            assert revoked_map[str(active_session_1)] is not None
            assert revoked_map[str(active_session_2)] is not None
            assert revoked_map[str(already_revoked_session)] is not None

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
            audit_rows = [
                row
                for row in audit_rows
                if _normalize_uuid(row.target_id) == _normalize_uuid(target_user_id)
            ]
            audit_actions = [str(row.action).lower() for row in audit_rows]
            assert "change_user_role" in audit_actions or "auditlogaction.change_user_role" in audit_actions
            assert "offboard_user" in audit_actions or "auditlogaction.offboard_user" in audit_actions
            for row in audit_rows:
                assert _normalize_uuid(row.actor_id) == _normalize_uuid(admin_id)
                assert _normalize_uuid(row.target_id) == _normalize_uuid(target_user_id)
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


@pytest.mark.asyncio
async def test_org_user_management_rejects_owner_offboard_with_409() -> None:
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
    await _setup_org_user_management_tables(engine)

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    org_id = str(uuid.uuid4())
    owner_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    owner_token, _ = issue_access_token(
        user_id=owner_id,
        org_id=uuid.UUID(org_id),
        email="owner@acme.test",
        role="owner",
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
            for row in (
                {
                    "id": str(owner_id),
                    "email": "owner@acme.test",
                    "name": "Owner",
                    "role": "OWNER",
                    "status": "ACTIVE",
                },
                {
                    "id": str(admin_id),
                    "email": "admin@acme.test",
                    "name": "Admin",
                    "role": "ADMIN",
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
                        "org_id": org_id,
                        "public_key": "pub",
                        "encrypted_private_key": "enc-priv",
                        "auth_verifier_hash": argon2_hasher.hash("Verifier123!"),
                    },
                )
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.delete(
                f"/api/v1/org/users/{owner_id}",
                headers={"Authorization": f"Bearer {owner_token}"},
            )
        assert response.status_code == 409
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
