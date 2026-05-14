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


# ---------- Task 3: decode_canonical_token ----------


def _make_legacy_token(sub: str = "user@example.com", role: str = "user") -> str:
    """Build a legacy-shaped token (sub=email, no org_id, no jti) for
    rejection tests. Matches main.py:create_access_token format."""
    from agents.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES

    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)).timestamp()),
    }
    return pyjwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def test_decode_canonical_token_roundtrip():
    from app.auth.canonical import create_canonical_token, decode_canonical_token

    user_id = uuid.uuid4()
    org_id = uuid.uuid4()
    token = create_canonical_token(
        user_id=user_id, org_id=org_id, email="x@y.com", role="admin"
    )

    user = decode_canonical_token(token)
    assert user.user_id == user_id
    assert user.org_id == org_id
    assert user.email == "x@y.com"
    assert user.role == "admin"


def test_decode_rejects_legacy_token():
    from app.auth.canonical import decode_canonical_token, CanonicalTokenError

    legacy = _make_legacy_token()
    with pytest.raises(CanonicalTokenError):
        decode_canonical_token(legacy)


def test_decode_rejects_non_uuid_sub():
    from app.auth.canonical import decode_canonical_token, CanonicalTokenError
    from agents.config import SECRET_KEY, ALGORITHM

    now = datetime.now(timezone.utc)
    bad = pyjwt.encode(
        {
            "sub": "not-a-uuid",
            "email": "x@y.com",
            "org_id": str(uuid.uuid4()),
            "role": "user",
            "jti": str(uuid.uuid4()),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=1)).timestamp()),
        },
        SECRET_KEY,
        algorithm=ALGORITHM,
    )
    with pytest.raises(CanonicalTokenError):
        decode_canonical_token(bad)


def test_decode_rejects_non_uuid_org_id():
    from app.auth.canonical import decode_canonical_token, CanonicalTokenError
    from agents.config import SECRET_KEY, ALGORITHM

    now = datetime.now(timezone.utc)
    bad = pyjwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "email": "x@y.com",
            "org_id": "not-a-uuid",
            "role": "user",
            "jti": str(uuid.uuid4()),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=1)).timestamp()),
        },
        SECRET_KEY,
        algorithm=ALGORITHM,
    )
    with pytest.raises(CanonicalTokenError):
        decode_canonical_token(bad)


def test_decode_rejects_missing_email():
    from app.auth.canonical import decode_canonical_token, CanonicalTokenError
    from agents.config import SECRET_KEY, ALGORITHM

    now = datetime.now(timezone.utc)
    bad = pyjwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "org_id": str(uuid.uuid4()),
            "role": "user",
            "jti": str(uuid.uuid4()),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=1)).timestamp()),
        },
        SECRET_KEY,
        algorithm=ALGORITHM,
    )
    with pytest.raises(CanonicalTokenError):
        decode_canonical_token(bad)


def test_decode_rejects_expired_token():
    from app.auth.canonical import decode_canonical_token, CanonicalTokenError
    from agents.config import SECRET_KEY, ALGORITHM

    now = datetime.now(timezone.utc)
    expired = pyjwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "email": "x@y.com",
            "org_id": str(uuid.uuid4()),
            "role": "user",
            "jti": str(uuid.uuid4()),
            "iat": int((now - timedelta(hours=2)).timestamp()),
            "exp": int((now - timedelta(hours=1)).timestamp()),
        },
        SECRET_KEY,
        algorithm=ALGORITHM,
    )
    with pytest.raises(CanonicalTokenError):
        decode_canonical_token(expired)


def test_decode_rejects_bad_signature():
    from app.auth.canonical import (
        create_canonical_token,
        decode_canonical_token,
        CanonicalTokenError,
    )

    token = create_canonical_token(
        user_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        email="x@y.com",
        role="user",
    )
    # Tamper with the last segment (signature)
    parts = token.split(".")
    tampered = ".".join([parts[0], parts[1], "AAAA" + parts[2][4:]])
    with pytest.raises(CanonicalTokenError):
        decode_canonical_token(tampered)


def test_decode_invalid_token_message_does_not_leak_token():
    """Spec §8: error messages never include token contents. PyJWT's
    InvalidTokenError messages are content-free today, but we don't
    depend on that — our wrapper uses a constant string."""
    from app.auth.canonical import decode_canonical_token, CanonicalTokenError

    # A garbage 'JWT' that fails JWT format parsing.
    with pytest.raises(CanonicalTokenError) as excinfo:
        decode_canonical_token("not.a.real.jwt")
    assert str(excinfo.value) == "invalid token"


# ---------- Task 5: get_current_canonical_user dependency ----------

from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient


def _build_dep_test_app():
    """Minimal FastAPI app that exposes one route guarded by
    get_current_canonical_user. Used to test the dependency end-to-end
    via the test client."""
    from app.auth.dependencies import get_current_canonical_user
    from app.auth.canonical import CanonicalUser

    app = FastAPI()

    @app.get("/__probe")
    async def probe(user: CanonicalUser = Depends(get_current_canonical_user)):
        return {"email": user.email}

    return app


def test_dependency_accepts_valid_v2_token():
    from app.auth.canonical import create_canonical_token

    app = _build_dep_test_app()
    client = TestClient(app)

    token = create_canonical_token(
        user_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        email="ok@example.com",
        role="user",
    )
    r = client.get("/__probe", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json() == {"email": "ok@example.com"}


def test_dependency_rejects_legacy_token_with_401():
    app = _build_dep_test_app()
    client = TestClient(app)

    legacy = _make_legacy_token()
    r = client.get("/__probe", headers={"Authorization": f"Bearer {legacy}"})
    assert r.status_code == 401


def test_dependency_rejects_missing_header_with_401_or_403():
    app = _build_dep_test_app()
    client = TestClient(app)

    r = client.get("/__probe")
    # HTTPBearer returns 403 by default for missing creds; either is acceptable.
    assert r.status_code in (401, 403)


def test_dependency_rejects_malformed_bearer_with_401():
    app = _build_dep_test_app()
    client = TestClient(app)

    r = client.get("/__probe", headers={"Authorization": "Bearer not-a-token"})
    assert r.status_code == 401


# ---------- Task 6: /me endpoint ----------


def _build_router_test_app():
    """Minimal FastAPI app that mounts the v2 router. Used to test
    endpoints in isolation without booting main.py."""
    from app.routers.auth_v2 import router as auth_v2_router

    app = FastAPI()
    app.include_router(auth_v2_router, prefix="/api/auth/v2", tags=["auth-v2"])
    return app


def test_me_returns_canonical_user():
    from app.auth.canonical import create_canonical_token

    app = _build_router_test_app()
    client = TestClient(app)

    user_id = uuid.uuid4()
    org_id = uuid.uuid4()
    token = create_canonical_token(
        user_id=user_id, org_id=org_id, email="me@example.com", role="user"
    )

    r = client.get("/api/auth/v2/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == str(user_id)
    assert body["org_id"] == str(org_id)
    assert body["email"] == "me@example.com"
    assert body["role"] == "user"


def test_me_rejects_unauthenticated_request():
    app = _build_router_test_app()
    client = TestClient(app)
    r = client.get("/api/auth/v2/me")
    assert r.status_code in (401, 403)


# ---------- Task 7: /logout endpoint ----------


def test_logout_returns_204_with_no_auth_header():
    app = _build_router_test_app()
    client = TestClient(app)
    r = client.post("/api/auth/v2/logout")
    assert r.status_code == 204
    assert r.content == b""


def test_logout_returns_204_with_valid_token():
    from app.auth.canonical import create_canonical_token

    app = _build_router_test_app()
    client = TestClient(app)
    token = create_canonical_token(
        user_id=uuid.uuid4(), org_id=uuid.uuid4(), email="x@y.com", role="user"
    )
    r = client.post("/api/auth/v2/logout", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 204


def test_logout_returns_204_with_garbage_token():
    """Logout is a no-op — it doesn't validate the token. Frontend
    just wants to call 'logout' as a fire-and-forget signal."""
    app = _build_router_test_app()
    client = TestClient(app)
    r = client.post("/api/auth/v2/logout", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 204
