"""FastAPI dependency for the canonical v2 JWT.

This is the v2 counterpart to legacy `get_current_user` in main.py and
in app/dependencies.py. They are independent: each decodes its own
token shape. Endpoints opt in by importing whichever they need.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.canonical import CanonicalTokenError, CanonicalUser, decode_canonical_token

_security = HTTPBearer()


async def get_current_canonical_user(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
) -> CanonicalUser:
    """Validate a canonical v2 JWT and return the user.

    Returns 401 (via HTTPException) on any failure: bad signature,
    expired, missing claim, malformed UUID, malformed email. The
    detail string comes from CanonicalTokenError and never includes
    token contents.
    """
    try:
        return decode_canonical_token(credentials.credentials)
    except CanonicalTokenError as e:
        raise HTTPException(status_code=401, detail=str(e))
