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
