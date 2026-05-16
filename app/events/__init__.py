"""Cross-product event bus — Phase 4.3.

Pull-based event ledger, not a broker. The `events` table is itself a
persistent log; subscribers pull cursor-paginated over the
`event_seq BIGSERIAL` cursor. See

  docs/superpowers/specs/2026-05-16-phase-4-3-event-bus-design-v0-2.md

for the full design. This package owns the pieces a producer or
subscriber writes against — Pydantic payload schemas, canonical-JSON
serialisation, HMAC envelope signing, GDPR scan, type registry, and
the wire envelope shape.

The HTTP routing lives in `app/routers/events.py`; the SQLAlchemy
models in `app/db/models.py`; the DDL in
`migrations/versions/0007_event_bus.py`.
"""
from app.events.canonical_json import canonical_payload_json, sha256_hex
from app.events.envelope import EventEnvelope
from app.events.hmac import EnvelopeSignatureError, sign_envelope, verify_envelope
from app.events.registry import (
    EventTypeNotRegisteredError,
    PayloadValidationError,
    get_payload_schema,
    known_event_types,
    summarize_payload,
    validate_payload,
)
from app.events.safety import EventGdprRejection, scan_payload_for_gdpr_violations

__all__ = [
    "EnvelopeSignatureError",
    "EventEnvelope",
    "EventGdprRejection",
    "EventTypeNotRegisteredError",
    "PayloadValidationError",
    "canonical_payload_json",
    "get_payload_schema",
    "known_event_types",
    "scan_payload_for_gdpr_violations",
    "sha256_hex",
    "sign_envelope",
    "summarize_payload",
    "validate_payload",
    "verify_envelope",
]
