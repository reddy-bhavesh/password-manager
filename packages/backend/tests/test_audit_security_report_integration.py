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


async def _setup_audit_security_report_tables(engine) -> None:
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
                CREATE TABLE audit_logs (
                    id TEXT PRIMARY KEY,
                    org_id TEXT NOT NULL,
                    actor_id TEXT NULL,
                    action TEXT NOT NULL,
                    target_id TEXT NULL,
                    ip_address TEXT NOT NULL,
                    user_agent TEXT NOT NULL,
                    geo_location TEXT NOT NULL,
                    timestamp TEXT NOT NULL
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
async def test_security_health_report_returns_metrics_and_score_from_seeded_data() -> None:
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
    await _setup_audit_security_report_tables(engine)

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    org_id = uuid.uuid4()
    other_org_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    member_id = uuid.uuid4()
    now = datetime.datetime.now(datetime.UTC)
    owner_token, _ = issue_access_token(
        user_id=owner_id,
        org_id=org_id,
        email="owner@acme.test",
        role="owner",
    )

    try:
        async with session_factory() as session:
            await session.execute(
                text(
                    """
                    INSERT INTO organizations (id, name, subscription_tier, settings)
                    VALUES (:org1, 'Acme', 'enterprise', '{}'),
                           (:org2, 'Other', 'enterprise', '{}')
                    """
                ),
                {"org1": str(org_id), "org2": str(other_org_id)},
            )

            users = [
                # Active users (4 total), two have MFA enabled -> 50%
                ("owner@acme.test", "OWNER", "ACTIVE", 1, owner_id),
                ("admin@acme.test", "ADMIN", "ACTIVE", 1, uuid.uuid4()),
                ("member1@acme.test", "MEMBER", "ACTIVE", 0, uuid.uuid4()),
                ("member2@acme.test", "MEMBER", "ACTIVE", 0, uuid.uuid4()),
                # Suspended account (count=1)
                ("suspended@acme.test", "MEMBER", "SUSPENDED", 0, uuid.uuid4()),
                # Invited user should not affect active MFA denominator
                ("invited@acme.test", "MEMBER", "INVITED", 0, uuid.uuid4()),
                # Other org noise
                ("other@other.test", "ADMIN", "ACTIVE", 1, uuid.uuid4()),
            ]
            for email, role, status, mfa_enabled, user_id in users:
                await session.execute(
                    text(
                        """
                        INSERT INTO users (
                            id, org_id, email, name, role, status, public_key, encrypted_private_key,
                            auth_verifier_hash, mfa_enabled
                        ) VALUES (
                            :id, :org_id, :email, :name, :role, :status, 'pk', 'enc', :auth_verifier_hash, :mfa_enabled
                        )
                        """
                    ),
                    {
                        "id": str(user_id),
                        "org_id": str(other_org_id if email == "other@other.test" else org_id),
                        "email": email,
                        "name": email.split("@", 1)[0],
                        "role": role,
                        "status": status,
                        "auth_verifier_hash": argon2_hasher.hash("Verifier123!"),
                        "mfa_enabled": mfa_enabled,
                    },
                )

            recent_failed_1 = now - datetime.timedelta(days=5)
            recent_failed_2 = now - datetime.timedelta(days=15)
            old_failed = now - datetime.timedelta(days=45)
            for row in (
                (org_id, owner_id, "FAILED_LOGIN", recent_failed_1),
                (org_id, owner_id, "FAILED_LOGIN", recent_failed_2),
                (org_id, owner_id, "FAILED_LOGIN", old_failed),
                (other_org_id, uuid.uuid4(), "FAILED_LOGIN", recent_failed_1),
                (org_id, owner_id, "LOGIN", recent_failed_1),
            ):
                await session.execute(
                    text(
                        """
                        INSERT INTO audit_logs (
                            id, org_id, actor_id, action, target_id, ip_address, user_agent, geo_location, timestamp
                        ) VALUES (
                            :id, :org_id, :actor_id, :action, NULL, '127.0.0.1', 'pytest', 'unknown', :timestamp
                        )
                        """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "org_id": str(row[0]),
                        "actor_id": str(row[1]),
                        "action": row[2],
                        "timestamp": row[3].strftime("%Y-%m-%d %H:%M:%S"),
                    },
                )

            item_over_shared = uuid.uuid4()
            item_not_over_shared = uuid.uuid4()
            collection_over_shared = uuid.uuid4()
            collection_normal = uuid.uuid4()

            await session.execute(
                text(
                    """
                    INSERT INTO vault_items (id, owner_id, org_id, type, encrypted_data, encrypted_key, name)
                    VALUES
                    (:item1, :owner_id, :org_id, 'LOGIN', 'cipher1', 'key1', 'Shared Widely'),
                    (:item2, :owner_id, :org_id, 'LOGIN', 'cipher2', 'key2', 'Shared Narrowly')
                    """
                ),
                {
                    "item1": str(item_over_shared),
                    "item2": str(item_not_over_shared),
                    "owner_id": str(owner_id),
                    "org_id": str(org_id),
                },
            )
            await session.execute(
                text(
                    """
                    INSERT INTO collections (id, org_id, name, created_by)
                    VALUES
                    (:c1, :org_id, 'All Hands', :owner_id),
                    (:c2, :org_id, 'Small Team', :owner_id)
                    """
                ),
                {
                    "c1": str(collection_over_shared),
                    "c2": str(collection_normal),
                    "org_id": str(org_id),
                    "owner_id": str(owner_id),
                },
            )
            await session.execute(
                text(
                    """
                    INSERT INTO collection_items (collection_id, item_id)
                    VALUES
                    (:c1, :item1),
                    (:c2, :item2)
                    """
                ),
                {
                    "c1": str(collection_over_shared),
                    "c2": str(collection_normal),
                    "item1": str(item_over_shared),
                    "item2": str(item_not_over_shared),
                },
            )
            for idx in range(6):
                await session.execute(
                    text(
                        """
                        INSERT INTO collection_members (collection_id, user_or_group_id, permission)
                        VALUES (:collection_id, :subject_id, 'VIEW')
                        """
                    ),
                    {
                        "collection_id": str(collection_over_shared),
                        "subject_id": str(uuid.uuid4()),
                    },
                )
            for idx in range(5):
                await session.execute(
                    text(
                        """
                        INSERT INTO collection_members (collection_id, user_or_group_id, permission)
                        VALUES (:collection_id, :subject_id, 'VIEW')
                        """
                    ),
                    {
                        "collection_id": str(collection_normal),
                        "subject_id": str(uuid.uuid4()),
                    },
                )
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/audit/reports/security",
                headers={"Authorization": f"Bearer {owner_token}"},
            )

        assert response.status_code == 200
        assert response.json() == {
            "overall_score": 61,
            "failed_logins_30d": 2,
            "mfa_adoption_pct": 50,
            "suspended_accounts": 1,
            "over_shared_items": 1,
        }
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


@pytest.mark.asyncio
async def test_security_health_report_non_admin_forbidden() -> None:
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
    await _setup_audit_security_report_tables(engine)

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    org_id = uuid.uuid4()
    member_id = uuid.uuid4()
    member_token, _ = issue_access_token(
        user_id=member_id,
        org_id=org_id,
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
                {"id": str(org_id)},
            )
            await session.execute(
                text(
                    """
                    INSERT INTO users (
                        id, org_id, email, name, role, status, public_key, encrypted_private_key, auth_verifier_hash
                    ) VALUES (
                        :id, :org_id, :email, :name, 'MEMBER', 'ACTIVE', 'pk', 'enc', :auth_verifier_hash
                    )
                    """
                ),
                {
                    "id": str(member_id),
                    "org_id": str(org_id),
                    "email": "member@acme.test",
                    "name": "Member",
                    "auth_verifier_hash": argon2_hasher.hash("Verifier123!"),
                },
            )
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/audit/reports/security",
                headers={"Authorization": f"Bearer {member_token}"},
            )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
