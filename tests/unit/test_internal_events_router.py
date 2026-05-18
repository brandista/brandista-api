"""Integration tests for the internal-secret event-publish router.

DB-touching tests that exercise the server-to-server publish path
used by Continuity's SBE pipeline. Mirror of `test_events_router.py`
plus the identity-resolution + allowlist cases.

Boot:
    cd infra && docker compose up -d postgres
    DATABASE_URL=postgresql://brandista:dev@localhost:5433/brandista \\
        alembic upgrade head
"""
from __future__ import annotations

import os
import uuid
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool


os.environ.setdefault("BRANDISTA_INTERNAL_SECRET", "test-internal-secret")
os.environ.setdefault("SECRET_KEY", "test-jwt-secret")


@pytest_asyncio.fixture
async def db_engine():
    raw = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql://brandista:dev@localhost:5433/brandista",
    )
    dsn = (
        raw.replace("postgresql://", "postgresql+asyncpg://", 1)
        if "+asyncpg" not in raw
        else raw
    )
    engine = create_async_engine(dsn, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        await session.execute(
            text(
                "TRUNCATE TABLE "
                "event_audit, event_handler_attempts, "
                "event_subscriber_checkpoints, events "
                "RESTART IDENTITY CASCADE"
            )
        )
        await session.execute(
            text(
                "TRUNCATE TABLE "
                "entitlements, credits, profile_facts, user_email_aliases, "
                "users, organizations "
                "RESTART IDENTITY CASCADE"
            )
        )
        await session.commit()
        yield session


@pytest_asyncio.fixture
async def seeded_user(db_session: AsyncSession):
    user_id = uuid4()
    org_id = uuid4()
    email = f"user-{user_id}@example.com"
    await db_session.execute(
        text("INSERT INTO organizations (id, name) VALUES (:org, :name)"),
        {"org": org_id, "name": "Test Org"},
    )
    await db_session.execute(
        text(
            "INSERT INTO users (id, org_id, email, is_active, role, username) "
            "VALUES (:id, :org, :email, true, 'user', :uname)"
        ),
        {"id": user_id, "org": org_id, "email": email, "uname": email},
    )
    await db_session.commit()
    return user_id, org_id, email


def _build_internal_events_app(db_session: AsyncSession) -> FastAPI:
    from app.db.session import get_session
    from app.routers.internal_events import router as internal_events_router

    app = FastAPI()
    app.include_router(
        internal_events_router,
        prefix="/api/v1/internal/events",
        tags=["internal-events"],
    )

    async def _override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = _override_get_session
    return app


INTERNAL = {"X-Brandista-Internal-Auth": "test-internal-secret"}


def _recovery_payload(severity: str = "significant", rank: int = 3) -> dict:
    return {
        "observed_at": "2026-05-16T06:14:00Z",
        "severity": severity,
        "severity_rank": rank,
        "hrv_drop_pct": -27.0,
        "contributing_signals": ["hrv_below_baseline", "sleep_deficit"],
    }


def _publish_body(**overrides) -> dict:
    base = {
        "event_type": "health.recovery_pressure",
        "event_version": 1,
        "source_product": "continuity",
        "occurred_at": "2026-05-16T06:14:00Z",
        "idempotency_key": "continuity:rp:user-1:2026-05-16T06:14:00Z",
        "payload": _recovery_payload(),
    }
    base.update(overrides)
    return base


# ---------- happy path ----------


@pytest.mark.asyncio
async def test_publish_by_user_id_happy_path(db_session, seeded_user):
    user_id, org_id, email = seeded_user
    app = _build_internal_events_app(db_session)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        r = await client.post(
            "/api/v1/internal/events",
            headers=INTERNAL,
            json={**_publish_body(), "user_id": str(user_id)},
        )

    assert r.status_code == 201, r.text
    body = r.json()
    assert body["idempotent"] is False
    assert body["resolved_user_id"] == str(user_id)
    assert body["event_seq"] >= 1
    assert len(body["envelope_sig_hex"]) == 64

    # severity_rank populated on the row by the registry hot-path hook.
    row = (
        await db_session.execute(
            text("SELECT severity_rank FROM events WHERE event_id = :eid"),
            {"eid": body["event_id"]},
        )
    ).one()
    assert row[0] == 3


@pytest.mark.asyncio
async def test_publish_by_email_resolves_to_user_id(db_session, seeded_user):
    user_id, _, email = seeded_user
    app = _build_internal_events_app(db_session)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        r = await client.post(
            "/api/v1/internal/events",
            headers=INTERNAL,
            json={**_publish_body(), "email": email},
        )

    assert r.status_code == 201, r.text
    body = r.json()
    assert body["resolved_user_id"] == str(user_id)


@pytest.mark.asyncio
async def test_publish_by_email_alias_resolves_to_user_id(db_session, seeded_user):
    user_id, _, _ = seeded_user
    alias = f"alias-{user_id}@example.com"
    await db_session.execute(
        text(
            "INSERT INTO user_email_aliases (email, user_id) "
            "VALUES (:email, :user_id)"
        ),
        {"email": alias, "user_id": user_id},
    )
    await db_session.commit()
    app = _build_internal_events_app(db_session)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        r = await client.post(
            "/api/v1/internal/events",
            headers=INTERNAL,
            json={**_publish_body(), "email": alias.upper()},
        )

    assert r.status_code == 201, r.text
    assert r.json()["resolved_user_id"] == str(user_id)


# ---------- idempotency ----------


@pytest.mark.asyncio
async def test_idempotency_match_returns_200(db_session, seeded_user):
    user_id, _, _ = seeded_user
    app = _build_internal_events_app(db_session)
    body = {**_publish_body(), "user_id": str(user_id)}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        first = await client.post("/api/v1/internal/events", headers=INTERNAL, json=body)
        second = await client.post("/api/v1/internal/events", headers=INTERNAL, json=body)

    assert first.status_code == 201
    assert second.status_code == 200, second.text
    assert second.json()["idempotent"] is True
    assert second.json()["event_id"] == first.json()["event_id"]


@pytest.mark.asyncio
async def test_idempotency_payload_mismatch_returns_409(db_session, seeded_user):
    user_id, _, _ = seeded_user
    app = _build_internal_events_app(db_session)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        first = await client.post(
            "/api/v1/internal/events",
            headers=INTERNAL,
            json={**_publish_body(), "user_id": str(user_id)},
        )
        second = await client.post(
            "/api/v1/internal/events",
            headers=INTERNAL,
            json={
                **_publish_body(payload=_recovery_payload(severity="moderate", rank=2)),
                "user_id": str(user_id),
            },
        )

    assert first.status_code == 201
    assert second.status_code == 409, second.text
    assert "idempotency_payload_mismatch" in second.text


# ---------- allowlist + identity guards ----------


@pytest.mark.asyncio
async def test_source_product_outside_allowlist_403(db_session, seeded_user):
    user_id, _, _ = seeded_user
    app = _build_internal_events_app(db_session)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        # veyra is intentionally absent from _INTERNAL_PUBLISHER_ALLOWLIST.
        r = await client.post(
            "/api/v1/internal/events",
            headers=INTERNAL,
            json={
                **_publish_body(source_product="veyra"),
                "user_id": str(user_id),
            },
        )
    assert r.status_code == 403, r.text
    assert "allowlist" in r.text or "internal publisher" in r.text


@pytest.mark.asyncio
async def test_neither_user_id_nor_email_400(db_session, seeded_user):
    app = _build_internal_events_app(db_session)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        r = await client.post(
            "/api/v1/internal/events",
            headers=INTERNAL,
            json=_publish_body(),
        )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_both_user_id_and_email_400(db_session, seeded_user):
    user_id, _, email = seeded_user
    app = _build_internal_events_app(db_session)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        r = await client.post(
            "/api/v1/internal/events",
            headers=INTERNAL,
            json={**_publish_body(), "user_id": str(user_id), "email": email},
        )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_unknown_user_id_404(db_session, seeded_user):
    app = _build_internal_events_app(db_session)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        r = await client.post(
            "/api/v1/internal/events",
            headers=INTERNAL,
            json={**_publish_body(), "user_id": str(uuid4())},
        )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_unknown_email_404(db_session, seeded_user):
    app = _build_internal_events_app(db_session)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        r = await client.post(
            "/api/v1/internal/events",
            headers=INTERNAL,
            json={**_publish_body(), "email": "nobody@example.com"},
        )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_wrong_internal_secret_401(db_session, seeded_user):
    user_id, _, _ = seeded_user
    app = _build_internal_events_app(db_session)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        r = await client.post(
            "/api/v1/internal/events",
            headers={"X-Brandista-Internal-Auth": "wrong"},
            json={**_publish_body(), "user_id": str(user_id)},
        )
    # require_internal_auth returns 401 on mismatch.
    assert r.status_code in (401, 403), r.text


# ---------- payload validation + GDPR ----------


@pytest.mark.asyncio
async def test_extra_field_rejected_with_422(db_session, seeded_user):
    user_id, _, _ = seeded_user
    app = _build_internal_events_app(db_session)
    bad_payload = {**_recovery_payload(), "raw_hrv_ms": 42}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        r = await client.post(
            "/api/v1/internal/events",
            headers=INTERNAL,
            json={**_publish_body(payload=bad_payload), "user_id": str(user_id)},
        )
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_severity_rank_mismatch_rejected_422(db_session, seeded_user):
    user_id, _, _ = seeded_user
    app = _build_internal_events_app(db_session)
    bad_payload = _recovery_payload(severity="significant", rank=1)  # mismatch

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        r = await client.post(
            "/api/v1/internal/events",
            headers=INTERNAL,
            json={**_publish_body(payload=bad_payload), "user_id": str(user_id)},
        )
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_unknown_event_type_400(db_session, seeded_user):
    user_id, _, _ = seeded_user
    app = _build_internal_events_app(db_session)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        r = await client.post(
            "/api/v1/internal/events",
            headers=INTERNAL,
            json={
                **_publish_body(event_type="health.something_new"),
                "user_id": str(user_id),
            },
        )
    assert r.status_code == 400
