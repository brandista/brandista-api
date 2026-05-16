"""Deterministic JSON for payload comparison and HMAC signing.

The envelope signature includes `sha256_hex(canonical_payload_json)`,
and idempotency-mismatch detection compares the canonical form of an
incoming payload against the stored one. Both rely on byte-identical
output regardless of which subscriber library serialises — so the
canonical form must be deterministic across producer and verifier.

Rules (mirror of spec §7):
- UTF-8 output.
- ASCII-safe escaping disabled (`ensure_ascii=False`) so Finnish
  text doesn't round-trip through `\\u00e4` and compare bytewise
  against an already-decoded form.
- Object keys sorted.
- No insignificant whitespace (separators `,` and `:`).
- `datetime` values rendered as ISO-8601 strings via the caller
  before they reach this module — `json.dumps` cannot serialise
  them on its own.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


def canonical_payload_json(payload: Any) -> bytes:
    """Return the deterministic UTF-8 byte representation of `payload`.

    `payload` is expected to be already JSON-friendly — Pydantic
    `.model_dump(mode='json')` is the producer-side normaliser. If a
    `datetime` slips through anyway it's coerced to ISO-8601 UTC here
    so the signing path never raises on an upstream oversight.
    """
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_default,
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    """Hex-encoded SHA-256 digest. Used in the envelope signing string."""
    return hashlib.sha256(data).hexdigest()


def _default(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    raise TypeError(
        f"Object of type {type(value).__name__} is not JSON-serialisable in "
        f"canonical_payload_json; convert it before signing."
    )
