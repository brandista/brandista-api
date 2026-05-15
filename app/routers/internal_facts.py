"""Internal (server-to-server) read-only facts endpoint.

Mounted at `/api/v1/internal/profile/facts`. Used by Continuity-api's
SBE pipeline to fetch a user's safety facts before computing
`blocked_actions[]`. The pipeline runs in an async background task
that does not have a user JWT — hence the server-to-server path.

Strictly read-only. POST / DELETE are NOT exposed on this prefix.
Writes always go through the canonical-JWT-authenticated user route
in `app/routers/facts.py`. This separation matters: if the internal
secret ever leaks, the blast radius is read-only data exfiltration
(bad but bounded), not arbitrary fact creation under any user's
identity.

Auth is delegated to `app.auth.internal.require_internal_auth`. See
that module for the trust model and fail-loud bootstrap behaviour.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import HTTPException, status

from app.auth.internal import require_internal_auth
from app.db.models import ProfileFact, User
from app.db.session import get_session
from app.routers.facts import _CONFIDENCE_RANK
from app.schemas.facts import Fact, FactConfidence, FactList

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "",
    response_model=FactList,
    summary="Read another user's profile facts (server-to-server, read-only)",
    dependencies=[Depends(require_internal_auth)],
)
async def list_facts_internal(
    user_id: Annotated[UUID | None, Query(description="brandista user_id to read")] = None,
    email: Annotated[str | None, Query(description="email to resolve to user_id (alternative to user_id)")] = None,
    scope: Annotated[str | None, Query(description="Comma-separated scope filter")] = None,
    min_confidence: Annotated[FactConfidence | None, Query()] = None,
    include_expired: Annotated[bool, Query()] = False,
    session: AsyncSession = Depends(get_session),
) -> FactList:
    """Same filter semantics as the user-authenticated GET, but takes
    an explicit identity hint in the query rather than deriving it
    from a JWT.

    Caller passes exactly one of:
    - `user_id` — the brandista canonical user UUID. Preferred when
      the caller already has it cached (e.g. via prior sync).
    - `email` — natural-key alternative for callers that only know
      the user by their address (e.g. continuity-api's pipeline
      task, which has only Continuity's local user_id + email and
      no platform UUID stored locally yet). Resolves to user_id
      server-side via `SELECT users WHERE email = ?`.

    Returns 400 if neither or both supplied, 404 if email doesn't
    resolve.

    Audit: every call logs the queried user_id (always resolved to
    canonical form, regardless of which hint the caller used). The
    read-only constraint bounds the blast radius of a leaked secret
    to data exfiltration.
    """
    if (user_id is None) == (email is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="exactly one of user_id or email must be provided",
        )

    if email is not None:
        normalized = email.strip().lower()
        row = (
            await session.execute(select(User).where(User.email == normalized))
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="user not found for given email",
            )
        user_id = row.id

    stmt = select(ProfileFact).where(ProfileFact.user_id == user_id)

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
    logger.info(
        "internal-facts: read user_id=%s scope=%s min_confidence=%s -> %d rows",
        user_id, scope, min_confidence, len(rows),
    )
    return FactList(
        facts=[Fact.model_validate(r) for r in rows],
        as_of=now,
    )
