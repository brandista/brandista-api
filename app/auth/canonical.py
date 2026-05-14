"""Canonical platform JWT primitives.

This module owns the v2 token contract end-to-end: model, encode, decode,
and DB-side provisioning. Endpoints in app/routers/auth_v2.py are thin
wrappers that call helpers here.

Token shape (per spec §4):
    {
      "sub":    "<user-uuid>",
      "email":  "<email>",
      "org_id": "<org-uuid>",
      "role":   "<role>",
      "jti":    "<random-uuid>",
      "iat":    <unix-ts>,
      "exp":    <unix-ts>
    }
"""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from pydantic import BaseModel, EmailStr

from agents.config import ACCESS_TOKEN_EXPIRE_MINUTES, ALGORITHM, SECRET_KEY


class CanonicalTokenError(Exception):
    """Raised by decode_canonical_token when a token is rejected.

    Messages never include token contents — only the reason the token
    was rejected ("expired", "missing claim 'org_id'", etc.). This lets
    get_current_canonical_user surface the reason in the 401 detail
    without leaking JWT material to logs or clients.
    """


class CanonicalUser(BaseModel):
    """Validated decoded form of a v2 JWT.

    Used both as the return type of decode_canonical_token and as the
    response model for GET /api/auth/v2/me. EmailStr enforces RFC 5321
    shape on the email claim.
    """

    user_id: UUID
    org_id: UUID
    email: EmailStr
    role: str


def create_canonical_token(
    *,
    user_id: UUID,
    org_id: UUID,
    email: str,
    role: str,
) -> str:
    """Encode a v2 platform JWT for the given user.

    Pure function — does not touch the database. Caller is responsible
    for having already verified the user exists and resolved their org.

    Expiry is ACCESS_TOKEN_EXPIRE_MINUTES from issuance, identical to
    legacy tokens (currently 24h). HS256, signed with shared SECRET_KEY.

    Every token gets a fresh `jti` (UUID) so that a future Redis blocklist
    can revoke individual tokens without re-issuing. The blocklist itself
    is out of scope for step 3.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "org_id": str(org_id),
        "role": role,
        "jti": str(_uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)).timestamp()),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
