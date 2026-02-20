from __future__ import annotations

import datetime
import uuid

import pytest

from app.security.tokens import AccessTokenValidationError, issue_access_token, validate_access_token


def test_issue_and_validate_access_token_round_trip() -> None:
    now = datetime.datetime.now(datetime.UTC).replace(microsecond=0)
    user_id = uuid.uuid4()
    org_id = uuid.uuid4()

    token, expiry = issue_access_token(
        user_id=user_id,
        org_id=org_id,
        email="unit@example.com",
        role="member",
        now=now,
    )
    payload = validate_access_token(token)

    assert payload.sub == user_id
    assert payload.org_id == org_id
    assert payload.email == "unit@example.com"
    assert payload.role == "member"
    assert payload.iss == "vaultguard"
    assert payload.iat == now
    assert payload.exp == expiry.replace(microsecond=0)


def test_validate_access_token_rejects_expired_token() -> None:
    token, _ = issue_access_token(
        user_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        email="expired@example.com",
        role="member",
        now=datetime.datetime.now(datetime.UTC),
        expires_in=datetime.timedelta(seconds=-1),
    )

    with pytest.raises(AccessTokenValidationError):
        validate_access_token(token)
