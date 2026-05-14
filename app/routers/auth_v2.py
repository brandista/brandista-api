"""Canonical platform auth endpoints (v2).

Mounted at /api/auth/v2/* from main.py. Coexists with legacy /auth/*
endpoints — they share SECRET_KEY but issue and accept different token
shapes. See docs/superpowers/specs/2026-05-14-canonical-auth-v2-design.md.
"""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel

from app.auth.canonical import (
    CanonicalUser,
    create_canonical_token,
    provision_canonical_user,
)
from app.auth.dependencies import get_current_canonical_user

logger = logging.getLogger(__name__)

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
        raise HTTPException(status_code=401, detail="invalid Google token")
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
