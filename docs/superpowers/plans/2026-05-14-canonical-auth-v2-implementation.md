# Canonical Auth v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship five `/api/auth/v2/*` endpoints that issue and validate canonical platform JWTs (`{sub=uuid, email, org_id, role, jti, exp, iat}`) alongside the existing legacy `/auth/*` flow, with auto-provisioning of new users into the canonical `users`/`organizations`/`credits`/`entitlements` tables.

**Architecture:** New `app/auth/` package holds token primitives (encode, decode, validate) and the DB-side `provision_canonical_user` helper. A new `app/routers/auth_v2.py` mounts under `/api/auth/v2` and is wired into `main.py` (the production FastAPI app). Legacy `main.py:get_current_user`, `app/dependencies.py:get_current_user`, and all `/auth/*` endpoints are untouched. Continuity's `BrandistaCoreIdentityProvider` already accepts the new shape, so no consumer-side change is needed.

**Tech Stack:** FastAPI, SQLAlchemy 2 async (via `app/db/session.py`), `pyjwt` (already imported as `jwt`), `pydantic` v2 (`EmailStr`), `httpx.AsyncClient` for tests, docker-compose Postgres on `localhost:5433` for DB-touching tests, `pytest-asyncio` (already enabled in `pytest.ini` per `asyncio_mode=auto`).

**Spec:** `docs/superpowers/specs/2026-05-14-canonical-auth-v2-design.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `app/auth/__init__.py` | Create | Empty package marker |
| `app/auth/canonical.py` | Create | `CanonicalUser` Pydantic model, `CanonicalTokenError`, `create_canonical_token`, `decode_canonical_token`, `provision_canonical_user` |
| `app/auth/dependencies.py` | Create | `get_current_canonical_user` FastAPI dependency |
| `app/routers/auth_v2.py` | Create | Five v2 endpoints |
| `main.py` | Modify (one-line insert near other `include_router` calls) | Mount the v2 router |
| `tests/unit/test_auth_v2.py` | Create | All v2 unit + endpoint tests, plus local fixtures |
| `CHANGELOG.md` | Modify | Entry under `[unreleased]` |

Each new file has one clear responsibility. `canonical.py` is the heaviest (~150 LOC) but stays focused: it owns the token contract end-to-end. Endpoints in `auth_v2.py` are thin wrappers that call `canonical.py` helpers — the router file should not grow past ~200 LOC.

---

## Task 0: Pre-flight — confirm test DB is reachable

**Files:** none

- [ ] **Step 1: Bring up the local Postgres if not already running**

```bash
cd infra && docker compose up -d postgres
docker compose ps
```

Expected: `postgres` container in state `Up`. Port 5433 mapped to 5432.

- [ ] **Step 2: Confirm canonical schema is migrated**

```bash
DATABASE_URL="postgresql://brandista:dev@localhost:5433/brandista" \
  alembic current
```

Expected: `0002_canonical_id (head)`. If empty, run `alembic upgrade head` against the same DATABASE_URL.

- [ ] **Step 3: Set the test env var for the rest of this plan**

```bash
export TEST_DATABASE_URL="postgresql://brandista:dev@localhost:5433/brandista"
```

Every task's pytest invocation in this plan assumes this is exported. If you start a new shell, re-export.

No commit — this is environment setup.

---

## Task 1: Auth package + `CanonicalUser` model + `CanonicalTokenError`

**Files:**
- Create: `app/auth/__init__.py`
- Create: `app/auth/canonical.py`
- Create: `tests/unit/test_auth_v2.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/test_auth_v2.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/unit/test_auth_v2.py -x -q
```

Expected: 3 tests, all errored with `ModuleNotFoundError: No module named 'app.auth'`.

- [ ] **Step 3: Create the empty package marker**

`app/auth/__init__.py`:

```python
"""Canonical platform auth — token primitives, FastAPI dependencies.

See docs/superpowers/specs/2026-05-14-canonical-auth-v2-design.md for the
contract. Coexists with legacy auth in main.py and app/dependencies.py;
they share SECRET_KEY but issue and accept different token shapes.
"""
```

- [ ] **Step 4: Implement model + exception**

`app/auth/canonical.py`:

```python
"""Canonical platform JWT primitives.

This module owns the v2 token contract end-to-end: model, encode, decode,
and DB-side provisioning. Endpoints in app/routers/auth_v2.py are thin
wrappers that call helpers here.

Token shape (per spec §4):
    {
      "sub":    "<user-uuid>",
      "email":  "<email>",
      "org_id": "<org-uuid>",
      "role":   "<role>",
      "jti":    "<random-uuid>",
      "iat":    <unix-ts>,
      "exp":    <unix-ts>
    }
"""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, EmailStr


class CanonicalTokenError(Exception):
    """Raised by decode_canonical_token when a token is rejected.

    Messages never include token contents — only the reason the token
    was rejected ("expired", "missing claim 'org_id'", etc.). This lets
    get_current_canonical_user surface the reason in the 401 detail
    without leaking JWT material to logs or clients.
    """


class CanonicalUser(BaseModel):
    """Validated decoded form of a v2 JWT.

    Used both as the return type of decode_canonical_token and as the
    response model for GET /api/auth/v2/me. EmailStr enforces RFC 5321
    shape on the email claim.
    """

    user_id: UUID
    org_id: UUID
    email: EmailStr
    role: str
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python3 -m pytest tests/unit/test_auth_v2.py -x -q
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add app/auth/__init__.py app/auth/canonical.py tests/unit/test_auth_v2.py
git commit -m "feat(auth-v2): CanonicalUser model + CanonicalTokenError

Pydantic model + exception class for the canonical platform JWT.
First module in the new app/auth/ package. No token logic yet — that
lands in the next task. See spec §4 + §8."
```

---

## Task 2: `create_canonical_token` (pure JWT encoding)

**Files:**
- Modify: `app/auth/canonical.py` (add function + import)
- Modify: `tests/unit/test_auth_v2.py` (add tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_auth_v2.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/unit/test_auth_v2.py -x -q -k "create_canonical_token"
```

Expected: 2 errors, `ImportError: cannot import name 'create_canonical_token'`.

- [ ] **Step 3: Implement the function**

Append to `app/auth/canonical.py`:

```python
import uuid as _uuid
from datetime import datetime, timedelta, timezone

import jwt

from agents.config import ACCESS_TOKEN_EXPIRE_MINUTES, ALGORITHM, SECRET_KEY


def create_canonical_token(
    *,
    user_id: UUID,
    org_id: UUID,
    email: str,
    role: str,
) -> str:
    """Encode a v2 platform JWT for the given user.

    Pure function — does not touch the database. Caller is responsible
    for having already verified the user exists and resolved their org.

    Expiry is ACCESS_TOKEN_EXPIRE_MINUTES from issuance, identical to
    legacy tokens (currently 24h). HS256, signed with shared SECRET_KEY.

    Every token gets a fresh `jti` (UUID) so that a future Redis blocklist
    can revoke individual tokens without re-issuing. The blocklist itself
    is out of scope for step 3.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "org_id": str(org_id),
        "role": role,
        "jti": str(_uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)).timestamp()),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/unit/test_auth_v2.py -x -q
```

Expected: 5 passed (3 from Task 1 + 2 new).

- [ ] **Step 5: Commit**

```bash
git add app/auth/canonical.py tests/unit/test_auth_v2.py
git commit -m "feat(auth-v2): create_canonical_token encoder

Pure JWT encoding with the canonical claim set. Uses shared SECRET_KEY
and ALGORITHM from agents.config. Every token gets a fresh jti for
future blocklist-based revocation (deferred to step 4)."
```

---

## Task 3: `decode_canonical_token` (validation)

**Files:**
- Modify: `app/auth/canonical.py`
- Modify: `tests/unit/test_auth_v2.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_auth_v2.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/unit/test_auth_v2.py -x -q -k "decode"
```

Expected: 7 errors / failures, `ImportError: cannot import name 'decode_canonical_token'`.

- [ ] **Step 3: Implement decode_canonical_token**

Append to `app/auth/canonical.py`:

```python
from pydantic import ValidationError as _PydanticValidationError


_REQUIRED_CLAIMS = ("sub", "email", "org_id", "role", "jti", "iat", "exp")


def decode_canonical_token(token: str) -> CanonicalUser:
    """Validate a v2 platform JWT and return the decoded CanonicalUser.

    Rejects (CanonicalTokenError):
      - Bad signature, expired, or otherwise malformed JWT.
      - Any missing required claim from _REQUIRED_CLAIMS.
      - Non-UUID 'sub' or 'org_id'.
      - 'email' that does not pass EmailStr validation.

    Does not touch the database — the token is self-contained.
    """
    try:
        claims = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as e:
        raise CanonicalTokenError("token expired") from e
    except jwt.InvalidTokenError as e:
        raise CanonicalTokenError(f"invalid token: {e}") from e

    missing = [c for c in _REQUIRED_CLAIMS if c not in claims]
    if missing:
        raise CanonicalTokenError(f"missing required claim(s): {', '.join(missing)}")

    try:
        user_id = UUID(claims["sub"])
    except (ValueError, TypeError) as e:
        raise CanonicalTokenError("'sub' is not a valid UUID") from e

    try:
        org_id = UUID(claims["org_id"])
    except (ValueError, TypeError) as e:
        raise CanonicalTokenError("'org_id' is not a valid UUID") from e

    try:
        return CanonicalUser(
            user_id=user_id,
            org_id=org_id,
            email=claims["email"],
            role=claims["role"],
        )
    except _PydanticValidationError as e:
        # Surfacing the field name is fine; the value would leak token contents.
        fields = ", ".join(err["loc"][0] for err in e.errors())
        raise CanonicalTokenError(f"invalid claim shape: {fields}") from e
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/unit/test_auth_v2.py -x -q
```

Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add app/auth/canonical.py tests/unit/test_auth_v2.py
git commit -m "feat(auth-v2): decode_canonical_token validator

Validates v2 JWTs against the canonical claim shape, returning a
CanonicalUser on success and raising CanonicalTokenError otherwise.
Legacy-shaped tokens are explicitly rejected by the required-claims
check (no org_id / no jti). No DB access."
```

---

## Task 4: `provision_canonical_user` (DB transaction)

**Files:**
- Modify: `app/auth/canonical.py`
- Modify: `tests/unit/test_auth_v2.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_auth_v2.py`:

```python
# ---------- Task 4: provision_canonical_user ----------

import asyncio
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest_asyncio.fixture
async def db_engine():
    """Async engine pointed at the docker-compose test Postgres.

    Requires TEST_DATABASE_URL exported. Migration 0002 must already
    have run against this DB (see plan Task 0).
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/unit/test_auth_v2.py -x -q -k "provision"
```

Expected: error — `AttributeError: module 'app.auth.canonical' has no attribute 'provision_canonical_user'`.

- [ ] **Step 3: Implement provision_canonical_user**

Append to `app/auth/canonical.py`:

```python
import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.models import Credits, Entitlement, Organization, User
from app.db.session import get_session_maker

logger = logging.getLogger(__name__)


def _session_maker_for_provision():
    """Indirection point so tests can swap in their own session maker
    without monkey-patching get_session_maker globally."""
    return get_session_maker()


async def provision_canonical_user(*, email: str, source: str) -> User:
    """Create canonical user + org + credits + growth_engine entitlement
    for a verified email. Single transaction.

    Idempotent under race: if another request creates the user between
    our SELECT and INSERT, the unique(email) constraint fires and we
    re-query to return whoever won.

    source: 'google' | 'magic_link' — used only in the log line emitted
            on successful provisioning. Not stored on any row today.
    """
    email = email.lower().strip()
    maker = _session_maker_for_provision()
    async with maker() as session:
        existing = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        try:
            async with session.begin():
                org = Organization(name=email)
                session.add(org)
                await session.flush()

                user = User(
                    email=email,
                    org_id=org.id,
                    is_active=True,
                    role="user",
                )
                session.add(user)
                await session.flush()

                session.add(Credits(org_id=org.id, balance=0, plan_monthly_limit=0))
                session.add(Entitlement(org_id=org.id, module="growth_engine"))
            await session.refresh(user)
            logger.info(f"auth-v2: provisioned canonical user {email} (source={source})")
            return user
        except IntegrityError:
            # Race: someone else won the INSERT. Re-query and return theirs.
            await session.rollback()
            return (
                await session.execute(select(User).where(User.email == email))
            ).scalar_one()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/unit/test_auth_v2.py -x -q -k "provision"
```

Expected: 1 passed.

- [ ] **Step 5: Add the idempotency test**

Append to `tests/unit/test_auth_v2.py`:

```python
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
```

- [ ] **Step 6: Run idempotency test**

```bash
python3 -m pytest tests/unit/test_auth_v2.py -x -q -k "provision"
```

Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add app/auth/canonical.py tests/unit/test_auth_v2.py
git commit -m "feat(auth-v2): provision_canonical_user with auto-org creation

Single-transaction provisioning of user + org + credits + growth_engine
entitlement for a verified email. Idempotent on repeat (returns the
existing user) and idempotent under race (IntegrityError → re-query).
Replicates migration 0002 backfill logic for new users."
```

---

## Task 5: `get_current_canonical_user` FastAPI dependency

**Files:**
- Create: `app/auth/dependencies.py`
- Modify: `tests/unit/test_auth_v2.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_auth_v2.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/unit/test_auth_v2.py -x -q -k "dependency"
```

Expected: 4 errors — `ModuleNotFoundError: No module named 'app.auth.dependencies'`.

- [ ] **Step 3: Implement the dependency**

`app/auth/dependencies.py`:

```python
"""FastAPI dependency for the canonical v2 JWT.

This is the v2 counterpart to legacy `get_current_user` in main.py and
in app/dependencies.py. They are independent: each decodes its own
token shape. Endpoints opt in by importing whichever they need.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.canonical import CanonicalTokenError, CanonicalUser, decode_canonical_token

_security = HTTPBearer()


async def get_current_canonical_user(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
) -> CanonicalUser:
    """Validate a canonical v2 JWT and return the user.

    Returns 401 (via HTTPException) on any failure: bad signature,
    expired, missing claim, malformed UUID, malformed email. The
    detail string comes from CanonicalTokenError and never includes
    token contents.
    """
    try:
        return decode_canonical_token(credentials.credentials)
    except CanonicalTokenError as e:
        raise HTTPException(status_code=401, detail=str(e))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/unit/test_auth_v2.py -x -q -k "dependency"
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add app/auth/dependencies.py tests/unit/test_auth_v2.py
git commit -m "feat(auth-v2): get_current_canonical_user FastAPI dependency

HTTPBearer-based dependency that decodes v2 JWTs and rejects legacy
or malformed tokens with 401. Independent of legacy get_current_user
in main.py — neither touches the other."
```

---

## Task 6: `/api/auth/v2/me` endpoint + router scaffolding

**Files:**
- Create: `app/routers/auth_v2.py`
- Modify: `tests/unit/test_auth_v2.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_auth_v2.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/unit/test_auth_v2.py -x -q -k "test_me"
```

Expected: errors — `ModuleNotFoundError: No module named 'app.routers.auth_v2'`.

- [ ] **Step 3: Create the router with /me**

`app/routers/auth_v2.py`:

```python
"""Canonical platform auth endpoints (v2).

Mounted at /api/auth/v2/* from main.py. Coexists with legacy /auth/*
endpoints — they share SECRET_KEY but issue and accept different token
shapes. See docs/superpowers/specs/2026-05-14-canonical-auth-v2-design.md.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from fastapi.responses import Response

from app.auth.canonical import CanonicalUser
from app.auth.dependencies import get_current_canonical_user

router = APIRouter()


@router.get("/me", response_model=CanonicalUser, summary="Current canonical user")
async def me(user: CanonicalUser = Depends(get_current_canonical_user)) -> CanonicalUser:
    """Return the canonical user derived from the validated v2 JWT.

    Does not re-query the DB. The token's claims are the source of truth
    for this endpoint — by definition the token was issued from validated
    DB state, and revocation will be handled via the future blocklist
    rather than per-request lookups.
    """
    return user
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/unit/test_auth_v2.py -x -q -k "test_me"
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add app/routers/auth_v2.py tests/unit/test_auth_v2.py
git commit -m "feat(auth-v2): GET /api/auth/v2/me endpoint + router scaffold

First v2 endpoint. Returns the canonical user decoded from the JWT.
Sets up the app/routers/auth_v2.py module that subsequent tasks add
endpoints to."
```

---

## Task 7: `POST /api/auth/v2/logout`

**Files:**
- Modify: `app/routers/auth_v2.py`
- Modify: `tests/unit/test_auth_v2.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_auth_v2.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/unit/test_auth_v2.py -x -q -k "logout"
```

Expected: 3 errors — 404 because the endpoint does not exist.

- [ ] **Step 3: Implement /logout**

Append to `app/routers/auth_v2.py`:

```python
@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Sign out (no-op server-side)",
)
async def logout() -> Response:
    """No-op logout — returns 204.

    Frontend is responsible for deleting the token from its own storage.
    The token remains technically valid against the canonical dependency
    until `exp`, but with the frontend no longer sending it, that
    technically-valid window has no effect.

    Forward compatibility: when step 4 adds the Redis blocklist, this
    endpoint will extract the request token's `jti` and insert it into
    the blocklist with TTL = remaining exp. No URL change.
    """
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/unit/test_auth_v2.py -x -q -k "logout"
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add app/routers/auth_v2.py tests/unit/test_auth_v2.py
git commit -m "feat(auth-v2): POST /api/auth/v2/logout no-op endpoint

Returns 204 unconditionally — does not validate the request token,
does not touch DB, does not maintain server-side session state.
Future blocklist (step 4) hooks in here without changing the URL."
```

---

## Task 8: `POST /api/auth/v2/google/native`

**Files:**
- Modify: `app/routers/auth_v2.py`
- Modify: `tests/unit/test_auth_v2.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_auth_v2.py`:

```python
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
    client = TestClient(app)

    r = client.post(
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/unit/test_auth_v2.py -x -q -k "google_native"
```

Expected: 404 errors (endpoint not registered yet).

- [ ] **Step 3: Implement the endpoint**

Append to `app/routers/auth_v2.py`:

```python
import logging
import os

from fastapi import HTTPException
from pydantic import BaseModel, EmailStr

from app.auth.canonical import create_canonical_token, provision_canonical_user

logger = logging.getLogger(__name__)


class GoogleNativeRequest(BaseModel):
    credential: str


class V2TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: CanonicalUser


def _verify_google_id_token(credential: str) -> dict:
    """Verify a Google id_token against the configured audiences. Returns
    the verified token claims dict. Raises HTTPException on any failure.

    Audiences: GOOGLE_CLIENT_ID plus comma-separated GOOGLE_ADDITIONAL_CLIENT_IDS.
    Mirrors the audience policy of legacy /auth/google/native (main.py:7252).
    """
    google_client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    if not google_client_id:
        raise HTTPException(status_code=500, detail="GOOGLE_CLIENT_ID not configured")

    extra = [
        a.strip()
        for a in os.getenv("GOOGLE_ADDITIONAL_CLIENT_IDS", "").split(",")
        if a.strip()
    ]
    audiences = [google_client_id, *extra]

    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token as google_id_token

        return google_id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            audiences if len(audiences) > 1 else audiences[0],
        )
    except ValueError as e:
        logger.warning(f"auth-v2 google/native: id_token verification failed: {e}")
        raise HTTPException(status_code=401, detail=f"invalid Google token: {e}")
    except Exception as e:  # noqa: BLE001 — Google libs raise broad types on transport errors
        logger.error(f"auth-v2 google/native: unexpected verification error: {e}")
        raise HTTPException(status_code=500, detail="Google token verification failed")


@router.post(
    "/google/native",
    response_model=V2TokenResponse,
    summary="Native Google sign-in → canonical v2 token",
)
async def google_native(req: GoogleNativeRequest) -> V2TokenResponse:
    """Verify a Google id_token, look up or auto-provision the canonical
    user, return a v2 JWT.

    Ports legacy /auth/google/native (main.py:7209) onto the canonical
    schema and token shape.
    """
    credential = (req.credential or "").strip()
    if not credential:
        raise HTTPException(status_code=400, detail="missing 'credential' (Google id_token)")

    idinfo = _verify_google_id_token(credential)

    email = (idinfo.get("email") or "").lower().strip()
    if not email or not idinfo.get("email_verified", False):
        raise HTTPException(status_code=400, detail="Google email not verified")

    user_row = await provision_canonical_user(email=email, source="google")

    token = create_canonical_token(
        user_id=user_row.id,
        org_id=user_row.org_id,
        email=user_row.email,
        role=user_row.role,
    )
    canonical_user = CanonicalUser(
        user_id=user_row.id,
        org_id=user_row.org_id,
        email=user_row.email,
        role=user_row.role,
    )
    logger.info(f"auth-v2 google/native: issued v2 token for {email}")
    return V2TokenResponse(access_token=token, user=canonical_user)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/unit/test_auth_v2.py -x -q -k "google_native"
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add app/routers/auth_v2.py tests/unit/test_auth_v2.py
git commit -m "feat(auth-v2): POST /api/auth/v2/google/native

Ports legacy /auth/google/native onto canonical identity + v2 token
shape. Verifies Google id_token against configured audiences (inc.
iOS additional client IDs), auto-provisions new users, issues v2 JWT."
```

---

## Task 9: `POST /api/auth/v2/magic-link/request`

**Files:**
- Modify: `app/routers/auth_v2.py`
- Modify: `tests/unit/test_auth_v2.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_auth_v2.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/unit/test_auth_v2.py -x -q -k "magic_link_request"
```

Expected: 404 errors.

- [ ] **Step 3: Implement the endpoint**

Append to `app/routers/auth_v2.py`:

```python
from fastapi import BackgroundTasks, Request


class MagicLinkRequestBody(BaseModel):
    email: EmailStr


class MagicLinkRequestResponse(BaseModel):
    status: str  # always "sent"


def _get_magic_link_auth():
    """Pull the already-initialized magic_link_auth singleton from main.py.

    Indirection so tests can swap it out. main.py initializes
    magic_link_auth at startup (main.py:1671); we use whatever it
    holds today. May be None if Redis/SMTP are not configured —
    in which case the endpoint silently no-ops and returns 'sent'.
    """
    try:
        import main  # type: ignore[import-not-found]

        return getattr(main, "magic_link_auth", None)
    except Exception:  # noqa: BLE001 — main may not be importable in some test setups
        return None


@router.post(
    "/magic-link/request",
    response_model=MagicLinkRequestResponse,
    summary="Request a magic link email",
)
async def magic_link_request(
    body: MagicLinkRequestBody,
    request: Request,
    background_tasks: BackgroundTasks,
) -> MagicLinkRequestResponse:
    """Send a magic-link email to the given address.

    Delegates to the existing magic_link_auth subsystem (auth_magic_link.py)
    which handles rate-limiting, token storage, and email send. The
    response is always `{"status": "sent"}` regardless of whether the
    email exists — same anti-enumeration behavior as the legacy endpoint.
    """
    email = body.email.lower().strip()
    mla = _get_magic_link_auth()
    if mla is None:
        logger.warning("auth-v2 magic-link/request: magic_link_auth not configured")
        return MagicLinkRequestResponse(status="sent")

    try:
        await mla.send_magic_link(
            email=email,
            request=request,
            background_tasks=background_tasks,
        )
    except HTTPException:
        # Rate-limit hits (429) etc. — let them propagate to the client
        # because the legacy endpoint does the same.
        raise
    except Exception as e:  # noqa: BLE001
        logger.error(f"auth-v2 magic-link/request: send failed for {email}: {e}")
        # Still return 'sent' so we don't reveal whether the email is registered
    return MagicLinkRequestResponse(status="sent")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/unit/test_auth_v2.py -x -q -k "magic_link_request"
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add app/routers/auth_v2.py tests/unit/test_auth_v2.py
git commit -m "feat(auth-v2): POST /api/auth/v2/magic-link/request

Wraps the existing magic_link_auth subsystem with the v2 URL prefix.
Always returns {status: 'sent'} to avoid leaking which emails are
registered, matching legacy /auth/magic-link/request behavior."
```

---

## Task 10: `POST /api/auth/v2/magic-link/verify`

**Files:**
- Modify: `app/routers/auth_v2.py`
- Modify: `tests/unit/test_auth_v2.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_auth_v2.py`:

```python
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

    app = _build_router_test_app()
    client = TestClient(app)
    r = client.post("/api/auth/v2/magic-link/verify", json={"token": "good-token"})
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/unit/test_auth_v2.py -x -q -k "magic_link_verify"
```

Expected: 404 errors.

- [ ] **Step 3: Implement the endpoint**

Append to `app/routers/auth_v2.py`:

```python
class MagicLinkVerifyBody(BaseModel):
    token: str


@router.post(
    "/magic-link/verify",
    response_model=V2TokenResponse,
    summary="Verify magic link → canonical v2 token",
)
async def magic_link_verify(
    body: MagicLinkVerifyBody, request: Request
) -> V2TokenResponse:
    """Verify a magic-link single-use token and issue a v2 JWT.

    Ports legacy GET /auth/magic-link/verify (main.py:6874) — but as POST
    with a JSON body because the call is server-to-server XHR from the
    frontend page that the email link redirects to.
    """
    mla = _get_magic_link_auth()
    if mla is None:
        raise HTTPException(status_code=503, detail="Magic link authentication not available")

    result = await mla.verify_magic_link(token=body.token, request=request)
    if not result or not result.get("valid"):
        raise HTTPException(status_code=400, detail="Invalid or expired magic link")

    email = (result.get("user") or {}).get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Invalid magic link response")
    email = email.lower().strip()

    user_row = await provision_canonical_user(email=email, source="magic_link")

    token = create_canonical_token(
        user_id=user_row.id,
        org_id=user_row.org_id,
        email=user_row.email,
        role=user_row.role,
    )
    canonical_user = CanonicalUser(
        user_id=user_row.id,
        org_id=user_row.org_id,
        email=user_row.email,
        role=user_row.role,
    )
    logger.info(f"auth-v2 magic-link/verify: issued v2 token for {email}")
    return V2TokenResponse(access_token=token, user=canonical_user)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/unit/test_auth_v2.py -x -q -k "magic_link_verify"
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add app/routers/auth_v2.py tests/unit/test_auth_v2.py
git commit -m "feat(auth-v2): POST /api/auth/v2/magic-link/verify

Verifies single-use magic-link token via existing magic_link_auth
subsystem, auto-provisions canonical user, issues v2 token.
Completes the five-endpoint v2 surface."
```

---

## Task 11: Mount router in `main.py` (production wiring)

**Files:**
- Modify: `main.py` (one insert)
- Modify: `tests/unit/test_auth_v2.py`

- [ ] **Step 1: Locate the right insertion point**

```bash
grep -n "include_router" main.py
```

Expected output: lines mounting `chat`, `books`, `health` (existing `app/routers/*`). Insert after the last such call in the same block.

- [ ] **Step 2: Write the failing test**

Append to `tests/unit/test_auth_v2.py`:

```python
# ---------- Task 11: production app mounts the router ----------


def test_main_app_mounts_v2_router():
    """Importing main.py registers the v2 router. We don't run any
    request — just assert at least one /api/auth/v2/* route exists on
    the actual FastAPI app object. Catches the case where someone
    forgets the include_router line."""
    import main  # imports the production app

    paths = {getattr(r, "path", "") for r in main.app.routes}
    v2_paths = {p for p in paths if p.startswith("/api/auth/v2")}
    assert v2_paths, f"no /api/auth/v2/* routes found on main.app; have: {sorted(paths)[:20]}"
```

- [ ] **Step 3: Run test to verify it fails**

```bash
python3 -m pytest tests/unit/test_auth_v2.py -x -q -k "main_app_mounts"
```

Expected: AssertionError — no `/api/auth/v2/*` routes registered.

- [ ] **Step 4: Modify main.py**

Find the block where other `app/routers/*` are included (look for `include_router(chat`, `include_router(books`, or `include_router(health`). Insert immediately after the last existing call:

```python
# Canonical platform identity (v2) — Phase 4.1 step 2.
# Coexists with legacy /auth/* endpoints in this file.
try:
    from app.routers.auth_v2 import router as auth_v2_router
    app.include_router(auth_v2_router, prefix="/api/auth/v2", tags=["auth-v2"])
    logger.info("✅ Mounted canonical auth v2 router at /api/auth/v2")
except Exception as e:  # noqa: BLE001 — never crash boot over a failed mount
    logger.error(f"❌ Failed to mount auth_v2 router: {e}")
```

- [ ] **Step 5: Run test to verify it passes**

```bash
python3 -m pytest tests/unit/test_auth_v2.py -x -q -k "main_app_mounts"
```

Expected: 1 passed.

- [ ] **Step 6: Run the full v2 test suite**

```bash
python3 -m pytest tests/unit/test_auth_v2.py -x -q
```

Expected: all v2 tests pass (full count).

- [ ] **Step 7: Run the full project test suite to confirm nothing broke**

```bash
python3 -m pytest tests/ -x -q -m "not slow and not integration and not e2e"
```

Expected: previously-passing tests still pass, plus the new v2 tests. Compare count against the pre-step baseline (625 passed, 29 skipped, 15 deselected as of 2026-05-13).

- [ ] **Step 8: Commit**

```bash
git add main.py tests/unit/test_auth_v2.py
git commit -m "feat(auth-v2): mount /api/auth/v2 router in production app

Wires the v2 endpoints into main.py — the entrypoint Railway actually
runs. Try/except guard so a mount failure logs but does not crash
boot. Legacy /auth/* paths are untouched."
```

---

## Task 12: CHANGELOG entry + final verification

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Add CHANGELOG entry**

Open `CHANGELOG.md`. Under the existing `## [unreleased]` heading (or create one if none) add this block as the newest entry **above** the previous identity-migration entry from 2026-05-13:

```markdown
## [unreleased] - 2026-05-14 — Canonical auth v2 (Phase 4.1 step 2)

### Added
- **`app/auth/` package** — canonical platform JWT primitives:
  `CanonicalUser` model, `CanonicalTokenError`, `create_canonical_token`,
  `decode_canonical_token`, `provision_canonical_user`. Token shape:
  `{sub=<user_uuid>, email, org_id=<org_uuid>, role, jti, iat, exp}`,
  HS256 with shared `SECRET_KEY`. Matches the contract documented in
  Continuity's `apps/continuity-api/src/continuity_api/auth/brandista_core.py`.
- **`app/auth/dependencies.py:get_current_canonical_user`** — FastAPI
  dependency that validates v2 JWTs and rejects legacy-shaped tokens
  with 401. Independent of legacy `get_current_user` in `main.py` and
  `app/dependencies.py`.
- **`app/routers/auth_v2.py`** — five new endpoints mounted at
  `/api/auth/v2/*`:
  - `POST /google/native` — ports legacy `/auth/google/native` onto
    canonical schema + v2 token shape.
  - `POST /magic-link/request` — wraps existing `magic_link_auth.send_magic_link`.
  - `POST /magic-link/verify` — verifies single-use token, auto-provisions
    canonical user, issues v2 JWT.
  - `GET /me` — returns the canonical user from the validated token.
  - `POST /logout` — no-op (204). Frontend deletes token client-side.
    Future Redis blocklist (deferred to step 4+) hooks in here without
    changing the URL.
- **Auto-provisioning** — when an unknown email signs in via Google or
  magic-link verify, `provision_canonical_user` creates user + org +
  credits + `growth_engine` entitlement in a single transaction.
  Idempotent under race (UNIQUE(email) constraint → re-query on
  IntegrityError).

### Unchanged (deliberate)
- Legacy `/auth/*` endpoints in `main.py` — `/auth/login`, `/auth/google/native`,
  `/auth/magic-link/request`, `/auth/magic-link/verify`. All keep working
  against the legacy token shape (`sub=email`). No code touched.
- Legacy `get_current_user` in `main.py:2334` and `app/dependencies.py:29`.
- `agents/config.py` — same `SECRET_KEY` and `ALGORITHM` for both shapes.

### Tests
- `tests/unit/test_auth_v2.py` — model validation, token roundtrip,
  legacy/expired/malformed-token rejection, dependency 401/403 paths,
  endpoint happy paths, auto-provisioning under repeat, mount verification.
  DB-touching tests use the docker-compose Postgres on port 5433 (see
  `infra/docker-compose.yml`).

### Sprint context
- Phase 4.1 step 2 — first endpoints that actually issue and accept
  canonical platform JWTs. The schema (step 1, 2026-05-13) is now in
  use, not just sitting in the DB. Sprint application §02
  "multiple domain agents reasoning over a single shared
  organisational memory" — this is the auth/identity layer that
  carries `(user_id, org_id)` across products.

### Deferred to follow-ups
- **Step 3.5:** Apple Sign In — needs `users.apple_id` migration,
  Apple Developer Service ID config, JWKS verification, private-relay
  email handling. Lands once Google v2 is already in production.
- **Step 4:** Refresh tokens, RS256/JWKS migration, `entitlements`
  claim in token, real revocation via Redis blocklist (the `jti` claim
  is already populated — only the blocklist lookup is missing).
- **Step 5+:** Legacy `/auth/*` endpoint deprecation, frontend cutover.

### Deploy notes
- No schema migration in this step (step 1 already shipped the schema).
- Requires no new env vars — uses existing `SECRET_KEY`, `GOOGLE_CLIENT_ID`,
  `GOOGLE_ADDITIONAL_CLIENT_IDS`, magic-link / SMTP env (already set
  in production).
- Additive only — legacy paths untouched, so no production rollback
  drill needed beyond the standard "revert the commit and redeploy".
```

- [ ] **Step 2: Run the full test suite one more time**

```bash
python3 -m pytest tests/ -x -q -m "not slow and not integration and not e2e"
```

Expected: green.

- [ ] **Step 3: Manual smoke test of legacy path (no app boot required — purely import-level)**

```bash
python3 -c "
import main
# Legacy endpoints still registered
paths = {getattr(r, 'path', '') for r in main.app.routes}
assert '/auth/google/native' in paths
assert '/auth/magic-link/verify' in paths
assert '/auth/magic-link/request' in paths
# v2 endpoints registered
assert '/api/auth/v2/me' in paths
assert '/api/auth/v2/logout' in paths
assert '/api/auth/v2/google/native' in paths
assert '/api/auth/v2/magic-link/request' in paths
assert '/api/auth/v2/magic-link/verify' in paths
print('OK — legacy + v2 both mounted')
"
```

Expected: `OK — legacy + v2 both mounted`.

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): canonical auth v2 (Phase 4.1 step 2)

Five new /api/auth/v2/* endpoints, auto-provisioning, jti for future
blocklist. Legacy /auth/* untouched. No schema migration in this step."
```

- [ ] **Step 5: Push the branch**

```bash
git push
```

The branch (`feat/canonical-platform-identity`) is already tracking `origin/feat/canonical-platform-identity`. No PR needs to be opened from this plan — coordinate that with the human reviewing the work.

---

## Acceptance gate (run before declaring done)

- [ ] `python3 -m pytest tests/unit/test_auth_v2.py -x -q` → all tests passing (no skips other than DB-touching tests in environments without the docker DB).
- [ ] `python3 -m pytest tests/ -x -q -m "not slow and not integration and not e2e"` → still green, count not lower than the 2026-05-13 baseline of 625 passed.
- [ ] `git log --oneline feat/canonical-platform-identity ^main` (or equivalent) shows 12 new commits — one per task — with messages following the conventional prefix style (`feat(auth-v2):`, `docs(changelog):`).
- [ ] Manual import smoke test from Task 12 step 3 prints "OK — legacy + v2 both mounted".
