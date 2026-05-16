"""HMAC envelope signing + canonical JSON tests (Phase 4.3).

Locks the v0.2 §7 contract: server-side signing string is
byte-exact, signature roundtrips, every tampered field flips the
HMAC, missing secret fails loud.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.events.canonical_json import canonical_payload_json, sha256_hex
from app.events.hmac import (
    EnvelopeSignatureError,
    build_signing_message,
    sign_envelope,
    verify_envelope,
)


@pytest.fixture(autouse=True)
def _signing_secret(monkeypatch):
    monkeypatch.setenv("BRANDISTA_INTERNAL_SECRET", "test-secret-please")
    monkeypatch.delenv("BRANDISTA_EVENT_SIGNING_SECRET", raising=False)
    yield


def _envelope_args(**overrides):
    base = dict(
        event_id=UUID("11111111-1111-1111-1111-111111111111"),
        event_seq=42,
        event_type="workout.scheduled",
        event_version=1,
        user_id=UUID("22222222-2222-2222-2222-222222222222"),
        occurred_at=datetime(2026, 5, 16, 15, 0, tzinfo=timezone.utc),
        payload={"intensity": "sopiva", "title": "Zone 2"},
    )
    base.update(overrides)
    return base


# ---------- canonical JSON ----------


def test_canonical_json_sorts_keys():
    a = canonical_payload_json({"b": 1, "a": 2})
    b = canonical_payload_json({"a": 2, "b": 1})
    assert a == b


def test_canonical_json_no_whitespace():
    out = canonical_payload_json({"a": 1, "b": 2})
    assert b" " not in out


def test_canonical_json_finnish_text_not_escaped():
    out = canonical_payload_json({"title": "polkupyörä"})
    # ensure_ascii=False keeps the ä as UTF-8 byte sequence, not ä.
    assert "polkupyörä".encode("utf-8") in out


def test_canonical_json_handles_datetime():
    out = canonical_payload_json(
        {"observed_at": datetime(2026, 5, 16, 6, 14, tzinfo=timezone.utc)}
    )
    assert b"2026-05-16T06:14:00Z" in out


def test_canonical_json_rejects_naive_unknown_types():
    class Foo:
        pass
    with pytest.raises(TypeError):
        canonical_payload_json({"x": Foo()})


def test_sha256_hex_known_value():
    assert sha256_hex(b"abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


# ---------- signing message ----------


def test_signing_message_uses_pipe_separator_and_iso8601_z():
    msg = build_signing_message(**_envelope_args())
    text = msg.decode("ascii")
    parts = text.split("|")
    assert parts[0] == "11111111-1111-1111-1111-111111111111"
    assert parts[1] == "42"
    assert parts[2] == "workout.scheduled"
    assert parts[3] == "1"
    assert parts[4] == "22222222-2222-2222-2222-222222222222"
    assert parts[5] == "2026-05-16T15:00:00Z"
    # final part is sha256 hex of canonical payload
    assert len(parts[6]) == 64


def test_signing_message_normalises_naive_datetime_to_utc():
    msg = build_signing_message(
        **_envelope_args(occurred_at=datetime(2026, 5, 16, 15, 0))
    )
    assert b"2026-05-16T15:00:00Z" in msg


# ---------- sign / verify ----------


def test_sign_verify_roundtrip():
    args = _envelope_args()
    sig = sign_envelope(**args)
    assert len(sig) == 32  # SHA-256 raw digest
    verify_envelope(**args, envelope_sig=sig)


@pytest.mark.parametrize(
    "tamper",
    [
        {"event_seq": 43},
        {"event_type": "workout.completed"},
        {"event_version": 2},
        {"user_id": uuid4()},
        {"occurred_at": datetime(2026, 5, 16, 15, 1, tzinfo=timezone.utc)},
        {"payload": {"intensity": "raskas", "title": "Zone 2"}},
        {"payload": {"intensity": "sopiva", "title": "Zone 2 ", "extra": True}},
    ],
)
def test_tampering_any_field_breaks_signature(tamper):
    args = _envelope_args()
    sig = sign_envelope(**args)
    with pytest.raises(EnvelopeSignatureError):
        verify_envelope(**{**args, **tamper}, envelope_sig=sig)


def test_missing_secret_fails_loud(monkeypatch):
    monkeypatch.delenv("BRANDISTA_INTERNAL_SECRET", raising=False)
    monkeypatch.delenv("BRANDISTA_EVENT_SIGNING_SECRET", raising=False)
    with pytest.raises(RuntimeError) as exc:
        sign_envelope(**_envelope_args())
    assert "BRANDISTA_EVENT_SIGNING_SECRET" in str(exc.value)


def test_event_signing_secret_overrides_internal_secret(monkeypatch):
    monkeypatch.setenv("BRANDISTA_INTERNAL_SECRET", "internal-only")
    args = _envelope_args()
    sig_internal = sign_envelope(**args)

    monkeypatch.setenv("BRANDISTA_EVENT_SIGNING_SECRET", "event-specific")
    sig_specific = sign_envelope(**args)
    assert sig_internal != sig_specific
