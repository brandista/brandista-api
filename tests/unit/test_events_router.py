"""Integration tests for the Phase 4.3 event-bus router.

DB-touching tests that exercise the producer/subscriber roundtrip
against a real Postgres (docker-compose service `postgres` on
localhost:5433). Requires migration 0007 already applied — boot:

    cd infra && docker compose up -d postgres
    DATABASE_URL=postgresql://brandista:dev@localhost:5433/brandista \\
        alembic upgrade head

Tests locked here mirror the §11 validation scenarios:
- W2: idempotency match → 200
- W3: idempotency payload mismatch → 409
- R1 (partial): producer → GET → ack roundtrip
- R2: checkpoint persists across "restart" (fresh session)
- F-prefix: subscriber-filter / registry rejections (S3/S4)
- A1: cursor_rewind_refused
- A2: cursor_overshoot_refused
- S1: Pydantic extra=forbid → 422
- S2: anti-spoof source_product mismatch → 403
- GDPR: dose pattern in title → 400
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
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


# ---------- env defaults that several modules expect at import time ----------

os.environ.setdefault("BRANDISTA_INTERNAL_SECRET", "test-internal-secret")
os.environ.setdefault("SECRET_KEY", "test-jwt-secret")


# ---------- DB fixtures ----------


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
    # NullPool: connections aren't reused across tests so the asyncpg
    # event-loop binding never crosses fixture boundaries — avoids the
    # MissingGreenlet error that pool_pre_ping triggers on a reused
    # connection whose original loop has been torn down.
    engine = create_async_engine(dsn, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session_maker(db_engine):
    """A maker so test code AND the FastAPI dependency override can
    each open their own short-lived session against the same engine."""
    return async_sessionmaker(
        db_engine, expire_on_commit=False, class_=AsyncSession
    )


@pytest_asyncio.fixture
async def db_session(session_maker):
    """Fresh AsyncSession used by test bodies for direct verification.
    Truncates everything that can hold per-test state; preserves the
    `event_subscribers` migration seed."""
    async with session_maker() as session:
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
                "entitlements, credits, profile_facts, users, organizations "
                "RESTART IDENTITY CASCADE"
            )
        )
        await session.commit()
        yield session


@pytest_asyncio.fixture
async def seeded_user(db_session: AsyncSession):
    """Create an organization + user via direct SQL — sidesteps the
    Google/Apple auth flow. Returns (user_id, org_id, email)."""
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


# ---------- App + token fixtures ----------


def _build_events_test_app(db_session: AsyncSession) -> FastAPI:
    """Mount the events router and override `get_session` to yield the
    test's already-open session. Same trick auth_v2 tests use via
    `_OneShotSessionMaker` — sharing the session keeps every request in
    the test's event loop, sidestepping the MissingGreenlet that pops
    up when an async engine spawns a fresh connection from inside a
    request handler in this test setup.
    """
    from app.db.session import get_session
    from app.routers.events import router as events_router

    app = FastAPI()
    app.include_router(events_router, prefix="/api/v1/events", tags=["events"])

    async def _override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = _override_get_session
    return app


def _veyra_token(user_id: uuid.UUID, org_id: uuid.UUID, email: str) -> str:
    from app.auth.canonical import create_canonical_token

    return create_canonical_token(
        user_id=user_id, org_id=org_id, email=email, role="user", product="veyra"
    )


def _continuity_token(user_id: uuid.UUID, org_id: uuid.UUID, email: str) -> str:
    from app.auth.canonical import create_canonical_token

    return create_canonical_token(
        user_id=user_id, org_id=org_id, email=email, role="user", product="continuity"
    )


def _unknown_product_token(
    user_id: uuid.UUID, org_id: uuid.UUID, email: str
) -> str:
    from app.auth.canonical import create_canonical_token

    return create_canonical_token(
        user_id=user_id, org_id=org_id, email=email, role="user"
    )


def _workout_scheduled_payload(**overrides) -> dict:
    base = {
        "starts_at": "2026-05-16T18:00:00Z",
        "ends_at": "2026-05-16T18:45:00Z",
        "intensity": "sopiva",
        "title": "Zone 2 polkupyörä",
        "duration_descriptor": "45 min",
        "equipment_summary": [],
    }
    base.update(overrides)
    return base


def _publish_body(**overrides) -> dict:
    base = {
        "event_type": "workout.scheduled",
        "event_version": 1,
        "source_product": "veyra",
        "occurred_at": "2026-05-16T15:00:00Z",
        "idempotency_key": "veyra:workout_unit_test_1:scheduled",
        "payload": _workout_scheduled_payload(),
    }
    base.update(overrides)
    return base


INTERNAL = {"X-Brandista-Internal-Auth": "test-internal-secret"}


# ---------- §11 W1: producer happy path ----------


@pytest.mark.asyncio
async def test_w1_publish_happy_path(db_session, session_maker, seeded_user):
    user_id, org_id, email = seeded_user
    app = _build_events_test_app(db_session)
    token = _veyra_token(user_id, org_id, email)
    headers = {"Authorization": f"Bearer {token}"}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        r = await client.post("/api/v1/events", headers=headers, json=_publish_body())

    assert r.status_code == 201, r.text
    body = r.json()
    assert body["idempotent"] is False
    assert body["event_seq"] >= 1
    assert len(body["envelope_sig_hex"]) == 64

    # workout_starts_at / workout_ends_at populated by the router from
    # the validated payload.
    row = (
        await db_session.execute(
            text(
                "SELECT workout_starts_at, workout_ends_at, severity_rank "
                "FROM events WHERE event_id = :eid"
            ),
            {"eid": body["event_id"]},
        )
    ).one()
    assert row[0] is not None
    assert row[1] is not None
    assert row[2] is None

    # Audit row written.
    audit_count = (
        await db_session.execute(
            text(
                "SELECT count(*) FROM event_audit WHERE event_id = :eid"
            ),
            {"eid": body["event_id"]},
        )
    ).scalar_one()
    assert audit_count == 1


# ---------- §11 W2 + W3: idempotency match / mismatch ----------


@pytest.mark.asyncio
async def test_w2_idempotency_match_returns_200(db_session, session_maker, seeded_user):
    user_id, org_id, email = seeded_user
    app = _build_events_test_app(db_session)
    token = _veyra_token(user_id, org_id, email)
    headers = {"Authorization": f"Bearer {token}"}
    body = _publish_body()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        first = await client.post("/api/v1/events", headers=headers, json=body)
        second = await client.post("/api/v1/events", headers=headers, json=body)

    assert first.status_code == 201
    assert second.status_code == 200, second.text
    assert second.json()["idempotent"] is True
    assert second.json()["event_id"] == first.json()["event_id"]

    # Only one row in events.
    count = (
        await db_session.execute(text("SELECT count(*) FROM events"))
    ).scalar_one()
    assert count == 1


@pytest.mark.asyncio
async def test_w3_idempotency_payload_mismatch_returns_409(db_session, session_maker, seeded_user):
    user_id, org_id, email = seeded_user
    app = _build_events_test_app(db_session)
    token = _veyra_token(user_id, org_id, email)
    headers = {"Authorization": f"Bearer {token}"}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        first = await client.post("/api/v1/events", headers=headers, json=_publish_body())
        second = await client.post(
            "/api/v1/events",
            headers=headers,
            json=_publish_body(
                payload=_workout_scheduled_payload(intensity="raskas")
            ),
        )

    assert first.status_code == 201
    assert second.status_code == 409, second.text
    assert "idempotency_payload_mismatch" in second.text


# ---------- §11 R1 + R2: GET + ack roundtrip + restart-resume ----------


@pytest.mark.asyncio
async def test_r1_subscriber_pull_and_ack_roundtrip(db_session, session_maker, seeded_user):
    user_id, org_id, email = seeded_user
    app = _build_events_test_app(db_session)
    token = _veyra_token(user_id, org_id, email)
    headers = {"Authorization": f"Bearer {token}"}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        publish = await client.post(
            "/api/v1/events", headers=headers, json=_publish_body()
        )
        assert publish.status_code == 201
        published_seq = publish.json()["event_seq"]

        # Subscriber pull.
        pull = await client.get(
            "/api/v1/events",
            headers=INTERNAL,
            params={
                "subscriber_id": "continuity-sbe-pipeline",
                "user_id": str(user_id),
            },
        )
        assert pull.status_code == 200, pull.text
        body = pull.json()
        assert len(body["events"]) == 1
        assert body["events"][0]["event_seq"] == published_seq
        assert body["next_event_seq"] is None  # only one page

        # Ack.
        ack = await client.post(
            "/api/v1/events/ack",
            headers=INTERNAL,
            json={
                "subscriber_id": "continuity-sbe-pipeline",
                "user_id": str(user_id),
                "advance_to_event_seq": published_seq,
            },
        )
        assert ack.status_code == 200, ack.text
        assert ack.json()["advanced"] is True

        # Subsequent pull returns nothing (R2-like restart-resume).
        pull2 = await client.get(
            "/api/v1/events",
            headers=INTERNAL,
            params={
                "subscriber_id": "continuity-sbe-pipeline",
                "user_id": str(user_id),
            },
        )
    assert pull2.status_code == 200
    assert pull2.json()["events"] == []


# ---------- §11 S1 / S2 / GDPR ----------


@pytest.mark.asyncio
async def test_s1_extra_field_rejected_with_422(db_session, session_maker, seeded_user):
    user_id, org_id, email = seeded_user
    app = _build_events_test_app(db_session)
    token = _veyra_token(user_id, org_id, email)
    headers = {"Authorization": f"Bearer {token}"}

    bad = _publish_body()
    bad["payload"]["raw_hrv_ms"] = 42

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        r = await client.post("/api/v1/events", headers=headers, json=bad)
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_s2_anti_spoof_source_product_mismatch_403(db_session, session_maker, seeded_user):
    user_id, org_id, email = seeded_user
    app = _build_events_test_app(db_session)
    veyra_token = _veyra_token(user_id, org_id, email)
    headers = {"Authorization": f"Bearer {veyra_token}"}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        r = await client.post(
            "/api/v1/events",
            headers=headers,
            json=_publish_body(source_product="continuity"),
        )
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_product_unknown_token_cannot_publish(db_session, session_maker, seeded_user):
    user_id, org_id, email = seeded_user
    app = _build_events_test_app(db_session)
    token = _unknown_product_token(user_id, org_id, email)
    headers = {"Authorization": f"Bearer {token}"}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        r = await client.post("/api/v1/events", headers=headers, json=_publish_body())
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_gdpr_dose_pattern_rejected_with_400(db_session, session_maker, seeded_user):
    user_id, org_id, email = seeded_user
    app = _build_events_test_app(db_session)
    token = _veyra_token(user_id, org_id, email)
    headers = {"Authorization": f"Bearer {token}"}

    bad = _publish_body()
    bad["payload"]["title"] = "metformin 500 mg ride"

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        r = await client.post("/api/v1/events", headers=headers, json=bad)
    assert r.status_code == 400, r.text
    assert "dose_data_not_allowed" in r.text


# ---------- §11 S3 / S4: subscriber-registry filter ----------


@pytest.mark.asyncio
async def test_s3_subscriber_filter_excludes_unallowed_type(
    db_session, seeded_user
):
    user_id, org_id, email = seeded_user
    app = _build_events_test_app(db_session)
    veyra_token = _veyra_token(user_id, org_id, email)
    continuity_token = _continuity_token(user_id, org_id, email)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        # Continuity publishes a recovery_pressure event.
        rp = await client.post(
            "/api/v1/events",
            headers={"Authorization": f"Bearer {continuity_token}"},
            json={
                "event_type": "health.recovery_pressure",
                "event_version": 1,
                "source_product": "continuity",
                "occurred_at": "2026-05-16T06:14:00Z",
                "idempotency_key": "continuity:rp-1",
                "payload": {
                    "observed_at": "2026-05-16T06:14:00Z",
                    "severity": "significant",
                    "severity_rank": 3,
                    "hrv_drop_pct": -27.0,
                    "contributing_signals": ["hrv_below_baseline"],
                },
            },
        )
        assert rp.status_code == 201, rp.text

        # Veyra publishes a workout event.
        ws = await client.post(
            "/api/v1/events",
            headers={"Authorization": f"Bearer {veyra_token}"},
            json=_publish_body(),
        )
        assert ws.status_code == 201

        # continuity-sbe-pipeline subscriber should see ONLY the workout
        # event, not the recovery_pressure event (not in its allowed
        # event types).
        pull = await client.get(
            "/api/v1/events",
            headers=INTERNAL,
            params={
                "subscriber_id": "continuity-sbe-pipeline",
                "user_id": str(user_id),
            },
        )
    assert pull.status_code == 200
    types = [e["event_type"] for e in pull.json()["events"]]
    assert types == ["workout.scheduled"]


@pytest.mark.asyncio
async def test_s4_unknown_subscriber_404(db_session, session_maker, seeded_user):
    user_id, _, _ = seeded_user
    app = _build_events_test_app(db_session)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        r = await client.get(
            "/api/v1/events",
            headers=INTERNAL,
            params={"subscriber_id": "attacker-bot", "user_id": str(user_id)},
        )
    assert r.status_code == 404


# ---------- §11 A1 / A2: cursor refusals ----------


@pytest.mark.asyncio
async def test_a1_ack_rewind_refused(db_session, session_maker, seeded_user):
    user_id, org_id, email = seeded_user
    app = _build_events_test_app(db_session)
    veyra_token = _veyra_token(user_id, org_id, email)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        pub = await client.post(
            "/api/v1/events",
            headers={"Authorization": f"Bearer {veyra_token}"},
            json=_publish_body(),
        )
        seq = pub.json()["event_seq"]

        ack1 = await client.post(
            "/api/v1/events/ack",
            headers=INTERNAL,
            json={
                "subscriber_id": "continuity-sbe-pipeline",
                "user_id": str(user_id),
                "advance_to_event_seq": seq,
            },
        )
        assert ack1.status_code == 200

        ack_rewind = await client.post(
            "/api/v1/events/ack",
            headers=INTERNAL,
            json={
                "subscriber_id": "continuity-sbe-pipeline",
                "user_id": str(user_id),
                "advance_to_event_seq": seq - 1,
            },
        )
    assert ack_rewind.status_code == 400
    assert "cursor_rewind_refused" in ack_rewind.text


@pytest.mark.asyncio
async def test_a2_ack_overshoot_refused(db_session, session_maker, seeded_user):
    user_id, org_id, email = seeded_user
    app = _build_events_test_app(db_session)
    veyra_token = _veyra_token(user_id, org_id, email)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        pub = await client.post(
            "/api/v1/events",
            headers={"Authorization": f"Bearer {veyra_token}"},
            json=_publish_body(),
        )
        seq = pub.json()["event_seq"]

        ack_overshoot = await client.post(
            "/api/v1/events/ack",
            headers=INTERNAL,
            json={
                "subscriber_id": "continuity-sbe-pipeline",
                "user_id": str(user_id),
                "advance_to_event_seq": seq + 999_999,
            },
        )
    assert ack_overshoot.status_code == 400, ack_overshoot.text
    assert "cursor_overshoot_refused" in ack_overshoot.text
    body = ack_overshoot.json()
    # Detail body echoes the cap so the caller can correct.
    assert body["detail"]["max_eligible_event_seq"] == seq
