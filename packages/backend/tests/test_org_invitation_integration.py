from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from typing import AsyncIterator
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.v1.org import get_invitation_email_sender
from app.db.session import get_db_session
from app.main import app
from app.security.password import argon2_hasher
from app.security.tokens import issue_access_token, issue_invitation_token


@dataclass
class CapturingInvitationEmailSender:
    sent: list[tuple[str, str]] = field(default_factory=list)

    async def send_invitation(self, *, recipient_email: str, invitation_link: str) -> None:
        self.sent.append((recipient_email, invitation_link))


def _extract_token(link: str) -> str:
    parsed = urlparse(link)
    values = parse_qs(parsed.query).get("token", [])
    assert values
    return values[0]


async def _setup_org_invite_tables(engine) -> None:
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
                    timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )


@pytest.mark.asyncio
async def test_invite_endpoint_creates_invited_user_with_token_hash_and_audit_log() -> None:
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
    await _setup_org_invite_tables(engine)

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    sender = CapturingInvitationEmailSender()
    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_invitation_email_sender] = lambda: sender

    org_id = str(uuid.uuid4())
    admin_id = uuid.uuid4()
    admin_email = "admin@example.com"
    admin_token, _ = issue_access_token(
        user_id=admin_id,
        org_id=uuid.UUID(org_id),
        email=admin_email,
        role="admin",
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
                {"id": org_id, "name": "Org", "subscription_tier": "enterprise", "settings": "{}"},
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
                    "id": str(admin_id),
                    "org_id": org_id,
                    "email": admin_email,
                    "name": "Admin",
                    "role": "ADMIN",
                    "status": "ACTIVE",
                    "public_key": "admin-public",
                    "encrypted_private_key": "admin-private",
                    "auth_verifier_hash": argon2_hasher.hash("AdminVerifier123!"),
                },
            )
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/org/users/invite",
                json={"email": "invitee@example.com", "role": "member"},
                headers={"Authorization": f"Bearer {admin_token}", "user-agent": "pytest"},
            )
        assert response.status_code == 201
        body = response.json()
        assert body["email"] == "invitee@example.com"
        assert body["status"] == "invited"
        assert body["role"] == "member"
        assert sender.sent

        invitation_token = _extract_token(sender.sent[0][1])
        expected_hash = hashlib.sha256(invitation_token.encode("utf-8")).hexdigest()
        async with session_factory() as session:
            row = (
                await session.execute(
                    text(
                        """
                        SELECT status, role, invitation_token_hash, invitation_expires_at
                        FROM users
                        WHERE email = :email
                        """
                    ),
                    {"email": "invitee@example.com"},
                )
            ).first()
            audit_row = (
                await session.execute(
                    text(
                        """
                        SELECT action
                        FROM audit_logs
                        ORDER BY timestamp DESC
                        LIMIT 1
                        """
                    )
                )
            ).first()

        assert row is not None
        assert str(row.status).lower() in {"invited", "userstatus.invited"}
        assert str(row.role).lower() in {"member", "userrole.member"}
        assert row.invitation_token_hash == expected_hash
        assert row.invitation_expires_at is not None
        assert audit_row is not None
        assert str(audit_row.action).lower() in {"invite_user", "auditlogaction.invite_user"}
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


@pytest.mark.asyncio
async def test_register_with_invitation_activates_user_and_reused_token_returns_410() -> None:
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
    await _setup_org_invite_tables(engine)

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    sender = CapturingInvitationEmailSender()
    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_invitation_email_sender] = lambda: sender

    org_id = str(uuid.uuid4())
    admin_id = uuid.uuid4()
    admin_email = "admin2@example.com"
    admin_token, _ = issue_access_token(
        user_id=admin_id,
        org_id=uuid.UUID(org_id),
        email=admin_email,
        role="admin",
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
                {"id": org_id, "name": "Org", "subscription_tier": "enterprise", "settings": "{}"},
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
                    "id": str(admin_id),
                    "org_id": org_id,
                    "email": admin_email,
                    "name": "Admin",
                    "role": "ADMIN",
                    "status": "ACTIVE",
                    "public_key": "admin-public",
                    "encrypted_private_key": "admin-private",
                    "auth_verifier_hash": argon2_hasher.hash("AdminVerifier123!"),
                },
            )
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            invite_response = await client.post(
                "/api/v1/org/users/invite",
                json={"email": "accept@example.com", "role": "member"},
                headers={"Authorization": f"Bearer {admin_token}", "user-agent": "pytest"},
            )
            assert invite_response.status_code == 201
            token = _extract_token(sender.sent[0][1])
            register_payload = {
                "email": "accept@example.com",
                "name": "Accepted User",
                "org_id": org_id,
                "auth_verifier": "AcceptedVerifier123!",
                "public_key": "accepted-public",
                "encrypted_private_key": "accepted-private",
                "invitation_token": token,
            }
            register_response = await client.post(
                "/api/v1/auth/register",
                json=register_payload,
                headers={"user-agent": "pytest"},
            )
            reused_response = await client.post(
                "/api/v1/auth/register",
                json=register_payload,
                headers={"user-agent": "pytest"},
            )

        assert register_response.status_code == 201
        assert reused_response.status_code == 410

        async with session_factory() as session:
            row = (
                await session.execute(
                    text(
                        """
                        SELECT status, invitation_token_hash, invitation_expires_at, auth_verifier_hash
                        FROM users
                        WHERE email = :email
                        """
                    ),
                    {"email": "accept@example.com"},
                )
            ).first()
            actions = (
                await session.execute(
                    text(
                        """
                        SELECT action
                        FROM audit_logs
                        WHERE target_id IN (SELECT id FROM users WHERE email = :email)
                        """
                    ),
                    {"email": "accept@example.com"},
                )
            ).scalars().all()

        assert row is not None
        assert str(row.status).lower() in {"active", "userstatus.active"}
        assert row.invitation_token_hash is None
        assert row.invitation_expires_at is None
        assert argon2_hasher.verify(row.auth_verifier_hash, "AcceptedVerifier123!")
        normalized_actions = {str(action).lower() for action in actions}
        assert "invite_user" in normalized_actions or "auditlogaction.invite_user" in normalized_actions
        assert "accept_invite" in normalized_actions or "auditlogaction.accept_invite" in normalized_actions
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


@pytest.mark.asyncio
async def test_register_with_expired_invitation_token_returns_410() -> None:
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
    await _setup_org_invite_tables(engine)

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    org_id = uuid.uuid4()
    invited_user_id = uuid.uuid4()
    invitation_token, invitation_expiry = issue_invitation_token(
        user_id=invited_user_id,
        org_id=org_id,
        email="expired@example.com",
        role="member",
        expires_in=timedelta(seconds=-1),
    )
    invitation_hash = hashlib.sha256(invitation_token.encode("utf-8")).hexdigest()

    try:
        async with session_factory() as session:
            await session.execute(
                text(
                    """
                    INSERT INTO organizations (id, name, subscription_tier, settings)
                    VALUES (:id, :name, :subscription_tier, :settings)
                    """
                ),
                {"id": str(org_id), "name": "Org", "subscription_tier": "enterprise", "settings": "{}"},
            )
            await session.execute(
                text(
                    """
                    INSERT INTO users (
                        id, org_id, email, name, role, status, public_key, encrypted_private_key, auth_verifier_hash,
                        invitation_token_hash, invitation_expires_at
                    ) VALUES (
                        :id, :org_id, :email, :name, :role, :status, :public_key, :encrypted_private_key, :auth_verifier_hash,
                        :invitation_token_hash, :invitation_expires_at
                    )
                    """
                ),
                {
                    "id": str(invited_user_id),
                    "org_id": str(org_id),
                    "email": "expired@example.com",
                    "name": "Expired Invite",
                    "role": "MEMBER",
                    "status": "INVITED",
                    "public_key": "",
                    "encrypted_private_key": "",
                    "auth_verifier_hash": argon2_hasher.hash("ExpiredVerifier123!"),
                    "invitation_token_hash": invitation_hash,
                    "invitation_expires_at": invitation_expiry.isoformat(),
                },
            )
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "expired@example.com",
                    "name": "Expired",
                    "org_id": str(org_id),
                    "auth_verifier": "ExpiredVerifier123!",
                    "public_key": "expired-public",
                    "encrypted_private_key": "expired-private",
                    "invitation_token": invitation_token,
                },
            )
        assert response.status_code == 410
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
