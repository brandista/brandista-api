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

from app.auth.internal import require_internal_auth
from app.db.models import ProfileFact
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
    user_id: Annotated[UUID, Query(description="user_id to read")],
    scope: Annotated[str | None, Query(description="Comma-separated scope filter")] = None,
    min_confidence: Annotated[FactConfidence | None, Query()] = None,
    include_expired: Annotated[bool, Query()] = False,
    session: AsyncSession = Depends(get_session),
) -> FactList:
    """Same filter semantics as the user-authenticated GET, but takes
    an explicit `user_id` query parameter instead of deriving it from
    a JWT. The caller (Continuity-api today) is responsible for
    passing the correct platform user_id.

    Audit: every call logs the requesting service-secret holder (via
    Railway env attribution) and the queried user_id. Combined with
    the read-only constraint, this lets us trace any internal
    exfiltration to its origin.
    """
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
