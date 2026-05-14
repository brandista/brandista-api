"""Unit + endpoint tests for canonical auth v2 (Phase 4.1 step 2).

Layout:
  - Pure-logic tests (token encode/decode, model validation) need no DB
    or HTTP client.
  - DB-touching tests use the docker-compose Postgres at
    TEST_DATABASE_URL (see plan task 0).
  - Endpoint tests use httpx.AsyncClient against the FastAPI app.

Run all: pytest tests/unit/test_auth_v2.py -x -q
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError


# ---------- Task 1: model + exception ----------

def test_canonical_user_accepts_valid_input():
    from app.auth.canonical import CanonicalUser

    user = CanonicalUser(
        user_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        email="user@example.com",
        role="user",
    )
    assert user.email == "user@example.com"
    assert user.role == "user"


def test_canonical_user_rejects_malformed_email():
    from app.auth.canonical import CanonicalUser

    with pytest.raises(ValidationError):
        CanonicalUser(
            user_id=uuid.uuid4(),
            org_id=uuid.uuid4(),
            email="not-an-email",
            role="user",
        )


def test_canonical_token_error_is_an_exception():
    from app.auth.canonical import CanonicalTokenError

    err = CanonicalTokenError("token bad")
    assert isinstance(err, Exception)
    assert str(err) == "token bad"


# ---------- Task 2: create_canonical_token ----------

import jwt as pyjwt


def test_create_canonical_token_returns_string_with_canonical_claims():
    from app.auth.canonical import create_canonical_token
    from agents.config import SECRET_KEY, ALGORITHM

    user_id = uuid.uuid4()
    org_id = uuid.uuid4()

    token = create_canonical_token(
        user_id=user_id,
        org_id=org_id,
        email="user@example.com",
        role="user",
    )

    assert isinstance(token, str)
    decoded = pyjwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    assert decoded["sub"] == str(user_id)
    assert decoded["org_id"] == str(org_id)
    assert decoded["email"] == "user@example.com"
    assert decoded["role"] == "user"
    assert "jti" in decoded
    # jti must be a valid UUID string
    uuid.UUID(decoded["jti"])
    assert "iat" in decoded
    assert "exp" in decoded
    assert decoded["exp"] > decoded["iat"]


def test_create_canonical_token_each_call_has_unique_jti():
    from app.auth.canonical import create_canonical_token
    from agents.config import SECRET_KEY, ALGORITHM

    args = dict(
        user_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        email="user@example.com",
        role="user",
    )
    a = pyjwt.decode(create_canonical_token(**args), SECRET_KEY, algorithms=[ALGORITHM])
    b = pyjwt.decode(create_canonical_token(**args), SECRET_KEY, algorithms=[ALGORITHM])
    assert a["jti"] != b["jti"]
