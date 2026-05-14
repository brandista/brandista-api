"""Canonical platform auth endpoints (v2).

Mounted at /api/auth/v2/* from main.py. Coexists with legacy /auth/*
endpoints — they share SECRET_KEY but issue and accept different token
shapes. See docs/superpowers/specs/2026-05-14-canonical-auth-v2-design.md.
"""
from __future__ import annotations

import logging
import os
import time
from urllib.parse import quote

from authlib.integrations.base_client.errors import MismatchingStateError, OAuthError
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, EmailStr

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


def _issue_v2_token_for(user_row, *, source: str) -> V2TokenResponse:
    """Build the v2 token response for a freshly-provisioned (or
    resolved) canonical user. Centralized so /google/native and
    /magic-link/verify can't drift on claim ordering, log format,
    or response shape.

    source: short label appearing in the issuance log line.
    """
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
    logger.info(f"auth-v2 {source}: issued v2 token for {user_row.email}")
    return V2TokenResponse(access_token=token, user=canonical_user)


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
    return _issue_v2_token_for(user_row, source="google/native")


class MagicLinkRequestBody(BaseModel):
    email: EmailStr


class MagicLinkRequestResponse(BaseModel):
    status: str  # always "sent"


def _get_magic_link_auth():
    """Pull the already-initialized magic_link_auth singleton from main.py.

    Indirection so tests can swap it out. main.py initializes
    magic_link_auth at startup (main.py:1671); we use whatever it
    holds today. May be None if Redis/SMTP are not configured —
    in which case the endpoint silently no-ops and returns 'sent'.
    """
    try:
        import main  # type: ignore[import-not-found]

        return getattr(main, "magic_link_auth", None)
    except Exception:  # noqa: BLE001 — main may not be importable in some test setups
        return None


@router.post(
    "/magic-link/request",
    response_model=MagicLinkRequestResponse,
    summary="Request a magic link email",
)
async def magic_link_request(
    body: MagicLinkRequestBody,
    request: Request,
    background_tasks: BackgroundTasks,
) -> MagicLinkRequestResponse:
    """Send a magic-link email to the given address.

    Delegates to the existing magic_link_auth subsystem (auth_magic_link.py)
    which handles rate-limiting, token storage, and email send. The
    response is always `{"status": "sent"}` regardless of whether the
    email exists — same anti-enumeration behavior as the legacy endpoint.
    """
    email = body.email.lower().strip()
    mla = _get_magic_link_auth()
    if mla is None:
        logger.warning("auth-v2 magic-link/request: magic_link_auth not configured")
        return MagicLinkRequestResponse(status="sent")

    try:
        await mla.send_magic_link(
            email=email,
            request=request,
            background_tasks=background_tasks,
        )
    except HTTPException:
        # Rate-limit hits (429) etc. — let them propagate to the client
        # because the legacy endpoint does the same.
        raise
    except Exception as e:  # noqa: BLE001
        logger.error(f"auth-v2 magic-link/request: send failed for {email}: {e}")
        # Still return 'sent' so we don't reveal whether the email is registered
    return MagicLinkRequestResponse(status="sent")


class MagicLinkVerifyBody(BaseModel):
    token: str


@router.post(
    "/magic-link/verify",
    response_model=V2TokenResponse,
    summary="Verify magic link → canonical v2 token",
)
async def magic_link_verify(
    body: MagicLinkVerifyBody, request: Request
) -> V2TokenResponse:
    """Verify a magic-link single-use token and issue a v2 JWT.

    Ports legacy GET /auth/magic-link/verify (main.py:6874) — but as POST
    with a JSON body because the call is server-to-server XHR from the
    frontend page that the email link redirects to.
    """
    mla = _get_magic_link_auth()
    if mla is None:
        raise HTTPException(status_code=503, detail="Magic link authentication not available")

    result = await mla.verify_magic_link(token=body.token, request=request)
    if not result or not result.get("valid"):
        raise HTTPException(status_code=400, detail="Invalid or expired magic link")

    email = (result.get("user") or {}).get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Invalid magic link response")
    email = email.lower().strip()

    user_row = await provision_canonical_user(email=email, source="magic_link")
    return _issue_v2_token_for(user_row, source="magic-link/verify")


def _get_oauth():
    """Pull the authlib oauth object initialized in app/main.py lifespan.

    Lazy import + getattr keeps this independent of import order and lets
    tests inject a fake via monkeypatch. main.oauth is set to either an
    authlib OAuth instance or None depending on whether GOOGLE_CLIENT_ID /
    GOOGLE_CLIENT_SECRET were set at boot.
    """
    try:
        import main  # type: ignore[import-not-found]

        return getattr(main, "oauth", None)
    except Exception:  # noqa: BLE001 — main may not be importable in some test setups
        return None


@router.get(
    "/google/login",
    summary="Begin Google OAuth flow → redirect to Google",
)
async def google_login(request: Request) -> RedirectResponse:
    """Initiate the server-side Google OAuth login flow.

    Web frontend redirects browser here (window.location.href = ...).
    We redirect to Google's consent screen; Google redirects back to
    /api/auth/v2/google/callback with an authorization code.

    Mirrors legacy /auth/google/login (main.py:6993). Differences:
      - Redirect URI is the v2 callback path.
      - Caller is expected to be a web client that handles the redirect
        chain. Native mobile clients should use /api/auth/v2/google/native
        (POST id_token) instead.
    """
    oauth = _get_oauth()
    if oauth is None:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")
    if not os.getenv("GOOGLE_CLIENT_ID"):
        raise HTTPException(status_code=503, detail="GOOGLE_CLIENT_ID not set")

    # The redirect URI Google sends the user back to. Must be whitelisted in
    # Google Cloud Console for the OAuth client. Env override allows separate
    # dev/staging targets.
    redirect_uri = os.getenv(
        "GOOGLE_V2_REDIRECT_URI",
        "https://api.brandista.eu/api/auth/v2/google/callback",
    )

    logger.info(f"auth-v2 google/login: redirecting to Google with redirect_uri={redirect_uri}")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get(
    "/google/callback",
    summary="Handle Google OAuth callback → issue v2 token + redirect to frontend",
)
async def google_callback(request: Request) -> RedirectResponse:
    """Handle the Google OAuth redirect: exchange the authorization code
    for user info, auto-provision the canonical user, issue a v2 JWT,
    and redirect the browser to the frontend dashboard with the token
    in the URL hash fragment.

    URL fragment shape (must stay identical to legacy /auth/google/callback
    for frontend compatibility):
        #token=<jwt>&email=<email>&username=<email-local-part>&role=<role>

    Ports legacy main.py:7027 onto canonical schema + v2 token shape.
    """
    oauth = _get_oauth()
    if oauth is None:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")

    try:
        token = await oauth.google.authorize_access_token(request)
    except (OAuthError, MismatchingStateError) as e:
        logger.warning(f"auth-v2 google/callback: client-side auth error: {e}")
        raise HTTPException(status_code=400, detail="Google authorization failed")
    except Exception as e:  # noqa: BLE001 — transport/server errors from Google
        logger.error(f"auth-v2 google/callback: token exchange transport error: {e}")
        raise HTTPException(status_code=502, detail="Google authorization failed")

    user_info = token.get("userinfo") or {}
    email = (user_info.get("email") or "").lower().strip()
    if not email or not user_info.get("email_verified", False):
        raise HTTPException(status_code=400, detail="Google email not verified")

    user_row = await provision_canonical_user(email=email, source="google_callback")
    jwt_token = create_canonical_token(
        user_id=user_row.id,
        org_id=user_row.org_id,
        email=user_row.email,
        role=user_row.role,
    )

    # Build the frontend redirect — fragment shape matches legacy so the
    # frontend's hash handler keeps working unchanged.
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")
    username = email.split("@")[0]
    timestamp = int(time.time())
    redirect_url = (
        f"{frontend_url}/dashboard?t={timestamp}"
        f"#token={quote(jwt_token, safe='')}"
        f"&email={quote(email, safe='')}"
        f"&username={quote(username, safe='')}"
        f"&role={quote(user_row.role, safe='')}"
    )
    logger.info(f"auth-v2 google/callback: issued v2 token for {email}, redirecting to frontend")
    return RedirectResponse(url=redirect_url, status_code=302)
