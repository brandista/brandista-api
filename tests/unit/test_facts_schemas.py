"""Pydantic-schema tests for the profile facts API.

These tests describe the wire contract: what shapes are accepted on
POST, what gets rejected, what comes back on GET. They're separate
from `test_facts_safety.py` (GDPR / Article-9 defensive scan) and
from the DB-touching router tests (out of scope here — would require
docker-compose Postgres).
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.facts import FactCreate


def _base_payload(**overrides) -> dict:
    base = {
        "scope": "training",
        "key": "available_equipment",
        "value": {"items": ["dumbbells_20kg_pair"]},
        "source_product": "veyra",
        "provenance": "user_stated",
        "confidence": "high",
    }
    base.update(overrides)
    return base


# ---------- scope ----------

def test_accepts_each_valid_scope():
    for scope in ("safety", "nutrition", "training", "general"):
        FactCreate(**_base_payload(scope=scope))


def test_rejects_unknown_scope():
    with pytest.raises(ValidationError) as exc:
        FactCreate(**_base_payload(scope="medical"))
    assert "scope" in str(exc.value)


# ---------- key ----------

def test_accepts_lowercase_snake_case_key():
    FactCreate(**_base_payload(key="cervical_spine_no_impact"))
    FactCreate(**_base_payload(key="a1_b2_c3"))


def test_rejects_uppercase_key():
    with pytest.raises(ValidationError) as exc:
        FactCreate(**_base_payload(key="Cervical_Spine"))
    assert "snake_case" in str(exc.value)


def test_rejects_kebab_case_key():
    with pytest.raises(ValidationError):
        FactCreate(**_base_payload(key="cervical-spine"))


def test_rejects_key_starting_with_digit():
    with pytest.raises(ValidationError):
        FactCreate(**_base_payload(key="1stkey"))


def test_rejects_key_starting_or_ending_with_underscore():
    with pytest.raises(ValidationError):
        FactCreate(**_base_payload(key="_leading"))
    with pytest.raises(ValidationError):
        FactCreate(**_base_payload(key="trailing_"))


def test_rejects_overly_long_key():
    # 120 chars max enforced by Field(max_length=120) AND the pattern;
    # we test the explicit limit. The pattern itself caps at 120 too.
    too_long = "a" + ("_b" * 60)  # 121 chars
    with pytest.raises(ValidationError):
        FactCreate(**_base_payload(key=too_long))


def test_rejects_empty_key():
    with pytest.raises(ValidationError):
        FactCreate(**_base_payload(key=""))


# ---------- provenance ----------

def test_accepts_each_valid_provenance():
    for prov in ("user_stated", "extracted", "inferred"):
        FactCreate(**_base_payload(provenance=prov))


def test_rejects_unknown_provenance():
    with pytest.raises(ValidationError):
        FactCreate(**_base_payload(provenance="guessed"))


# ---------- confidence ----------

def test_accepts_each_valid_confidence():
    for c in ("high", "medium", "low"):
        FactCreate(**_base_payload(confidence=c))


def test_rejects_unknown_confidence():
    with pytest.raises(ValidationError):
        FactCreate(**_base_payload(confidence="medium-high"))


# ---------- value ----------

def test_value_must_be_object_not_array():
    """The schema says value is a JSON object, not a bare array or
    scalar. This keeps producers from accidentally shipping
    primitives that consumers don't know how to interpret."""
    with pytest.raises(ValidationError):
        FactCreate(**_base_payload(value=["array", "not", "object"]))
    with pytest.raises(ValidationError):
        FactCreate(**_base_payload(value="bare string"))
    with pytest.raises(ValidationError):
        FactCreate(**_base_payload(value=42))


def test_empty_value_object_is_acceptable():
    """An empty {} is allowed — useful for boolean-only facts where
    the key itself is the signal. Consumers can layer their own
    requirements per (scope, key)."""
    FactCreate(**_base_payload(value={}))


# ---------- source_product ----------

def test_requires_source_product():
    payload = _base_payload()
    del payload["source_product"]
    with pytest.raises(ValidationError) as exc:
        FactCreate(**payload)
    assert "source_product" in str(exc.value)


def test_source_product_accepts_any_string_within_length():
    """The schema doesn't enforce source_product against
    ALLOWED_PRODUCTS — the ROUTER does that, against the caller's
    JWT. The schema only enforces a length range so callers can't
    smuggle in megabyte-strings."""
    FactCreate(**_base_payload(source_product="continuity"))
    FactCreate(**_base_payload(source_product="any_string_works_here"))


# ---------- extra fields ----------

def test_rejects_extra_fields():
    """The schema has model_config = ConfigDict(extra='forbid') so a
    caller can't sneak in unexpected fields (e.g. user_id, org_id)
    hoping the router blindly trusts them."""
    payload = _base_payload(user_id="11111111-1111-1111-1111-111111111111")
    with pytest.raises(ValidationError) as exc:
        FactCreate(**payload)
    assert "user_id" in str(exc.value).lower() or "extra" in str(exc.value).lower()


# ---------- expires_at ----------

def test_expires_at_defaults_to_none():
    """Most facts are indefinite. Callers don't need to set expires_at
    unless they specifically have a time-bound constraint."""
    fact = FactCreate(**_base_payload())
    assert fact.expires_at is None


# ---------- _require_known_product ----------

def _make_canonical_user(product: str):
    from uuid import uuid4
    from app.auth.canonical import CanonicalUser

    return CanonicalUser(
        user_id=uuid4(),
        org_id=uuid4(),
        email="user@example.com",
        role="user",
        product=product,
    )


def test_require_known_product_returns_allowlisted_product():
    from app.routers.facts import _require_known_product

    user = _make_canonical_user("veyra")
    assert _require_known_product(user) == "veyra"


def test_require_known_product_rejects_unknown_sentinel():
    """Token without an allowlisted product tag (e.g. minted before the
    Phase 4.2 step 1 retrofit) must be refused with 403 — the facts
    API never accepts writes from product=unknown tokens."""
    from fastapi import HTTPException

    from app.auth.canonical import PRODUCT_UNKNOWN
    from app.routers.facts import _require_known_product

    user = _make_canonical_user(PRODUCT_UNKNOWN)
    with pytest.raises(HTTPException) as exc:
        _require_known_product(user)
    assert exc.value.status_code == 403


def test_require_known_product_rejects_forged_value():
    """Defense-in-depth: even if a token somehow carried a non-
    allowlisted product string (e.g. forgery against a compromised
    SECRET_KEY), the router must still refuse. decode_canonical_token
    already collapses unknown values to PRODUCT_UNKNOWN, but the
    router doesn't rely on that — it re-checks here."""
    from fastapi import HTTPException

    from app.routers.facts import _require_known_product

    # We deliberately construct a user with a value that's NOT in
    # ALLOWED_PRODUCTS. CanonicalUser accepts any string in the
    # `product` field at the schema layer — the runtime check belongs
    # to the router.
    user = _make_canonical_user("attacker_corp")
    with pytest.raises(HTTPException) as exc:
        _require_known_product(user)
    assert exc.value.status_code == 403
