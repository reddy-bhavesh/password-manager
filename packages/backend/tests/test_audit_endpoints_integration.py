from __future__ import annotations

import datetime
import json
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


async def _setup_audit_tables(engine) -> None:
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


@pytest.mark.asyncio
async def test_audit_logs_query_filters_and_export_formats() -> None:
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
    await _setup_audit_tables(engine)

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    org_id = uuid.uuid4()
    other_org_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    actor_a = uuid.uuid4()
    actor_b = uuid.uuid4()
    owner_token, _ = issue_access_token(
        user_id=admin_id,
        org_id=org_id,
        email="admin@acme.test",
        role="admin",
    )
    base_time = datetime.datetime(2026, 2, 23, 12, 0, 0, tzinfo=datetime.UTC)

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
            for row in (
                {
                    "id": str(admin_id),
                    "org_id": str(org_id),
                    "email": "admin@acme.test",
                    "role": "ADMIN",
                },
                {
                    "id": str(actor_a),
                    "org_id": str(org_id),
                    "email": "actor-a@acme.test",
                    "role": "MEMBER",
                },
                {
                    "id": str(actor_b),
                    "org_id": str(org_id),
                    "email": "actor-b@acme.test",
                    "role": "MANAGER",
                },
            ):
                await session.execute(
                    text(
                        """
                        INSERT INTO users (
                            id, org_id, email, name, role, status, public_key, encrypted_private_key, auth_verifier_hash
                        ) VALUES (
                            :id, :org_id, :email, :name, :role, 'ACTIVE', 'pk', 'enc', :auth_verifier_hash
                        )
                        """
                    ),
                    {
                        **row,
                        "name": row["email"].split("@", 1)[0],
                        "auth_verifier_hash": argon2_hasher.hash("Verifier123!"),
                    },
                )

            audit_rows = [
                {
                    "id": str(uuid.uuid4()),
                    "org_id": str(org_id),
                    "actor_id": str(actor_a),
                    "action": "LOGIN",
                    "target_id": str(uuid.uuid4()),
                    "ip_address": "10.0.0.1",
                    "user_agent": "pytest-a",
                    "geo_location": "unknown",
                    "timestamp": (base_time - datetime.timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S"),
                },
                {
                    "id": str(uuid.uuid4()),
                    "org_id": str(org_id),
                    "actor_id": str(actor_a),
                    "action": "VIEW_ITEM",
                    "target_id": str(uuid.uuid4()),
                    "ip_address": "10.0.0.2",
                    "user_agent": "pytest-a",
                    "geo_location": "unknown",
                    "timestamp": (base_time - datetime.timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),
                },
                {
                    "id": str(uuid.uuid4()),
                    "org_id": str(org_id),
                    "actor_id": str(actor_b),
                    "action": "EDIT_ITEM",
                    "target_id": str(uuid.uuid4()),
                    "ip_address": "10.0.0.3",
                    "user_agent": "pytest-b",
                    "geo_location": "unknown",
                    "timestamp": base_time.strftime("%Y-%m-%d %H:%M:%S"),
                },
                {
                    "id": str(uuid.uuid4()),
                    "org_id": str(other_org_id),
                    "actor_id": str(uuid.uuid4()),
                    "action": "DELETE_ITEM",
                    "target_id": str(uuid.uuid4()),
                    "ip_address": "10.0.0.4",
                    "user_agent": "other",
                    "geo_location": "unknown",
                    "timestamp": base_time.strftime("%Y-%m-%d %H:%M:%S"),
                },
            ]
            for row in audit_rows:
                await session.execute(
                    text(
                        """
                        INSERT INTO audit_logs (
                            id, org_id, actor_id, action, target_id, ip_address, user_agent, geo_location, timestamp
                        ) VALUES (
                            :id, :org_id, :actor_id, :action, :target_id, :ip_address, :user_agent, :geo_location, :timestamp
                        )
                        """
                    ),
                    row,
                )
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/audit/logs",
                params={"page": 1, "per_page": 2},
                headers={"Authorization": f"Bearer {owner_token}"},
            )
            assert response.status_code == 200
            body = response.json()
            assert body["total"] == 3
            assert body["page"] == 1
            assert body["per_page"] == 2
            assert len(body["items"]) == 2
            assert [item["action"] for item in body["items"]] == ["edit_item", "view_item"]

            actor_filtered = await client.get(
                "/api/v1/audit/logs",
                params={"actor_id": str(actor_a), "page": 1, "per_page": 10},
                headers={"Authorization": f"Bearer {owner_token}"},
            )
            assert actor_filtered.status_code == 200
            actor_items = actor_filtered.json()["items"]
            assert len(actor_items) == 2
            assert {_normalize_uuid(item["actor_id"]) for item in actor_items} == {_normalize_uuid(actor_a)}

            action_filtered = await client.get(
                "/api/v1/audit/logs",
                params={"action": "view_item", "page": 1, "per_page": 10},
                headers={"Authorization": f"Bearer {owner_token}"},
            )
            assert action_filtered.status_code == 200
            assert [item["action"] for item in action_filtered.json()["items"]] == ["view_item"]

            start_date = (base_time - datetime.timedelta(hours=12)).isoformat()
            end_date = (base_time + datetime.timedelta(hours=1)).isoformat()
            date_filtered = await client.get(
                "/api/v1/audit/logs",
                params={"start_date": start_date, "end_date": end_date, "page": 1, "per_page": 10},
                headers={"Authorization": f"Bearer {owner_token}"},
            )
            assert date_filtered.status_code == 200
            date_items = date_filtered.json()["items"]
            assert len(date_items) == 1
            assert date_items[0]["action"] == "edit_item"

            combo_filtered = await client.get(
                "/api/v1/audit/logs",
                params={
                    "actor_id": str(actor_a),
                    "action": "view_item",
                    "start_date": (base_time - datetime.timedelta(days=1, minutes=1)).isoformat(),
                    "end_date": (base_time - datetime.timedelta(days=1) + datetime.timedelta(minutes=1)).isoformat(),
                    "page": 1,
                    "per_page": 10,
                },
                headers={"Authorization": f"Bearer {owner_token}"},
            )
            assert combo_filtered.status_code == 200
            combo_items = combo_filtered.json()["items"]
            assert len(combo_items) == 1
            assert combo_items[0]["action"] == "view_item"
            assert _normalize_uuid(combo_items[0]["actor_id"]) == _normalize_uuid(actor_a)

            csv_export = await client.get(
                "/api/v1/audit/logs/export",
                params={"format": "csv", "action": "view_item"},
                headers={"Authorization": f"Bearer {owner_token}"},
            )
            assert csv_export.status_code == 200
            assert csv_export.headers["content-disposition"] == 'attachment; filename="audit-logs.csv"'
            csv_text = csv_export.text
            assert csv_text.splitlines()[0].startswith("id,org_id,actor_id,action")
            assert "view_item" in csv_text
            assert "edit_item" not in csv_text

            json_export = await client.get(
                "/api/v1/audit/logs/export",
                params={"format": "json", "actor_id": str(actor_a)},
                headers={"Authorization": f"Bearer {owner_token}"},
            )
            assert json_export.status_code == 200
            assert json_export.headers["content-disposition"] == 'attachment; filename="audit-logs.ndjson"'
            lines = [line for line in json_export.text.splitlines() if line.strip()]
            assert len(lines) == 2
            parsed = [json.loads(line) for line in lines]
            assert all(row["action"] in {"login", "view_item"} for row in parsed)
            assert {_normalize_uuid(row["actor_id"]) for row in parsed} == {_normalize_uuid(actor_a)}

            invalid_range = await client.get(
                "/api/v1/audit/logs",
                params={
                    "start_date": base_time.isoformat(),
                    "end_date": (base_time - datetime.timedelta(days=1)).isoformat(),
                },
                headers={"Authorization": f"Bearer {owner_token}"},
            )
            assert invalid_range.status_code == 400
            assert invalid_range.headers["content-type"].startswith("application/problem+json")
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


@pytest.mark.asyncio
async def test_audit_logs_non_admin_forbidden() -> None:
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
    await _setup_audit_tables(engine)

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
            list_response = await client.get(
                "/api/v1/audit/logs",
                headers={"Authorization": f"Bearer {member_token}"},
            )
            export_response = await client.get(
                "/api/v1/audit/logs/export",
                params={"format": "csv"},
                headers={"Authorization": f"Bearer {member_token}"},
            )
        assert list_response.status_code == 403
        assert export_response.status_code == 403
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
