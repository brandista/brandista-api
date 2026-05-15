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

import json as _json
import logging
import os
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


#: Products allowed to be encoded into the canonical JWT `product`
#: claim. The claim is server-derived from the `X-Brandista-Product`
#: header at issuance time — products cannot inject it themselves on
#: token use. Anything outside this set falls back to `unknown`, which
#: facts API write endpoints reject (see Phase 4.2 spec §6).
ALLOWED_PRODUCTS: frozenset[str] = frozenset(
    {
        "veyra",
        "continuity",
        "growth_engine",
        "kirjanpito",
        "jobscout",
        "bemufix",
    }
)

#: Sentinel for tokens issued without a recognized product header.
#: Allowed for read-only flows; write flows on the facts API check
#: against this explicitly.
PRODUCT_UNKNOWN = "unknown"


def normalize_product(raw: str | None) -> str:
    """Map a candidate product-name string to the canonical product tag
    stored in the JWT. Unknown values, empty, or None all collapse to
    `PRODUCT_UNKNOWN`. Case- and whitespace-insensitive.

    This is the validator used after audience-based resolution — never
    on its own as a trust boundary. Audience is the trust boundary
    because Google/Apple cryptographically validate it; a request
    header is not.
    """
    if not raw:
        return PRODUCT_UNKNOWN
    candidate = raw.strip().lower()
    return candidate if candidate in ALLOWED_PRODUCTS else PRODUCT_UNKNOWN


def product_from_audience(aud: str | None) -> str:
    """Resolve a verified token `aud` claim (Google client_id or Apple
    bundle id) to a canonical product tag via the env-configured
    `PRODUCT_AUDIENCE_MAP`.

    The audience is the **trust boundary**: Google and Apple
    cryptographically validate that the bearer is in fact a client
    of that audience. brandista-api can therefore trust that a token
    carrying `aud=<veyran ios client id>` was issued for Veyra's
    iOS app and not, say, forged by a Continuity user who set an
    HTTP header.

    Env var: `PRODUCT_AUDIENCE_MAP` is a JSON object mapping audience
    strings to product names, e.g.

        {
          "1015-...veyra.googleusercontent.com": "veyra",
          "1015-...continuity.googleusercontent.com": "continuity",
          "eu.brandista.veyra": "veyra"
        }

    Unmapped audiences fall back to `PRODUCT_UNKNOWN` (read-only
    on the facts API). Empty / missing env means "no audiences are
    mapped", i.e. every token gets PRODUCT_UNKNOWN — operationally
    obvious enough to spot in deploy.
    """
    if not aud or not isinstance(aud, str):
        return PRODUCT_UNKNOWN
    mapping = _load_product_audience_map()
    candidate = mapping.get(aud.strip())
    if not candidate:
        return PRODUCT_UNKNOWN
    # Run the env-map value through the same normalizer as the
    # (no-longer-used) header path. Operator typos like "Veyra" or
    # "veyra " in PRODUCT_AUDIENCE_MAP shouldn't downgrade legitimate
    # users to PRODUCT_UNKNOWN — they should land on the canonical tag.
    # Strings outside ALLOWED_PRODUCTS still collapse to PRODUCT_UNKNOWN.
    return normalize_product(candidate)


_PRODUCT_AUDIENCE_MAP_CACHE: dict[str, str] | None = None


def _load_product_audience_map() -> dict[str, str]:
    """Read + cache `PRODUCT_AUDIENCE_MAP` from env. Parsed once per
    process; tests can reset the cache by clearing this module-level
    via `reset_product_audience_map_cache`.

    A malformed JSON env value logs an error and falls back to {} —
    every token then resolves to PRODUCT_UNKNOWN, which is the safe
    failure mode (refuses writes rather than silently overgranting).
    """
    global _PRODUCT_AUDIENCE_MAP_CACHE
    if _PRODUCT_AUDIENCE_MAP_CACHE is not None:
        return _PRODUCT_AUDIENCE_MAP_CACHE

    raw = os.getenv("PRODUCT_AUDIENCE_MAP", "").strip()
    if not raw:
        _PRODUCT_AUDIENCE_MAP_CACHE = {}
        return _PRODUCT_AUDIENCE_MAP_CACHE

    try:
        parsed = _json.loads(raw)
    except _json.JSONDecodeError as e:
        logger.error(
            "PRODUCT_AUDIENCE_MAP env is not valid JSON; treating as empty. %s", e
        )
        _PRODUCT_AUDIENCE_MAP_CACHE = {}
        return _PRODUCT_AUDIENCE_MAP_CACHE

    if not isinstance(parsed, dict):
        logger.error(
            "PRODUCT_AUDIENCE_MAP env must be a JSON object; got %s",
            type(parsed).__name__,
        )
        _PRODUCT_AUDIENCE_MAP_CACHE = {}
        return _PRODUCT_AUDIENCE_MAP_CACHE

    _PRODUCT_AUDIENCE_MAP_CACHE = {
        str(k): str(v) for k, v in parsed.items() if isinstance(v, str)
    }
    return _PRODUCT_AUDIENCE_MAP_CACHE


def reset_product_audience_map_cache() -> None:
    """Test helper. Clears the parsed env cache so a test can change
    `PRODUCT_AUDIENCE_MAP` between cases."""
    global _PRODUCT_AUDIENCE_MAP_CACHE
    _PRODUCT_AUDIENCE_MAP_CACHE = None


class CanonicalUser(BaseModel):
    """Validated decoded form of a v2 JWT.

    Used both as the return type of decode_canonical_token and as the
    response model for GET /api/auth/v2/me. EmailStr enforces RFC 5321
    shape on the email claim.

    `product` identifies which Brandista product issued this token —
    set at issuance time from the `X-Brandista-Product` header against
    `ALLOWED_PRODUCTS`. Used by the Phase 4.2 facts API to anti-spoof
    `source_product` writes. Tokens issued before this claim was added
    decode with `product=unknown` for backward compatibility.
    """

    user_id: UUID
    org_id: UUID
    email: EmailStr
    role: str
    product: str = PRODUCT_UNKNOWN


def create_canonical_token(
    *,
    user_id: UUID,
    org_id: UUID,
    email: str,
    role: str,
    product: str = PRODUCT_UNKNOWN,
) -> str:
    """Encode a v2 platform JWT for the given user.

    Pure function — does not touch the database. Caller is responsible
    for having already verified the user exists and resolved their org.

    Expiry is ACCESS_TOKEN_EXPIRE_MINUTES from issuance, identical to
    legacy tokens (currently 24h). HS256, signed with shared SECRET_KEY.

    Every token gets a fresh `jti` (UUID) so that a future Redis blocklist
    can revoke individual tokens without re-issuing. The blocklist itself
    is out of scope for step 3.

    `product` is the canonical product tag from `normalize_product()`.
    Defaults to `PRODUCT_UNKNOWN` so callers that don't (yet) thread the
    header through get a backward-compatible token; facts API write
    endpoints will refuse those.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "org_id": str(org_id),
        "role": role,
        "product": product,
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

    # `product` is intentionally NOT in _REQUIRED_CLAIMS — tokens issued
    # before this retrofit lack it and must still validate. Fall back to
    # PRODUCT_UNKNOWN, which behaves as read-only for the facts API.
    product = claims.get("product")
    if not isinstance(product, str) or product not in ALLOWED_PRODUCTS:
        product = PRODUCT_UNKNOWN

    try:
        return CanonicalUser(
            user_id=user_id,
            org_id=org_id,
            email=claims["email"],
            role=claims["role"],
            product=product,
        )
    except _PydanticValidationError as e:
        # Surfacing the field name is fine; the value would leak token contents.
        fields = ", ".join(err["loc"][0] for err in e.errors())
        raise CanonicalTokenError(f"invalid claim shape: {fields}") from e


def _session_maker_for_provision():
    """Indirection point so tests can swap in their own session maker
    without monkey-patching get_session_maker globally."""
    return get_session_maker()


async def provision_canonical_user(
    *,
    email: str,
    source: str,
    google_id: str | None = None,
    apple_id: str | None = None,
) -> User:
    """Resolve or create the canonical user + org + credits +
    growth_engine entitlement for a verified email. Single transaction.

    Lookup order (each is short-circuiting):
      1. `apple_id` match — Apple's `sub` is the only stable identifier
         when the email is a private relay that can rotate.
      2. `google_id` match — same role as apple_id for Google sign-in.
      3. `email` match — for both the legacy admin/super seeded rows
         and for cross-provider account linking (sign in with Google
         once, then with Apple on the same email → same canonical row).
      4. None — create a fresh user + org + credits + entitlement.

    When a user is resolved by email (case 3) and they have no
    `google_id` / `apple_id` recorded yet, the provider tag is
    backfilled so the next sign-in takes the fast path.

    Idempotent under race: if another request creates the user between
    our SELECT and INSERT, the unique(email) constraint fires and we
    re-query to return whoever won.

    source: 'google' | 'apple' | 'magic_link' — used in the log line
            emitted on successful provisioning.
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

        # 1. apple_id match
        if apple_id:
            existing = (
                await session.execute(select(User).where(User.apple_id == apple_id))
            ).scalar_one_or_none()
            if existing is not None:
                return existing

        # 2. google_id match
        if google_id:
            existing = (
                await session.execute(select(User).where(User.google_id == google_id))
            ).scalar_one_or_none()
            if existing is not None:
                return existing

        # 3. email match — possibly backfill missing provider tag
        existing = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if existing is not None:
            backfilled = False
            if apple_id and not existing.apple_id:
                existing.apple_id = apple_id
                backfilled = True
            if google_id and not existing.google_id:
                existing.google_id = google_id
                backfilled = True
            if backfilled:
                try:
                    async with _txn():
                        session.add(existing)
                    await session.refresh(existing)
                    logger.info(
                        f"auth-v2: backfilled provider tag for {email} (source={source})"
                    )
                except IntegrityError:
                    # Concurrent backfill won the unique race — another
                    # request set the same apple_id / google_id on a row
                    # first. Roll back, re-query by the provider tag we
                    # tried to write; if that resolves, return it (the
                    # other request landed on the same row). Otherwise
                    # the other request landed on a different row that
                    # happens to share this email — fall back to email
                    # lookup.
                    await session.rollback()
                    if apple_id:
                        winner = (
                            await session.execute(
                                select(User).where(User.apple_id == apple_id)
                            )
                        ).scalar_one_or_none()
                        if winner is not None:
                            return winner
                    if google_id:
                        winner = (
                            await session.execute(
                                select(User).where(User.google_id == google_id)
                            )
                        ).scalar_one_or_none()
                        if winner is not None:
                            return winner
                    return (
                        await session.execute(select(User).where(User.email == email))
                    ).scalar_one()
            return existing

        # 4. create
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
                    google_id=google_id,
                    apple_id=apple_id,
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
