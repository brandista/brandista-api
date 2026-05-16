"""Internal (server-to-server) event-publish endpoint.

Mounted at `/api/v1/internal/events`. Sibling to the canonical-JWT
`POST /api/v1/events` — same validation pipeline (registry, Pydantic
schema, GDPR scan, idempotency, envelope signing, audit row), but the
caller authenticates with `X-Brandista-Internal-Auth` rather than a
user JWT.

Why this exists: Continuity-api's SBE pipeline runs server-side and
has no per-user JWT for brandista-api. It DOES have its own local
identity for the user, and a shared HS256 secret for verifying inbound
canonical tokens — but minting a brandista canonical token would need
the canonical user_id (which Continuity doesn't store) and the org_id
(same). The server-to-server channel sidesteps both: the internal
caller passes the user_id explicitly (or an email that resolves to
one), and `source_product` is constrained to a small allowlist of
trusted server-side publishers.

Trust model (v1):

- `X-Brandista-Internal-Auth` must match `BRANDISTA_INTERNAL_SECRET`.
  Same secret as `internal_facts` (constant-time compared).
- `source_product` MUST be in `_INTERNAL_PUBLISHER_ALLOWLIST` —
  refuses anything outside `{"continuity"}` for now. Veyra-side
  publishes still flow through the canonical-JWT path.
- A leaked secret can publish any allowlisted event-type as the
  allowlisted source for any user. Spec §15 documents the v2 path
  (per-subscriber signed credentials) — not in v1.

Everything downstream of the auth + source_product check is identical
to the user-route handler in `app/routers/events.py`. The two paths
share the post-validate code path via a private helper so the
envelope-signing + idempotency logic stays in one place.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.internal import require_internal_auth
from app.db.models import Event, EventAudit, User
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
from app.events.registry import hot_path_columns, requires_gdpr_scan

logger = logging.getLogger(__name__)
router = APIRouter()


# Products that may publish via the internal-secret channel. Veyra is
# deliberately absent — it has a user JWT and uses the canonical path.
# Continuity is the only v1 entry. New entries are a deliberate
# operational action: add here + bump the changelog + redeploy.
_INTERNAL_PUBLISHER_ALLOWLIST: frozenset[str] = frozenset({"continuity"})


class InternalEventPublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str = Field(min_length=1, max_length=64)
    event_version: int = Field(default=1, ge=1, le=255)
    source_product: str = Field(min_length=1, max_length=64)
    occurred_at: datetime
    idempotency_key: str | None = Field(default=None, max_length=255)
    payload: dict[str, Any]
    # Exactly one of these identifies the user. `user_id` is preferred
    # when the caller has cached the canonical UUID; `email` is the
    # natural-key fallback for Continuity, which only stores email
    # locally and resolves to user_id through the same mechanism the
    # internal-facts endpoint already uses.
    user_id: UUID | None = Field(default=None)
    email: str | None = Field(default=None, min_length=1, max_length=320)


class InternalEventPublishResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    event_seq: int
    envelope_sig_hex: str
    idempotent: bool
    # Echoes the resolved canonical user_id so the caller (Continuity)
    # can cache it locally and skip the email lookup next time.
    resolved_user_id: UUID


@router.post(
    "",
    response_model=InternalEventPublishResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Publish a cross-product event (server-to-server)",
    dependencies=[Depends(require_internal_auth)],
)
async def publish_event_internal(
    body: InternalEventPublishRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> InternalEventPublishResponse:
    """Validate, sign, and persist an event from a trusted server-side
    publisher. Mirrors the canonical-JWT POST handler except for the
    identity resolution + source-product allowlist.
    """
    # Source-product allowlist — server-to-server callers can't claim
    # to be Veyra (Veyra has its own canonical-JWT path).
    if body.source_product not in _INTERNAL_PUBLISHER_ALLOWLIST:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"source_product='{body.source_product}' is not in the "
                f"internal publisher allowlist "
                f"{sorted(_INTERNAL_PUBLISHER_ALLOWLIST)}; use the user-JWT "
                "POST /api/v1/events path instead."
            ),
        )

    # Exactly-one identity hint, matches the internal facts pattern.
    if (body.user_id is None) == (body.email is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="exactly one of user_id or email must be provided",
        )

    resolved_user_id: UUID
    resolved_org_id: UUID
    if body.user_id is not None:
        row = (
            await session.execute(
                select(User).where(User.id == body.user_id)
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="user not found for given user_id",
            )
        resolved_user_id = row.id
        resolved_org_id = row.org_id
    else:
        normalized = (body.email or "").strip().lower()
        row = (
            await session.execute(
                select(User).where(User.email == normalized)
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="user not found for given email",
            )
        resolved_user_id = row.id
        resolved_org_id = row.org_id

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

    if requires_gdpr_scan(body.event_type):
        try:
            scan_payload_for_gdpr_violations(model.model_dump(mode="json"))
        except EventGdprRejection as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc

    payload_json = model.model_dump(mode="json")
    event_id = uuid4()
    event_seq_row = await session.execute(select(func.nextval("events_event_seq_seq")))
    event_seq = int(event_seq_row.scalar_one())

    envelope_sig = sign_envelope(
        event_id=event_id,
        event_seq=event_seq,
        event_type=body.event_type,
        event_version=body.event_version,
        user_id=resolved_user_id,
        occurred_at=body.occurred_at,
        payload=payload_json,
    )

    hot = hot_path_columns(body.event_type, model)

    row_new = Event(
        event_id=event_id,
        event_seq=event_seq,
        event_type=body.event_type,
        event_version=body.event_version,
        user_id=resolved_user_id,
        org_id=resolved_org_id,
        source_product=body.source_product,
        idempotency_key=body.idempotency_key,
        occurred_at=body.occurred_at,
        payload=payload_json,
        envelope_sig=envelope_sig,
        workout_starts_at=hot.workout_starts_at,
        workout_ends_at=hot.workout_ends_at,
        severity_rank=hot.severity_rank,
    )

    savepoint = await session.begin_nested()
    session.add(row_new)
    try:
        await session.flush()
        savepoint_committed = True
    except IntegrityError as exc:
        # Only collapse to the idempotency-dedup branch on the
        # specific per-(source_product, event_type, user_id,
        # idempotency_key) constraint. Any other IntegrityError (FK
        # breakage, NOT NULL trip, future constraint additions)
        # propagates — `concurrent_modification_retry` would be the
        # wrong story.
        from app.routers.events import _is_idempotency_violation
        if not _is_idempotency_violation(exc):
            await savepoint.rollback()
            raise
        await savepoint.rollback()
        savepoint_committed = False

    if savepoint_committed:
        audit = EventAudit(
            event_id=event_id,
            event_seq_at_audit=event_seq,
            event_type=body.event_type,
            source_product=body.source_product,
            user_id=resolved_user_id,
            org_id=resolved_org_id,
            payload_summary=_jsonify(summarize_payload(body.event_type, model)),
            actor_kind="producer",
            actor_id=body.source_product,
            action="published",
            actor_meta={"channel": "internal"},
        )
        session.add(audit)
        await session.commit()
        logger.info(
            "events: internal-published (event_id=%s, seq=%d, type=%s, source=%s, user=%s)",
            event_id, event_seq, body.event_type, body.source_product, resolved_user_id,
        )
        return InternalEventPublishResponse(
            event_id=event_id,
            event_seq=event_seq,
            envelope_sig_hex=envelope_sig.hex(),
            idempotent=False,
            resolved_user_id=resolved_user_id,
        )

    # Unique violation — SELECT existing, compare canonical payloads.
    existing = (
        await session.execute(
            select(Event).where(
                and_(
                    Event.source_product == body.source_product,
                    Event.event_type == body.event_type,
                    Event.user_id == resolved_user_id,
                    Event.idempotency_key == body.idempotency_key,
                )
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="concurrent_modification_retry",
        )

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

    await session.rollback()
    response.status_code = status.HTTP_200_OK
    logger.info(
        "events: internal idempotent dedup (event_id=%s, seq=%d, type=%s, user=%s)",
        existing_event_id, existing_event_seq, body.event_type, resolved_user_id,
    )
    return InternalEventPublishResponse(
        event_id=existing_event_id,
        event_seq=existing_event_seq,
        envelope_sig_hex=existing_envelope_sig.hex(),
        idempotent=True,
        resolved_user_id=resolved_user_id,
    )


def _jsonify(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, dict):
        return {k: _jsonify(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonify(item) for item in value]
    return value
