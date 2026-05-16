"""Cross-product event bus — POST / GET / ack endpoints.

Mounted at `/api/v1/events` from both `app/main.py` and `main.py` per
the Phase 4.2 dual-mount pattern. Phase 4.3 of the canonical platform.
Full design in
`docs/superpowers/specs/2026-05-16-phase-4-3-event-bus-design-v0-2.md`.

Three endpoints:

- POST `/api/v1/events`            — producer, canonical-JWT auth.
- GET  `/api/v1/events`            — subscriber pull, internal secret.
- POST `/api/v1/events/ack`        — subscriber checkpoint commit,
                                     internal secret, bounded by the
                                     max eligible event_seq.

The POST flow computes `event_id` (uuid4) and `event_seq`
(`SELECT nextval(...)`) *before* INSERT so the envelope signature is
populated in the same statement — see spec §5 step 5 + §7.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.canonical import (
    ALLOWED_PRODUCTS,
    CanonicalUser,
    PRODUCT_UNKNOWN,
)
from app.auth.dependencies import get_current_canonical_user
from app.auth.internal import require_internal_auth
from app.db.models import (
    Event,
    EventAudit,
    EventSubscriber,
    EventSubscriberCheckpoint,
    User,
)
from app.db.session import get_session
from app.events import (
    EventGdprRejection,
    EventTypeNotRegisteredError,
    PayloadValidationError,
    canonical_payload_json,
    scan_payload_for_gdpr_violations,
    sign_envelope,
    summarize_payload,
    validate_payload,
)
from app.events.registry import (
    hot_path_columns,
    requires_gdpr_scan,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class EventPublishRequest(BaseModel):
    """Producer POST body — see spec §5."""

    model_config = ConfigDict(extra="forbid")

    event_type: str = Field(min_length=1, max_length=64)
    event_version: int = Field(default=1, ge=1, le=255)
    source_product: str = Field(min_length=1, max_length=64)
    occurred_at: datetime
    idempotency_key: str | None = Field(default=None, max_length=255)
    payload: dict[str, Any]


class EventPublishResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    event_seq: int
    envelope_sig_hex: str
    idempotent: bool


class EventListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    event_seq: int
    event_type: str
    event_version: int
    user_id: UUID
    org_id: UUID
    source_product: str
    idempotency_key: str | None
    occurred_at: datetime
    received_at: datetime
    payload: dict[str, Any]
    envelope_sig_hex: str


class EventListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: list[EventListItem]
    # True when the subscriber's filter has more events beyond this
    # page. The GET endpoint paginates by checkpoint position; the
    # caller's next pull is a fresh GET (NOT a cursor parameter) —
    # so what matters is just "should I poll again right now?".
    # Document the pattern explicitly: ack the last successfully
    # handled event_seq from this page, then re-pull.
    has_more: bool


class EventAckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subscriber_id: str = Field(min_length=1, max_length=64)
    user_id: UUID
    advance_to_event_seq: int = Field(ge=0)


class EventAckResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subscriber_id: str
    user_id: UUID
    last_processed_event_seq: int
    advanced: bool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_known_product(user: CanonicalUser) -> str:
    if user.product == PRODUCT_UNKNOWN or user.product not in ALLOWED_PRODUCTS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Token has no product tag — re-authenticate through a "
                "client that sends X-Brandista-Product to obtain a "
                "publish-capable token."
            ),
        )
    return user.product


async def _resolve_subscriber(
    session: AsyncSession, subscriber_id: str
) -> EventSubscriber:
    row = (
        await session.execute(
            select(EventSubscriber).where(
                EventSubscriber.subscriber_id == subscriber_id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"subscriber '{subscriber_id}' is not registered",
        )
    return row


# ---------------------------------------------------------------------------
# POST /api/v1/events  — producer
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=EventPublishResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Publish a cross-product event",
)
async def publish_event(
    body: EventPublishRequest,
    response: Response,
    user: CanonicalUser = Depends(get_current_canonical_user),
    session: AsyncSession = Depends(get_session),
) -> EventPublishResponse:
    """Validate, sign, and persist an event.

    Auth: canonical v2 JWT. The token's `product` claim must equal
    `body.source_product` — anti-spoof per the Phase 4.2 audience-
    mapping policy. `PRODUCT_UNKNOWN` tokens cannot publish.

    Idempotency: `(source_product, event_type, user_id, idempotency_key)`
    is UNIQUE. Same key + same canonical payload → 200 with the
    existing row. Same key + different payload → 409
    `idempotency_payload_mismatch`. See spec §8.
    """
    caller_product = _require_known_product(user)

    if body.source_product != caller_product:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"source_product='{body.source_product}' does not match the "
                f"caller's product tag '{caller_product}'."
            ),
        )

    # Schema dispatch + payload validation.
    try:
        model = validate_payload(body.event_type, body.payload)
    except EventTypeNotRegisteredError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown event_type '{body.event_type}'",
        ) from None
    except PayloadValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "payload_validation_failed",
                # include_context=False drops the original exception
                # object out of `ctx`; otherwise model_validator-raised
                # ValueErrors propagate as non-JSON-serialisable refs
                # and FastAPI's response encoder raises TypeError
                # before returning the 422 to the client.
                "errors": exc.inner.errors(include_url=False, include_context=False),
            },
        ) from exc

    # Defensive Art-9 scan on top of `extra="forbid"`.
    if requires_gdpr_scan(body.event_type):
        try:
            scan_payload_for_gdpr_violations(model.model_dump(mode="json"))
        except EventGdprRejection as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc

    payload_json = model.model_dump(mode="json")

    # Pre-INSERT identity + ordering, so envelope_sig is computed and
    # written in the same INSERT — no insert-then-update.
    event_id = uuid4()
    event_seq_row = await session.execute(select(func.nextval("events_event_seq_seq")))
    event_seq = int(event_seq_row.scalar_one())

    envelope_sig = sign_envelope(
        event_id=event_id,
        event_seq=event_seq,
        event_type=body.event_type,
        event_version=body.event_version,
        user_id=user.user_id,
        occurred_at=body.occurred_at,
        payload=payload_json,
    )

    hot = hot_path_columns(body.event_type, model)

    row = Event(
        event_id=event_id,
        event_seq=event_seq,
        event_type=body.event_type,
        event_version=body.event_version,
        user_id=user.user_id,
        org_id=user.org_id,
        source_product=caller_product,
        idempotency_key=body.idempotency_key,
        occurred_at=body.occurred_at,
        payload=payload_json,
        envelope_sig=envelope_sig,
        workout_starts_at=hot.workout_starts_at,
        workout_ends_at=hot.workout_ends_at,
        severity_rank=hot.severity_rank,
    )

    # SAVEPOINT around the INSERT so a unique-violation doesn't poison
    # the outer transaction — the follow-up SELECT and audit-row write
    # must still run. Only collapse to the idempotency path on the
    # specific `uq_events_idempotency` constraint; any other
    # IntegrityError (FK breakage, NOT NULL trip, future constraint
    # additions) should bubble as a 500 rather than silently turn into
    # a misleading `concurrent_modification_retry`.
    savepoint = await session.begin_nested()
    session.add(row)
    try:
        await session.flush()
        savepoint_committed = True
    except IntegrityError as exc:
        if not _is_idempotency_violation(exc):
            await savepoint.rollback()
            raise
        await savepoint.rollback()
        savepoint_committed = False

    if savepoint_committed:
        # New row — write audit, commit, return 201.
        audit = EventAudit(
            event_id=event_id,
            event_seq_at_audit=event_seq,
            event_type=body.event_type,
            source_product=caller_product,
            user_id=user.user_id,
            org_id=user.org_id,
            payload_summary=_jsonify(summarize_payload(body.event_type, model)),
            actor_kind="producer",
            actor_id=caller_product,
            action="published",
        )
        session.add(audit)
        await session.commit()
        logger.info(
            "events: published (event_id=%s, seq=%d, type=%s, source=%s, user=%s)",
            event_id, event_seq, body.event_type, caller_product, user.user_id,
        )
        return EventPublishResponse(
            event_id=event_id,
            event_seq=event_seq,
            envelope_sig_hex=envelope_sig.hex(),
            idempotent=False,
        )

    # Unique violation path — SELECT existing, compare canonical
    # payloads, return 200 or 409.
    existing = (
        await session.execute(
            select(Event).where(
                and_(
                    Event.source_product == caller_product,
                    Event.event_type == body.event_type,
                    Event.user_id == user.user_id,
                    Event.idempotency_key == body.idempotency_key,
                )
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        # Race window: row vanished between the failed INSERT and the
        # follow-up SELECT. Surface as 500 — caller retries.
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="concurrent_modification_retry",
        )

    # Snapshot the columns we need BEFORE rolling back — rollback
    # expires every ORM attribute, and the next access would trigger a
    # refresh-from-DB (lazy load), which is expensive and in async
    # session land fails with MissingGreenlet outside a fresh
    # connection acquire.
    existing_event_id = existing.event_id
    existing_event_seq = existing.event_seq
    existing_payload = existing.payload
    existing_envelope_sig = existing.envelope_sig

    incoming_canonical = canonical_payload_json(payload_json)
    existing_canonical = canonical_payload_json(existing_payload)
    if incoming_canonical != existing_canonical:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="idempotency_payload_mismatch",
        )

    # True idempotent return — same key, same payload. The allocated
    # event_seq is intentionally not used; the sequence advances, the
    # row does not duplicate. Spec §5 step 10: dedup returns 200, not
    # 201 — override the decorator default.
    await session.rollback()
    response.status_code = status.HTTP_200_OK
    logger.info(
        "events: idempotent dedup (event_id=%s, seq=%d, type=%s, user=%s)",
        existing_event_id, existing_event_seq, body.event_type, user.user_id,
    )
    return EventPublishResponse(
        event_id=existing_event_id,
        event_seq=existing_event_seq,
        envelope_sig_hex=existing_envelope_sig.hex(),
        idempotent=True,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/events  — subscriber pull
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=EventListResponse,
    summary="Pull events for a subscriber (server-to-server)",
    dependencies=[Depends(require_internal_auth)],
)
async def list_events(
    subscriber_id: Annotated[str, Query(min_length=1, max_length=64)],
    user_id: Annotated[UUID | None, Query()] = None,
    email: Annotated[str | None, Query(min_length=1, max_length=320)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    session: AsyncSession = Depends(get_session),
) -> EventListResponse:
    """Return events newer than the (subscriber, user) checkpoint that
    match the subscriber's registry filter, ordered by `event_seq`.

    Identity hint: exactly one of `user_id` or `email`. The email
    fallback matches the internal-facts contract — Continuity-side
    callers know only email locally and resolve to user_id server-side.

    Does NOT advance the checkpoint — the caller acks explicitly via
    POST `/ack` after successful handling. The response carries
    `envelope_sig_hex` so subscribers can verify signatures locally.
    """
    if (user_id is None) == (email is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="exactly one of user_id or email must be provided",
        )

    subscriber = await _resolve_subscriber(session, subscriber_id)

    resolved_user_id: UUID
    if user_id is not None:
        resolved_user_id = user_id
    else:
        normalized = (email or "").strip().lower()
        row = (
            await session.execute(
                select(User.id).where(User.email == normalized)
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="user not found for given email",
            )
        resolved_user_id = row

    checkpoint_row = (
        await session.execute(
            select(EventSubscriberCheckpoint).where(
                and_(
                    EventSubscriberCheckpoint.subscriber_id == subscriber_id,
                    EventSubscriberCheckpoint.user_id == resolved_user_id,
                )
            )
        )
    ).scalar_one_or_none()
    last_seq = checkpoint_row.last_processed_event_seq if checkpoint_row else 0

    stmt = (
        select(Event)
        .where(
            Event.user_id == resolved_user_id,
            Event.event_seq > last_seq,
            Event.event_type.in_(subscriber.allowed_event_types),
            Event.source_product.in_(subscriber.allowed_source_products),
        )
        .order_by(Event.event_seq)
        .limit(limit + 1)  # one extra to detect "more pages remain"
    )
    rows = (await session.execute(stmt)).scalars().all()

    has_more = len(rows) > limit
    page = rows[:limit]

    items = [
        EventListItem(
            event_id=r.event_id,
            event_seq=r.event_seq,
            event_type=r.event_type,
            event_version=r.event_version,
            user_id=r.user_id,
            org_id=r.org_id,
            source_product=r.source_product,
            idempotency_key=r.idempotency_key,
            occurred_at=r.occurred_at,
            received_at=r.received_at,
            payload=r.payload,
            envelope_sig_hex=r.envelope_sig.hex(),
        )
        for r in page
    ]
    return EventListResponse(events=items, has_more=has_more)


# ---------------------------------------------------------------------------
# POST /api/v1/events/ack  — checkpoint commit
# ---------------------------------------------------------------------------


@router.post(
    "/ack",
    response_model=EventAckResponse,
    summary="Advance the (subscriber, user) checkpoint",
    dependencies=[Depends(require_internal_auth)],
)
async def ack_events(
    body: EventAckRequest,
    session: AsyncSession = Depends(get_session),
) -> EventAckResponse:
    """Advance the checkpoint to `advance_to_event_seq`.

    Refusals:
    - 404 if subscriber is unknown.
    - 400 `cursor_rewind_refused` if `advance_to_event_seq < current`.
    - 400 `cursor_overshoot_refused` if `advance_to_event_seq` exceeds
      the max `event_seq` the subscriber's filter could have served
      for this user. Body echoes `max_eligible_event_seq` so the
      caller can correct.
    - Equal → 200 idempotent no-op.

    Successful advance writes an `event_audit` row `cursor_advanced`
    carrying both old and new cursor values.
    """
    subscriber = await _resolve_subscriber(session, body.subscriber_id)

    current_row = (
        await session.execute(
            select(EventSubscriberCheckpoint).where(
                and_(
                    EventSubscriberCheckpoint.subscriber_id == body.subscriber_id,
                    EventSubscriberCheckpoint.user_id == body.user_id,
                )
            )
        )
    ).scalar_one_or_none()
    current = current_row.last_processed_event_seq if current_row else 0

    if body.advance_to_event_seq < current:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "cursor_rewind_refused",
                "current": current,
                "requested": body.advance_to_event_seq,
            },
        )

    if body.advance_to_event_seq == current:
        return EventAckResponse(
            subscriber_id=body.subscriber_id,
            user_id=body.user_id,
            last_processed_event_seq=current,
            advanced=False,
        )

    # Overshoot + middle-seq guard: ack must reference a real eligible
    # event_seq the subscriber's filter could have seen for this user,
    # not merely a value `<= max(event_seq)`. Otherwise a caller can
    # ack 15 when the only eligible seqs in the gap are 10 and 20:
    # checkpoint moves to 15 → next pull `event_seq > 15` returns
    # only 20, silently skipping 10.
    eligible_exists = (
        await session.execute(
            select(Event.event_seq).where(
                Event.event_seq == body.advance_to_event_seq,
                Event.user_id == body.user_id,
                Event.event_type.in_(subscriber.allowed_event_types),
                Event.source_product.in_(subscriber.allowed_source_products),
            )
        )
    ).scalar_one_or_none()
    if eligible_exists is None:
        # Compute max_eligible for the 400 body so the caller can correct.
        max_eligible = (
            await session.execute(
                select(func.max(Event.event_seq)).where(
                    Event.user_id == body.user_id,
                    Event.event_type.in_(subscriber.allowed_event_types),
                    Event.source_product.in_(subscriber.allowed_source_products),
                )
            )
        ).scalar_one()
        max_eligible = max_eligible or 0
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": (
                    "cursor_overshoot_refused"
                    if body.advance_to_event_seq > max_eligible
                    else "cursor_unseen_event_seq_refused"
                ),
                "max_eligible_event_seq": max_eligible,
                "requested": body.advance_to_event_seq,
            },
        )

    # UPSERT — first ack for this (subscriber, user) inserts the row.
    if current_row is None:
        new_cp = EventSubscriberCheckpoint(
            subscriber_id=body.subscriber_id,
            user_id=body.user_id,
            last_processed_event_seq=body.advance_to_event_seq,
        )
        session.add(new_cp)
    else:
        current_row.last_processed_event_seq = body.advance_to_event_seq
        current_row.last_processed_at = datetime.now(timezone.utc)

    # Resolve the user's org_id so the denormalised audit row stays
    # joinable in Sprint loppuraportti queries.
    user_org_id = (
        await session.execute(select(User.org_id).where(User.id == body.user_id))
    ).scalar_one_or_none()
    if user_org_id is None:
        # Subscriber sent an unknown user_id. Treat the same as 404 —
        # we never advance a cursor for a non-existent user.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="user_id not found",
        )

    advanced_audit = EventAudit(
        event_id=None,
        event_seq_at_audit=body.advance_to_event_seq,
        event_type="<cursor>",
        source_product="<n/a>",
        user_id=body.user_id,
        org_id=user_org_id,
        payload_summary={"from_seq": current, "to_seq": body.advance_to_event_seq},
        actor_kind="subscriber",
        actor_id=body.subscriber_id,
        action="cursor_advanced",
    )
    session.add(advanced_audit)
    await session.commit()

    logger.info(
        "events: ack (subscriber=%s, user=%s, %d -> %d)",
        body.subscriber_id, body.user_id, current, body.advance_to_event_seq,
    )
    return EventAckResponse(
        subscriber_id=body.subscriber_id,
        user_id=body.user_id,
        last_processed_event_seq=body.advance_to_event_seq,
        advanced=True,
    )


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------


def _is_idempotency_violation(exc: IntegrityError) -> bool:
    """True iff this IntegrityError comes from the per-(source_product,
    event_type, user_id, idempotency_key) unique constraint.

    Used by the producer path to decide whether to collapse the error
    into the idempotency-dedup branch. Any other IntegrityError
    (FK breakage, NOT NULL trip, future constraint additions) should
    propagate — `concurrent_modification_retry` would be the wrong
    response and `idempotency_payload_mismatch` an outright lie.
    """
    # asyncpg surfaces the constraint name on the wrapped error.
    # Defensive: walk both `orig` and `__cause__` chains and look for
    # the constraint name in any error attribute or stringified body.
    targets = {"uq_events_idempotency"}
    for source in (exc.orig, exc.__cause__, exc):
        if source is None:
            continue
        name = getattr(source, "constraint_name", None)
        if isinstance(name, str) and name in targets:
            return True
        for attr in ("diag", "args"):
            value = getattr(source, attr, None)
            if value is None:
                continue
            constraint = getattr(value, "constraint_name", None)
            if isinstance(constraint, str) and constraint in targets:
                return True
        if any(t in str(source) for t in targets):
            return True
    return False


def _jsonify(value: Any) -> Any:
    """Convert datetimes inside a dict/list to ISO-8601 UTC strings
    so the result is JSONB-storable without further coercion."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, dict):
        return {k: _jsonify(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonify(item) for item in value]
    return value
