"""Apple Sign In identity-token verification.

Apple issues RS256 JWTs signed with rotating keys published at
`https://appleid.apple.com/auth/keys`. This module fetches and caches
that JWK set, picks the right key by the token header's `kid`, and
validates issuer / audience / expiry.

Differences vs Google:
  - Algorithm is RS256 (Google ID tokens also support RS256 but our
    Google flow uses the google-auth library which abstracts it; here
    we go direct via python-jose because pip-installing a separate
    apple-auth library for one issuer is overkill).
  - `email` claim may be omitted (when the user hides the email on a
    return sign-in) — the client must forward what it has from the
    initial sign-in.
  - `email_verified` may be the **string** 'true' / 'false', not a
    boolean — Apple is inconsistent.
  - `is_private_email` indicates a relay address (rotates if the user
    toggles email forwarding off and back on, hence why we store
    `apple_id` separately).

The JWK set is cached in-process with a 1-hour TTL. Apple has stated
key-rotation cadence is months (not minutes), so an hour is comfortable
and keeps us from hammering their endpoint. A `kid` miss triggers a
forced refresh in case the token references a freshly rolled key.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTError

logger = logging.getLogger(__name__)

APPLE_ISSUER = "https://appleid.apple.com"
APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
_JWKS_TTL_SECONDS = 3600

_cache: dict[str, Any] = {"keys": None, "fetched_at": 0.0}


class AppleVerificationError(Exception):
    """Apple identity-token verification failure. Raised with a short,
    log-safe message; never includes Apple's internal claim values."""


def _fetch_jwks(force: bool = False) -> list[dict]:
    now = time.time()
    if (
        not force
        and _cache["keys"] is not None
        and (now - _cache["fetched_at"]) < _JWKS_TTL_SECONDS
    ):
        return _cache["keys"]

    try:
        response = httpx.get(APPLE_JWKS_URL, timeout=5.0)
        response.raise_for_status()
        body = response.json()
    except httpx.HTTPError as e:
        raise AppleVerificationError(f"Apple JWKS fetch failed: {type(e).__name__}") from e
    except ValueError as e:
        raise AppleVerificationError("Apple JWKS response not JSON") from e

    keys = body.get("keys")
    if not isinstance(keys, list) or not keys:
        raise AppleVerificationError("Apple JWKS response missing 'keys'")

    _cache["keys"] = keys
    _cache["fetched_at"] = now
    return keys


def _find_key(kid: str, allow_refresh: bool = True) -> dict | None:
    for key in _fetch_jwks():
        if key.get("kid") == kid:
            return key
    if allow_refresh:
        # `kid` not in the cached set — Apple may have rotated. Refresh
        # once and retry; if still missing, the token is bad.
        for key in _fetch_jwks(force=True):
            if key.get("kid") == kid:
                return key
    return None


def verify_apple_identity_token(
    identity_token: str, *, audiences: list[str]
) -> dict:
    """Validate an Apple identity token. Returns the verified claims dict.

    `audiences` is the list of acceptable values for the `aud` claim —
    one entry per Brandista product that uses Apple Sign In (Veyra
    iOS, Continuity iOS, etc.). Each iOS app's Apple bundle id (or the
    Service ID for web flows) is its own audience.

    Raises AppleVerificationError on any verification failure. The error
    message is short and log-safe — it never embeds Apple's internal
    claim contents (`sub`, raw `email`, etc.).
    """
    try:
        unverified_header = jwt.get_unverified_header(identity_token)
    except JWTError as e:
        raise AppleVerificationError(f"Apple token header unparseable: {e}") from e

    kid = unverified_header.get("kid")
    if not kid or not isinstance(kid, str):
        raise AppleVerificationError("Apple token missing 'kid' header")

    alg = unverified_header.get("alg")
    if alg != "RS256":
        # Apple has historically only ever issued RS256. If they ever
        # rotate to a new algorithm we want to fail loudly rather than
        # silently accept it.
        raise AppleVerificationError(f"Apple token unexpected alg: {alg}")

    key = _find_key(kid)
    if key is None:
        raise AppleVerificationError("Apple JWKS does not contain matching 'kid'")

    # python-jose's jwt.decode only accepts a single string for the
    # `audience` parameter — not a list. To support multiple Brandista
    # products on one Apple endpoint, we validate `aud` manually after
    # the signature/issuer/expiry pass.
    try:
        claims = jwt.decode(
            identity_token,
            key,
            algorithms=["RS256"],
            audience=None,
            issuer=APPLE_ISSUER,
            options={"verify_aud": False},
        )
    except ExpiredSignatureError as e:
        raise AppleVerificationError("Apple token expired") from e
    except JWTError as e:
        # Issuer / signature mismatch — single category for the caller;
        # the underlying message stays in the log.
        logger.warning(f"auth-v2 apple: token rejected: {e}")
        raise AppleVerificationError("Apple token signature/issuer mismatch") from e

    aud_claim = claims.get("aud")
    if isinstance(aud_claim, str):
        token_audiences = [aud_claim]
    elif isinstance(aud_claim, list) and all(isinstance(a, str) for a in aud_claim):
        token_audiences = aud_claim
    else:
        raise AppleVerificationError("Apple token 'aud' missing or malformed")

    if not any(a in audiences for a in token_audiences):
        # Don't echo the rejected audience back — log it, return generic.
        logger.warning(
            f"auth-v2 apple: aud mismatch (got={token_audiences}, accept={audiences})"
        )
        raise AppleVerificationError("Apple token audience mismatch")

    return claims


def coerce_apple_bool(value: Any) -> bool:
    """Apple sometimes returns boolean claims as the strings 'true' /
    'false' instead of true booleans. Normalize."""
    return value is True or value == "true"
