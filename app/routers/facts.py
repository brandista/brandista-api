"""Profile facts API — cross-product semantic fact store.

Mounted at /api/v1/profile/facts from app/main.py. Phase 4.2 of the
canonical platform layer. Design:
`docs/superpowers/specs/2026-05-15-phase-4-2-facts-api-design.md`.

Auth: every endpoint requires a v2 canonical JWT
(`get_current_canonical_user`). `user_id` and `org_id` are taken from
the JWT — never from the request body. The JWT `product` claim
(populated by the Phase 4.2 step 1 retrofit) gates writes via the
`source_product` anti-spoof.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import and_, delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.canonical import (
    ALLOWED_PRODUCTS,
    CanonicalUser,
    PRODUCT_UNKNOWN,
)
from app.auth.dependencies import get_current_canonical_user
from app.auth.facts_safety import FactGdprRejection, scan_for_gdpr_violations
from app.db.models import ProfileFact
from app.db.session import get_session
from app.schemas.facts import Fact, FactConfidence, FactCreate, FactList

logger = logging.getLogger(__name__)
router = APIRouter()

#: Confidence ordering for `min_confidence` filtering. higher → lower.
_CONFIDENCE_RANK = {"high": 2, "medium": 1, "low": 0}

#: Products allowed to write `safety`-scope facts at `confidence=high`.
#: Continuity is the only product whose safety claims carry the medical
#: provenance to be acted on directly. Other products may still write
#: safety-scope facts, but only at `confidence=medium` or `low` — they
#: surface as informational tags that Continuity's SBE filter
#: (`min_confidence=high`) ignores by default. This keeps the cross-
#: product information flow open (Veyra's coach can still report a
#: user-stated injury into the safety scope) without overriding a
#: real medical constraint.
_SAFETY_HIGH_CONFIDENCE_WRITERS: frozenset[str] = frozenset({"continuity"})


def _require_known_product(user: CanonicalUser) -> str:
    """Resolve the product the caller is acting as. Refuses writes
    from tokens that don't carry an allowlisted product tag — those
    are tokens minted before the Phase 4.2 step 1 retrofit, or by a
    flow that never set the `X-Brandista-Product` header.

    Raises HTTPException(403) on `PRODUCT_UNKNOWN`. The remediation is
    a fresh sign-in through a flow that does set the header.
    """
    if user.product == PRODUCT_UNKNOWN or user.product not in ALLOWED_PRODUCTS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Token has no product tag — re-authenticate through a "
                "client that sends X-Brandista-Product to obtain a "
                "write-capable token."
            ),
        )
    return user.product


@router.post(
    "",
    response_model=Fact,
    summary="Write or upsert a profile fact",
)
async def create_or_upsert_fact(
    body: FactCreate,
    user: CanonicalUser = Depends(get_current_canonical_user),
    session: AsyncSession = Depends(get_session),
) -> Fact:
    """Write a new fact for the authenticated user, or upsert if
    `(user_id, scope, key)` already exists.

    Authorization rules:
    - The caller's JWT must carry an allowlisted `product` tag (403 if not).
    - `body.source_product` must match the caller's JWT `product` —
      a Veyra token cannot post a fact tagged source_product=continuity.
    - `scope='safety'` writes at `confidence='high'` are restricted to
      products with verified medical provenance (today: Continuity only).
      Other products may write safety-scope facts at medium / low
      confidence; Continuity's SBE filter (`min_confidence=high`) won't
      consume them, but the data is available to other readers and can
      be promoted to high-confidence by a future review flow.

    GDPR boundary (see `app/auth/facts_safety.py`):
    - Dose patterns in the JSON value (e.g. "500 mg") are refused.
    - Raw clinical-diagnosis keys (e.g. `diabetes`, `cancer`) are refused.
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

    if (
        body.scope == "safety"
        and body.confidence == "high"
        and caller_product not in _SAFETY_HIGH_CONFIDENCE_WRITERS
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "high-confidence safety facts may only be written by "
                f"products with verified medical provenance "
                f"({sorted(_SAFETY_HIGH_CONFIDENCE_WRITERS)}). "
                f"'{caller_product}' may still record safety facts at "
                "confidence=medium or confidence=low — Continuity's SBE "
                "filter on min_confidence=high will not consume them, "
                "but other consumers can."
            ),
        )

    # GDPR / Article-9 boundary check on payload shape.
    try:
        scan_for_gdpr_violations(scope=body.scope, key=body.key, value=body.value)
    except FactGdprRejection as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e

    # Upsert pattern: try INSERT, on unique-violation re-SELECT and
    # UPDATE the columns that this caller is allowed to change.
    new_fact = ProfileFact(
        org_id=user.org_id,
        user_id=user.user_id,
        scope=body.scope,
        key=body.key,
        value=body.value,
        source_product=caller_product,
        provenance=body.provenance,
        confidence=body.confidence,
        expires_at=body.expires_at,
    )
    session.add(new_fact)
    try:
        await session.commit()
        await session.refresh(new_fact)
        logger.info(
            "facts: created (user=%s, scope=%s, key=%s, source=%s)",
            user.user_id, body.scope, body.key, caller_product,
        )
        return Fact.model_validate(new_fact)
    except IntegrityError:
        await session.rollback()

    # Row already exists for this (user, scope, key) → upsert.
    existing = (
        await session.execute(
            select(ProfileFact).where(
                and_(
                    ProfileFact.user_id == user.user_id,
                    ProfileFact.scope == body.scope,
                    ProfileFact.key == body.key,
                )
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        # IntegrityError fired but the row vanished — race with a delete?
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="concurrent modification, retry",
        )

    # Anti-clobber: refuse the upsert if a different product owns the row.
    # That's a Phase 4.2+ policy question (do we merge across products?)
    # but for step 2 we default to "owner wins" — only the original
    # writer can overwrite.
    if existing.source_product != caller_product:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"fact already exists for (scope={body.scope}, key={body.key}) "
                f"owned by source_product='{existing.source_product}' — "
                f"caller is '{caller_product}'"
            ),
        )

    existing.value = body.value
    existing.provenance = body.provenance
    existing.confidence = body.confidence
    existing.expires_at = body.expires_at
    await session.commit()
    await session.refresh(existing)
    logger.info(
        "facts: upserted (user=%s, scope=%s, key=%s, source=%s)",
        user.user_id, body.scope, body.key, caller_product,
    )
    return Fact.model_validate(existing)


@router.get(
    "",
    response_model=FactList,
    summary="Read the caller's profile facts",
)
async def list_facts(
    scope: Annotated[str | None, Query(description="Comma-separated scope filter")] = None,
    min_confidence: Annotated[FactConfidence | None, Query()] = None,
    include_expired: Annotated[bool, Query()] = False,
    user: CanonicalUser = Depends(get_current_canonical_user),
    session: AsyncSession = Depends(get_session),
) -> FactList:
    """Return the authenticated user's facts. Read-only — no product
    tag required (a read token without an allowlisted product can
    still pull state)."""
    stmt = select(ProfileFact).where(ProfileFact.user_id == user.user_id)

    if scope:
        scopes = [s.strip() for s in scope.split(",") if s.strip()]
        if scopes:
            stmt = stmt.where(ProfileFact.scope.in_(scopes))

    if min_confidence:
        threshold = _CONFIDENCE_RANK[min_confidence]
        accepted = [k for k, v in _CONFIDENCE_RANK.items() if v >= threshold]
        stmt = stmt.where(ProfileFact.confidence.in_(accepted))

    now = datetime.now(timezone.utc)
    if not include_expired:
        stmt = stmt.where(
            (ProfileFact.expires_at.is_(None)) | (ProfileFact.expires_at > now)
        )

    rows = (await session.execute(stmt)).scalars().all()
    return FactList(
        facts=[Fact.model_validate(r) for r in rows],
        as_of=now,
    )


@router.delete(
    "/{fact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete a single fact (user-initiated)",
)
async def delete_fact(
    fact_id: UUID,
    user: CanonicalUser = Depends(get_current_canonical_user),
    session: AsyncSession = Depends(get_session),
):
    """Delete one fact owned by the requesting user. Returns 204 on
    success; 404 if the fact_id is not the caller's (the response
    does not distinguish 'fact does not exist' from 'fact belongs to
    a different user' — both leak the same information)."""
    existing = (
        await session.execute(
            select(ProfileFact).where(
                and_(
                    ProfileFact.id == fact_id,
                    ProfileFact.user_id == user.user_id,
                )
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    await session.delete(existing)
    await session.commit()
    logger.info(
        "facts: deleted (user=%s, fact_id=%s)", user.user_id, fact_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "",
    summary="Bulk delete all facts written by a given source_product",
)
async def bulk_delete_facts_by_source_product(
    source_product: Annotated[str, Query(min_length=2, max_length=64)],
    user: CanonicalUser = Depends(get_current_canonical_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, int]:
    """Bulk-delete all facts the caller has written via a specific
    product — used when the user revokes that product's access.

    Authorization rules:
    - The caller's JWT must carry an allowlisted `product` tag (403
      otherwise) — read-only `PRODUCT_UNKNOWN` tokens can't bulk-delete.
    - `source_product` must equal the caller's `product` claim. A Veyra
      token cannot delete Continuity-owned facts; if it could, a
      compromised Veyra session would let an attacker wipe a user's
      safety constraints.

    Admin / platform-level cross-product cleanup is a separate (future)
    endpoint with its own role check; this endpoint is for the per-
    product revocation path only. Scoped to caller's `user_id`.
    """
    caller_product = _require_known_product(user)
    if source_product != caller_product:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"cannot bulk-delete facts owned by source_product="
                f"'{source_product}' from a '{caller_product}' token"
            ),
        )

    result = await session.execute(
        delete(ProfileFact).where(
            and_(
                ProfileFact.user_id == user.user_id,
                ProfileFact.source_product == source_product,
            )
        )
    )
    await session.commit()
    deleted = result.rowcount or 0
    logger.info(
        "facts: bulk-deleted (user=%s, source_product=%s, count=%d)",
        user.user_id, source_product, deleted,
    )
    return {"deleted": deleted}
