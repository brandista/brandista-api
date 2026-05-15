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


def test_create_canonical_token_includes_product_claim():
    """Phase 4.2 prerequisite: every issued token carries a `product`
    string claim so the facts API can anti-spoof source_product writes."""
    from app.auth.canonical import create_canonical_token
    from agents.config import SECRET_KEY, ALGORITHM

    token = create_canonical_token(
        user_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        email="user@example.com",
        role="user",
        product="veyra",
    )
    decoded = pyjwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    assert decoded["product"] == "veyra"


def test_create_canonical_token_product_defaults_to_unknown():
    """Callers that don't pass product (e.g. legacy code paths during
    migration) must still get a usable token — product falls back to
    the sentinel that the facts API treats as read-only."""
    from app.auth.canonical import create_canonical_token, PRODUCT_UNKNOWN
    from agents.config import SECRET_KEY, ALGORITHM

    token = create_canonical_token(
        user_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        email="user@example.com",
        role="user",
    )
    decoded = pyjwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    assert decoded["product"] == PRODUCT_UNKNOWN


def test_normalize_product_accepts_allowlisted_values():
    from app.auth.canonical import normalize_product

    assert normalize_product("veyra") == "veyra"
    assert normalize_product("continuity") == "continuity"
    assert normalize_product("growth_engine") == "growth_engine"


def test_normalize_product_is_case_and_whitespace_insensitive():
    from app.auth.canonical import normalize_product

    assert normalize_product("VEYRA") == "veyra"
    assert normalize_product("  Veyra  ") == "veyra"


def test_normalize_product_unknown_values_collapse_to_unknown():
    from app.auth.canonical import normalize_product, PRODUCT_UNKNOWN

    assert normalize_product("") == PRODUCT_UNKNOWN
    assert normalize_product(None) == PRODUCT_UNKNOWN
    assert normalize_product("evil_product") == PRODUCT_UNKNOWN
    # Crucially, a client can't inject an arbitrary string — only the
    # frozenset members survive. Otherwise the facts-API anti-spoof
    # is bypassable.
    assert normalize_product("veyra; DROP TABLE users") == PRODUCT_UNKNOWN


def test_decode_canonical_token_reads_product_claim():
    from app.auth.canonical import create_canonical_token, decode_canonical_token

    token = create_canonical_token(
        user_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        email="x@y.com",
        role="user",
        product="continuity",
    )
    user = decode_canonical_token(token)
    assert user.product == "continuity"


def test_decode_canonical_token_backward_compat_no_product_claim():
    """A token minted before the product claim was added (or with an
    unrecognized value) must still decode successfully — the user just
    can't write to the facts API. This protects in-flight tokens
    during the retrofit."""
    from app.auth.canonical import decode_canonical_token, PRODUCT_UNKNOWN
    from agents.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES

    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(uuid.uuid4()),
        "email": "old@example.com",
        "org_id": str(uuid.uuid4()),
        "role": "user",
        "jti": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)).timestamp()),
        # NB: no `product` claim — pre-retrofit shape
    }
    token = pyjwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    user = decode_canonical_token(token)
    assert user.product == PRODUCT_UNKNOWN


def test_decode_canonical_token_rejects_unknown_product_silently():
    """If a token carries `product=evil` somehow (forgery against a
    compromised SECRET_KEY, or a future code path that bypassed
    normalize_product on issuance), we still decode but collapse to
    unknown — never trust the wire value verbatim for the in-memory
    CanonicalUser."""
    from app.auth.canonical import decode_canonical_token, PRODUCT_UNKNOWN
    from agents.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES

    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(uuid.uuid4()),
        "email": "evil@example.com",
        "org_id": str(uuid.uuid4()),
        "role": "user",
        "product": "evil_product_not_on_allowlist",
        "jti": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)).timestamp()),
    }
    token = pyjwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    user = decode_canonical_token(token)
    assert user.product == PRODUCT_UNKNOWN


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


# ---------- Task 4: provision_canonical_user ----------

import asyncio
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest_asyncio.fixture
async def db_engine():
    """Async engine pointed at the docker-compose test Postgres.

    Requires TEST_DATABASE_URL exported. Migration 0002 must already
    have run against this DB (see plan task 0).
    """
    raw = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql://brandista:dev@localhost:5433/brandista",
    )
    dsn = raw.replace("postgresql://", "postgresql+asyncpg://", 1) if "+asyncpg" not in raw else raw
    engine = create_async_engine(dsn, pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    """Fresh AsyncSession per test. Truncates canonical tables before
    each test so order does not matter. Uses TRUNCATE ... CASCADE so
    that FK constraints don't block cleanup."""
    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        # Wipe canonical-identity rows. Order doesn't matter due to CASCADE.
        await session.execute(text(
            "TRUNCATE TABLE entitlements, credits, users, organizations "
            "RESTART IDENTITY CASCADE"
        ))
        await session.commit()
        yield session


@pytest.mark.asyncio
async def test_provision_creates_full_set(db_session, monkeypatch):
    """A new email gets a user + org + credits row + growth_engine
    entitlement, all in a single transaction."""
    from app.auth import canonical
    from app.db.models import Credits, Entitlement, Organization, User
    from sqlalchemy import select

    # Make provision_canonical_user use the test session maker.
    monkeypatch.setattr(canonical, "_session_maker_for_provision",
                        lambda: _OneShotSessionMaker(db_session))

    user = await canonical.provision_canonical_user(
        email="new@example.com", source="google"
    )

    assert user.email == "new@example.com"
    assert user.org_id is not None
    assert user.is_active is True
    assert user.role == "user"

    # Org exists
    org = (await db_session.execute(
        select(Organization).where(Organization.id == user.org_id)
    )).scalar_one()
    assert org.name == "new@example.com"

    # Credits seeded with balance=0
    credits = (await db_session.execute(
        select(Credits).where(Credits.org_id == user.org_id)
    )).scalar_one()
    assert credits.balance == 0
    assert credits.plan_monthly_limit == 0

    # growth_engine entitlement seeded
    ent = (await db_session.execute(
        select(Entitlement).where(
            Entitlement.org_id == user.org_id,
            Entitlement.module == "growth_engine",
        )
    )).scalar_one()
    assert ent.is_active is True


class _OneShotSessionMaker:
    """Test helper: a 'session maker' that returns the same already-open
    session via async context manager. Lets provision_canonical_user
    reuse the test's session so TRUNCATE-on-fixture-entry works."""

    def __init__(self, session):
        self._session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc):
        # Don't close — the fixture owns the lifecycle.
        return False


@pytest.mark.asyncio
async def test_provision_idempotent_on_repeat(db_session, monkeypatch):
    """Calling provision_canonical_user twice for the same email returns
    the same user, does not create duplicates."""
    from app.auth import canonical
    from app.db.models import Organization, User
    from sqlalchemy import func, select

    monkeypatch.setattr(canonical, "_session_maker_for_provision",
                        lambda: _OneShotSessionMaker(db_session))

    a = await canonical.provision_canonical_user(email="dup@example.com", source="google")
    b = await canonical.provision_canonical_user(email="dup@example.com", source="google")
    assert a.id == b.id

    user_count = (await db_session.execute(
        select(func.count(User.id)).where(User.email == "dup@example.com")
    )).scalar_one()
    org_count = (await db_session.execute(
        select(func.count(Organization.id)).where(Organization.name == "dup@example.com")
    )).scalar_one()
    assert user_count == 1
    assert org_count == 1


@pytest.mark.asyncio
async def test_provision_leaves_hashed_password_null(db_session, monkeypatch):
    """After migration 0003, provisioned passwordless users have
    hashed_password = NULL, not the legacy '' sentinel."""
    from app.auth import canonical
    from app.db.models import User
    from sqlalchemy import select

    monkeypatch.setattr(canonical, "_session_maker_for_provision",
                        lambda: _OneShotSessionMaker(db_session))

    await canonical.provision_canonical_user(email="nullpwd@example.com", source="google")

    row = (await db_session.execute(
        select(User).where(User.email == "nullpwd@example.com")
    )).scalar_one()
    assert row.hashed_password is None

# ---------- Task 8: /google/native endpoint ----------


@pytest.mark.asyncio
async def test_google_native_creates_user_and_issues_token(db_session, monkeypatch):
    """Happy path: new email through Google native → user provisioned,
    v2 token returned, all expected claims present."""
    from app.auth import canonical
    from app.auth.canonical import decode_canonical_token

    monkeypatch.setattr(canonical, "_session_maker_for_provision",
                        lambda: _OneShotSessionMaker(db_session))

    # Stub google id_token verification
    def fake_verify(credential, request_, audience):
        return {
            "email": "google-new@example.com",
            "email_verified": True,
            "aud": "test-client-id",
            "sub": "google-sub-123",
            "name": "Test User",
        }

    monkeypatch.setattr(
        "google.oauth2.id_token.verify_oauth2_token", fake_verify
    )
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")

    app = _build_router_test_app()

    # httpx.AsyncClient + ASGITransport runs the handler in this test's
    # event loop, so the shared db_session (bound to the same loop) works
    # across the test ↔ handler boundary. TestClient would spawn a new
    # loop via anyio.from_thread.start_blocking_portal and asyncpg would
    # blow up with "Future attached to a different loop".
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        r = await client.post(
            "/api/auth/v2/google/native",
            json={"credential": "any-non-empty-string"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "bearer"

    user = decode_canonical_token(body["access_token"])
    assert user.email == "google-new@example.com"
    assert user.role == "user"
    # And the response carries the canonical user too
    assert body["user"]["email"] == "google-new@example.com"


def test_google_native_rejects_missing_credential():
    app = _build_router_test_app()
    client = TestClient(app)
    r = client.post("/api/auth/v2/google/native", json={"credential": ""})
    assert r.status_code == 400


def test_google_native_rejects_unverified_email(monkeypatch):
    def fake_verify(credential, request_, audience):
        return {"email": "noverify@example.com", "email_verified": False}

    monkeypatch.setattr(
        "google.oauth2.id_token.verify_oauth2_token", fake_verify
    )
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")

    app = _build_router_test_app()
    client = TestClient(app)
    r = client.post(
        "/api/auth/v2/google/native", json={"credential": "any-non-empty-string"}
    )
    assert r.status_code == 400


def test_google_native_rejects_invalid_google_token(monkeypatch):
    def fake_verify(credential, request_, audience):
        raise ValueError("bad signature")

    monkeypatch.setattr(
        "google.oauth2.id_token.verify_oauth2_token", fake_verify
    )
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")

    app = _build_router_test_app()
    client = TestClient(app)
    r = client.post(
        "/api/auth/v2/google/native", json={"credential": "any-non-empty-string"}
    )
    assert r.status_code == 401


def test_google_native_401_detail_does_not_leak_token_details(monkeypatch):
    """Spec §8: error messages never include token contents. Google's
    ValueError messages can include internal claim values (aud, iss).
    Our 401 detail must be a constant string."""
    def fake_verify(credential, request_, audience):
        raise ValueError("Wrong audience: aud=secret-internal-value")

    monkeypatch.setattr(
        "google.oauth2.id_token.verify_oauth2_token", fake_verify
    )
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")

    app = _build_router_test_app()
    client = TestClient(app)
    r = client.post(
        "/api/auth/v2/google/native", json={"credential": "any-non-empty-string"}
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid Google token"
    # Verify the leaked content is NOT in the response body
    assert "secret-internal-value" not in r.text


# ---------- Task 9: /magic-link/request endpoint ----------


class _FakeMagicLinkAuth:
    """Captures send_magic_link calls without actually emailing."""

    def __init__(self):
        self.calls: list[dict] = []

    async def send_magic_link(self, email, request, background_tasks, redirect_url=None):
        self.calls.append({"email": email, "redirect_url": redirect_url})
        return {"success": True, "message": "sent", "expires_in_minutes": 15}


def test_magic_link_request_calls_into_magic_link_auth(monkeypatch):
    import app.routers.auth_v2 as auth_v2_mod

    fake = _FakeMagicLinkAuth()
    monkeypatch.setattr(auth_v2_mod, "_get_magic_link_auth", lambda: fake)

    app = _build_router_test_app()
    client = TestClient(app)
    r = client.post(
        "/api/auth/v2/magic-link/request",
        json={"email": "Magic@Example.com"},
    )
    assert r.status_code == 200
    assert r.json() == {"status": "sent"}
    assert len(fake.calls) == 1
    # Email normalized to lowercase before being passed in
    assert fake.calls[0]["email"] == "magic@example.com"


def test_magic_link_request_returns_sent_even_if_magic_link_auth_unavailable(monkeypatch):
    """If the underlying magic-link subsystem is not configured (e.g. no
    Redis/SMTP), we still return 200 'sent' to the caller — the legacy
    endpoint behaves the same way to avoid leaking which emails exist."""
    import app.routers.auth_v2 as auth_v2_mod

    monkeypatch.setattr(auth_v2_mod, "_get_magic_link_auth", lambda: None)

    app = _build_router_test_app()
    client = TestClient(app)
    r = client.post(
        "/api/auth/v2/magic-link/request",
        json={"email": "anything@example.com"},
    )
    assert r.status_code == 200
    assert r.json() == {"status": "sent"}


def test_magic_link_request_reraises_httpexception(monkeypatch):
    """Rate-limit (and other HTTPException) from the legacy subsystem
    must propagate to the client — that's how 429s reach the frontend.
    The endpoint's anti-enumeration policy intentionally does NOT swallow
    HTTPException."""
    import app.routers.auth_v2 as auth_v2_mod

    class _RateLimitedMagicLinkAuth:
        async def send_magic_link(self, email, request, background_tasks, redirect_url=None):
            from fastapi import HTTPException
            raise HTTPException(status_code=429, detail="rate limited")

    monkeypatch.setattr(auth_v2_mod, "_get_magic_link_auth",
                        lambda: _RateLimitedMagicLinkAuth())

    app = _build_router_test_app()
    client = TestClient(app)
    r = client.post(
        "/api/auth/v2/magic-link/request",
        json={"email": "ratelimited@example.com"},
    )
    assert r.status_code == 429
    assert r.json() == {"detail": "rate limited"}


def test_magic_link_request_swallows_generic_exception(monkeypatch):
    """An unexpected error from the legacy subsystem must NOT leak to the
    caller as a 500 — that would reveal which emails trigger downstream
    failures. The endpoint logs and still returns 'sent' to preserve the
    anti-enumeration guarantee."""
    import app.routers.auth_v2 as auth_v2_mod

    class _BrokenMagicLinkAuth:
        async def send_magic_link(self, email, request, background_tasks, redirect_url=None):
            raise RuntimeError("redis is down")

    monkeypatch.setattr(auth_v2_mod, "_get_magic_link_auth",
                        lambda: _BrokenMagicLinkAuth())

    app = _build_router_test_app()
    client = TestClient(app)
    r = client.post(
        "/api/auth/v2/magic-link/request",
        json={"email": "broken@example.com"},
    )
    assert r.status_code == 200
    assert r.json() == {"status": "sent"}


# ---------- Task 10: /magic-link/verify endpoint ----------


class _FakeMagicLinkAuthVerify:
    """Stub for verify path. Returns a fixed result keyed on token."""

    def __init__(self, valid_tokens: dict[str, str]):
        # token → email
        self._valid = valid_tokens

    async def verify_magic_link(self, token, request):
        email = self._valid.get(token)
        if not email:
            from fastapi import HTTPException
            raise HTTPException(400, "Invalid or expired magic link")
        return {"valid": True, "success": True, "user": {"email": email}}


@pytest.mark.asyncio
async def test_magic_link_verify_issues_v2_token(db_session, monkeypatch):
    import app.routers.auth_v2 as auth_v2_mod
    from app.auth import canonical
    from app.auth.canonical import decode_canonical_token

    monkeypatch.setattr(canonical, "_session_maker_for_provision",
                        lambda: _OneShotSessionMaker(db_session))
    monkeypatch.setattr(
        auth_v2_mod, "_get_magic_link_auth",
        lambda: _FakeMagicLinkAuthVerify({"good-token": "magic-new@example.com"}),
    )

    # Use httpx.AsyncClient + ASGITransport to avoid event-loop conflict
    # with the async db_session fixture (same pattern as Task 8 happy path).
    import httpx
    from httpx import ASGITransport

    app = _build_router_test_app()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.post("/api/auth/v2/magic-link/verify", json={"token": "good-token"})

    assert r.status_code == 200, r.text
    body = r.json()
    user = decode_canonical_token(body["access_token"])
    assert user.email == "magic-new@example.com"
    assert user.role == "user"


def test_magic_link_verify_rejects_bad_token(monkeypatch):
    import app.routers.auth_v2 as auth_v2_mod

    monkeypatch.setattr(
        auth_v2_mod, "_get_magic_link_auth",
        lambda: _FakeMagicLinkAuthVerify({}),
    )

    app = _build_router_test_app()
    client = TestClient(app)
    r = client.post("/api/auth/v2/magic-link/verify", json={"token": "bad-token"})
    assert r.status_code == 400


def test_magic_link_verify_503_if_subsystem_unavailable(monkeypatch):
    import app.routers.auth_v2 as auth_v2_mod

    monkeypatch.setattr(auth_v2_mod, "_get_magic_link_auth", lambda: None)
    app = _build_router_test_app()
    client = TestClient(app)
    r = client.post("/api/auth/v2/magic-link/verify", json={"token": "x"})
    assert r.status_code == 503


# ---------- Task 11: production app mounts the router ----------


def test_main_app_mounts_v2_router():
    """Importing main.py registers the v2 router. We don't run any
    request — just assert at least one /api/auth/v2/* route exists on
    the actual FastAPI app object. Catches the case where someone
    forgets the include_router line."""
    import main  # imports the legacy entrypoint

    paths = {getattr(r, "path", "") for r in main.app.routes}
    v2_paths = {p for p in paths if p.startswith("/api/auth/v2")}
    assert v2_paths, f"no /api/auth/v2/* routes found on main.app; have: {sorted(paths)[:20]}"


def test_modular_app_mounts_v2_router():
    """Production runs app/main.py (per start.py + railway.json), not
    legacy main.py. The modular entrypoint re-registers most legacy
    routes onto its own FastAPI instance — and it also needs to mount
    the v2 router. Without this, v2 endpoints would only exist on the
    legacy app and would 405 in prod (the catch-all OPTIONS handler
    swallows unknown paths)."""
    import app.main as modular_main

    paths = {getattr(r, "path", "") for r in modular_main.app.routes}
    v2_paths = {p for p in paths if p.startswith("/api/auth/v2")}
    assert v2_paths, (
        f"no /api/auth/v2/* routes found on app.main:app; have: {sorted(paths)[:20]}"
    )


# ---------- Task 2A: /google/login + /google/callback endpoints ----------


def test_google_login_503_if_oauth_not_configured(monkeypatch):
    """If the authlib oauth object is None (e.g. env vars missing on boot),
    /login returns 503 rather than 500. Same anti-leak rationale as
    /magic-link/verify."""
    import app.routers.auth_v2 as auth_v2_mod
    monkeypatch.setattr(auth_v2_mod, "_get_oauth", lambda: None)
    app = _build_router_test_app()
    client = TestClient(app)
    r = client.get("/api/auth/v2/google/login", follow_redirects=False)
    assert r.status_code == 503


def test_google_login_503_if_client_id_missing(monkeypatch):
    """Even if oauth object exists, refuse to redirect when GOOGLE_CLIENT_ID
    is unset — protects against issuing a useless redirect."""
    import app.routers.auth_v2 as auth_v2_mod

    class _FakeOauth:
        google = object()  # truthy

    monkeypatch.setattr(auth_v2_mod, "_get_oauth", lambda: _FakeOauth())
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    app = _build_router_test_app()
    client = TestClient(app)
    r = client.get("/api/auth/v2/google/login", follow_redirects=False)
    assert r.status_code == 503


def test_google_callback_503_if_oauth_not_configured(monkeypatch):
    import app.routers.auth_v2 as auth_v2_mod
    monkeypatch.setattr(auth_v2_mod, "_get_oauth", lambda: None)
    app = _build_router_test_app()
    client = TestClient(app)
    r = client.get("/api/auth/v2/google/callback?code=x&state=y", follow_redirects=False)
    assert r.status_code == 503


@pytest.mark.asyncio
async def test_google_callback_happy_path_redirects_with_v2_token(db_session, monkeypatch):
    """Happy path: callback exchanges code, gets verified email, provisions
    canonical user, issues v2 token, redirects to frontend with token in
    URL hash fragment matching the legacy contract."""
    import app.routers.auth_v2 as auth_v2_mod
    from app.auth import canonical
    from app.auth.canonical import decode_canonical_token

    monkeypatch.setattr(canonical, "_session_maker_for_provision",
                        lambda: _OneShotSessionMaker(db_session))

    class _FakeGoogle:
        async def authorize_access_token(self, request):
            return {
                "userinfo": {
                    "email": "callback-new@example.com",
                    "email_verified": True,
                    "sub": "google-sub-xyz",
                    "name": "Test User",
                }
            }

    class _FakeOauth:
        google = _FakeGoogle()

    monkeypatch.setattr(auth_v2_mod, "_get_oauth", lambda: _FakeOauth())
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("FRONTEND_URL", "https://brandista.eu/growthengine")

    import httpx
    from httpx import ASGITransport
    app = _build_router_test_app()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.get(
            "/api/auth/v2/google/callback?code=x&state=y",
            follow_redirects=False,
        )

    assert r.status_code in (302, 307), r.text
    location = r.headers["location"]
    assert location.startswith("https://brandista.eu/growthengine/dashboard")
    # URL fragment shape must match legacy: #token=...&email=...&username=...&role=...
    assert "#token=" in location
    assert "&email=callback-new%40example.com" in location or "&email=callback-new@example.com" in location
    assert "&username=callback-new" in location
    assert "&role=user" in location

    # Pull the token out of the fragment and decode it
    fragment = location.split("#", 1)[1]
    token = dict(p.split("=", 1) for p in fragment.split("&"))["token"]
    user = decode_canonical_token(token)
    assert user.email == "callback-new@example.com"
    assert user.role == "user"


@pytest.mark.asyncio
async def test_google_callback_400_if_email_not_verified(db_session, monkeypatch):
    """An unverified Google email must not become a canonical user — same
    policy as /google/native."""
    import app.routers.auth_v2 as auth_v2_mod
    from app.auth import canonical

    monkeypatch.setattr(canonical, "_session_maker_for_provision",
                        lambda: _OneShotSessionMaker(db_session))

    class _FakeGoogle:
        async def authorize_access_token(self, request):
            return {"userinfo": {"email": "x@y.com", "email_verified": False}}

    class _FakeOauth:
        google = _FakeGoogle()

    monkeypatch.setattr(auth_v2_mod, "_get_oauth", lambda: _FakeOauth())
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")

    import httpx
    from httpx import ASGITransport
    app = _build_router_test_app()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.get(
            "/api/auth/v2/google/callback?code=x&state=y",
            follow_redirects=False,
        )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_google_callback_400_if_userinfo_missing(db_session, monkeypatch):
    """If authlib returns a token dict with no userinfo (drift between
    versions, or Google response oddity), refuse cleanly — same as if
    email_verified is False. No crash, no leak."""
    import app.routers.auth_v2 as auth_v2_mod
    from app.auth import canonical

    monkeypatch.setattr(canonical, "_session_maker_for_provision",
                        lambda: _OneShotSessionMaker(db_session))

    class _FakeGoogle:
        async def authorize_access_token(self, request):
            return {}  # no 'userinfo' key

    class _FakeOauth:
        google = _FakeGoogle()

    monkeypatch.setattr(auth_v2_mod, "_get_oauth", lambda: _FakeOauth())
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")

    import httpx
    from httpx import ASGITransport
    app = _build_router_test_app()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.get(
            "/api/auth/v2/google/callback?code=x&state=y",
            follow_redirects=False,
        )
    assert r.status_code == 400


def test_google_callback_502_on_transport_error(monkeypatch):
    """Network/transport errors from Google's token endpoint must surface
    as 5xx (so monitoring alerts fire), NOT as 400 which would look like
    a client problem."""
    import app.routers.auth_v2 as auth_v2_mod

    class _FakeGoogle:
        async def authorize_access_token(self, request):
            raise RuntimeError("connection reset by peer")

    class _FakeOauth:
        google = _FakeGoogle()

    monkeypatch.setattr(auth_v2_mod, "_get_oauth", lambda: _FakeOauth())
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")

    app = _build_router_test_app()
    client = TestClient(app)
    r = client.get(
        "/api/auth/v2/google/callback?code=x&state=y",
        follow_redirects=False,
    )
    assert r.status_code == 502
    assert r.json() == {"detail": "Google authorization failed"}
