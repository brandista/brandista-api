"""HMAC envelope signing — tamper-check on transport.

In v1 `BRANDISTA_EVENT_SIGNING_SECRET` resolves to the same value as
`BRANDISTA_INTERNAL_SECRET` (see spec §7). The signature catches
in-flight bit-flips, mis-routing, and replay of a stale body against a
new `event_id` — it is **not** defence-in-depth against secret
compromise; a leaked secret breaks both transport auth and envelope
signing together.

Signing string (canonical, byte-exact — see spec §7):

    event_id "|" event_seq "|" event_type "|" event_version "|"
    user_id "|" occurred_at_iso8601 "|" sha256_hex(canonical_payload_json)
"""
from __future__ import annotations

import hmac as _hmac
import os
from datetime import datetime, timezone
from hashlib import sha256
from uuid import UUID

from app.events.canonical_json import canonical_payload_json, sha256_hex


class EnvelopeSignatureError(Exception):
    """Raised by `verify_envelope` when the HMAC doesn't match.

    The router and the subscriber library both raise this; the audit
    layer logs `signature_invalid` and the request is treated as a
    handler failure (retry counter increments).
    """


_SECRET_ENV_VAR = "BRANDISTA_EVENT_SIGNING_SECRET"


def _load_secret() -> bytes:
    """Resolve the signing secret at call time.

    Resolution order:
      1. `BRANDISTA_EVENT_SIGNING_SECRET` (allows future per-region or
         per-subscriber key splits without code change).
      2. `BRANDISTA_INTERNAL_SECRET` (v1 default — same value as the
         internal-auth secret).

    Fail-loud if neither is set. Matches the Phase 4.2 internal-facts
    pattern: a misconfigured production never silently accepts unsigned
    or weakly-signed events.
    """
    secret = os.environ.get(_SECRET_ENV_VAR) or os.environ.get(
        "BRANDISTA_INTERNAL_SECRET"
    )
    if not secret:
        raise RuntimeError(
            f"{_SECRET_ENV_VAR} (or BRANDISTA_INTERNAL_SECRET fallback) "
            f"is not configured; event-bus refuses to sign or verify."
        )
    return secret.encode("utf-8")


def build_signing_message(
    *,
    event_id: UUID,
    event_seq: int,
    event_type: str,
    event_version: int,
    user_id: UUID,
    occurred_at: datetime,
    payload: object,
) -> bytes:
    """Assemble the canonical signing string per spec §7."""
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=timezone.utc)
    occurred_iso = (
        occurred_at.astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )
    payload_hex = sha256_hex(canonical_payload_json(payload))
    parts = [
        str(event_id),
        str(event_seq),
        event_type,
        str(event_version),
        str(user_id),
        occurred_iso,
        payload_hex,
    ]
    return "|".join(parts).encode("utf-8")


def sign_envelope(
    *,
    event_id: UUID,
    event_seq: int,
    event_type: str,
    event_version: int,
    user_id: UUID,
    occurred_at: datetime,
    payload: object,
) -> bytes:
    """Return the HMAC-SHA256 of the canonical signing string."""
    message = build_signing_message(
        event_id=event_id,
        event_seq=event_seq,
        event_type=event_type,
        event_version=event_version,
        user_id=user_id,
        occurred_at=occurred_at,
        payload=payload,
    )
    return _hmac.new(_load_secret(), message, sha256).digest()


def verify_envelope(
    *,
    event_id: UUID,
    event_seq: int,
    event_type: str,
    event_version: int,
    user_id: UUID,
    occurred_at: datetime,
    payload: object,
    envelope_sig: bytes,
) -> None:
    """Raise EnvelopeSignatureError if the signature doesn't match.

    Constant-time comparison via `hmac.compare_digest`. Callers should
    treat any exception here as "this event must not be processed" —
    the audit row records `signature_invalid` and the retry counter
    advances.
    """
    expected = sign_envelope(
        event_id=event_id,
        event_seq=event_seq,
        event_type=event_type,
        event_version=event_version,
        user_id=user_id,
        occurred_at=occurred_at,
        payload=payload,
    )
    if not _hmac.compare_digest(expected, envelope_sig):
        raise EnvelopeSignatureError("envelope_signature_mismatch")
