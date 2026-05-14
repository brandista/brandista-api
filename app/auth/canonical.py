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

import logging
import uuid as _uuid
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from pydantic import BaseModel, EmailStr
from pydantic import ValidationError as _PydanticValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from agents.config import ACCESS_TOKEN_EXPIRE_MINUTES, ALGORITHM, SECRET_KEY
from app.db.models import Credits, Entitlement, Organization, User
from app.db.session import get_session_maker

logger = logging.getLogger(__name__)


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


_REQUIRED_CLAIMS = ("sub", "email", "org_id", "role", "jti", "iat", "exp")


def decode_canonical_token(token: str) -> CanonicalUser:
    """Validate a v2 platform JWT and return the decoded CanonicalUser.

    Rejects (CanonicalTokenError):
      - Bad signature, expired, or otherwise malformed JWT.
      - Any missing required claim from _REQUIRED_CLAIMS.
      - Non-UUID 'sub' or 'org_id'.
      - 'email' that does not pass EmailStr validation.

    Does not touch the database — the token is self-contained.
    """
    try:
        claims = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as e:
        raise CanonicalTokenError("token expired") from e
    except jwt.InvalidTokenError as e:
        raise CanonicalTokenError("invalid token") from e

    missing = [c for c in _REQUIRED_CLAIMS if c not in claims]
    if missing:
        raise CanonicalTokenError(f"missing required claim(s): {', '.join(missing)}")

    try:
        user_id = UUID(claims["sub"])
    except (ValueError, TypeError) as e:
        raise CanonicalTokenError("'sub' is not a valid UUID") from e

    try:
        org_id = UUID(claims["org_id"])
    except (ValueError, TypeError) as e:
        raise CanonicalTokenError("'org_id' is not a valid UUID") from e

    try:
        return CanonicalUser(
            user_id=user_id,
            org_id=org_id,
            email=claims["email"],
            role=claims["role"],
        )
    except _PydanticValidationError as e:
        # Surfacing the field name is fine; the value would leak token contents.
        fields = ", ".join(err["loc"][0] for err in e.errors())
        raise CanonicalTokenError(f"invalid claim shape: {fields}") from e


def _session_maker_for_provision():
    """Indirection point so tests can swap in their own session maker
    without monkey-patching get_session_maker globally."""
    return get_session_maker()


async def provision_canonical_user(*, email: str, source: str) -> User:
    """Create canonical user + org + credits + growth_engine entitlement
    for a verified email. Single transaction.

    Idempotent under race: if another request creates the user between
    our SELECT and INSERT, the unique(email) constraint fires and we
    re-query to return whoever won.

    source: 'google' | 'magic_link' — used only in the log line emitted
            on successful provisioning. Not stored on any row today.
    """
    email = email.lower().strip()
    maker = _session_maker_for_provision()
    async with maker() as session:
        # Pick the right transaction primitive based on whether we own
        # the session (production: fresh, no autobegun txn → begin())
        # or share it with a caller (tests: outer txn already open →
        # begin_nested() = SAVEPOINT, so we still get atomicity without
        # double-begin).
        def _txn():
            return session.begin_nested() if session.in_transaction() else session.begin()

        existing = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        try:
            async with _txn():
                org = Organization(name=email)
                session.add(org)
                await session.flush()

                user = User(
                    email=email,
                    org_id=org.id,
                    is_active=True,
                    role="user",
                )
                session.add(user)
                await session.flush()

                session.add(Credits(org_id=org.id, balance=0, plan_monthly_limit=0))
                session.add(Entitlement(org_id=org.id, module="growth_engine"))
            await session.refresh(user)
            logger.info(f"auth-v2: provisioned canonical user {email} (source={source})")
            return user
        except IntegrityError:
            # Race: someone else won the INSERT. Re-query and return theirs.
            await session.rollback()
            return (
                await session.execute(select(User).where(User.email == email))
            ).scalar_one()
