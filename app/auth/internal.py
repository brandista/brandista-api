"""Server-to-server authentication for trusted Brandista backends.

Continuity-api (and future internal services) need to read another
user's profile facts without a per-request user JWT — the canonical
flow assumes a logged-in user, but Continuity's `safety/engine.bound()`
runs in an async background task with only the user_id in hand.

Rather than minting fake user JWTs (which would require Continuity to
know every user's org_id and would share a token-issuance capability
across services), we add a small server-to-server channel:

  - `BRANDISTA_INTERNAL_SECRET` env var, shared between brandista-api
    and the calling backend (today: continuity-api).
  - `X-Brandista-Internal-Auth: <secret>` header on the request.
  - Mounted only on read endpoints under `/api/v1/internal/*` — never
    on writes. POSTing facts via this channel would let a compromised
    Continuity write to any user's row; the internal channel is
    deliberately GET-only.
  - Constant-time secret comparison.

Bootstrap fail-loud: if the env is missing the dependency refuses
every request rather than silently allowing them. The deploy mistake
of forgetting to set the secret is loud and immediate, not silent
and exploitable.
"""
from __future__ import annotations

import hmac
import logging
import os

from fastapi import Header, HTTPException, status

logger = logging.getLogger(__name__)


class InternalAuthError(Exception):
    """Raised when an internal-secret header fails validation."""


def require_internal_auth(
    x_brandista_internal_auth: str | None = Header(default=None, alias="X-Brandista-Internal-Auth"),
) -> None:
    """FastAPI dependency that validates the server-to-server secret.

    Status codes intentionally distinguish two failure modes:

    - **503 Service Unavailable** when `BRANDISTA_INTERNAL_SECRET` is
      not configured (or only whitespace). This is a deployment
      misconfiguration, not a caller error — surface it as a
      service-state problem so on-call sees the right signal (the
      endpoint is *unavailable*, not *unauthorised*) and fixes the
      env rather than chasing a credential mismatch.
    - **401 Unauthorized** when the header is missing or the supplied
      value does not match (constant-time comparison).
    """
    expected = os.getenv("BRANDISTA_INTERNAL_SECRET", "").strip()
    if not expected:
        logger.error(
            "internal-auth: BRANDISTA_INTERNAL_SECRET is not configured; "
            "refusing all internal requests"
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="internal auth not configured",
        )
    if not x_brandista_internal_auth:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing X-Brandista-Internal-Auth header",
        )
    # Constant-time comparison to avoid timing oracles on the secret.
    if not hmac.compare_digest(
        x_brandista_internal_auth.strip().encode("utf-8"),
        expected.encode("utf-8"),
    ):
        logger.warning("internal-auth: invalid secret presented")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid internal auth",
        )
