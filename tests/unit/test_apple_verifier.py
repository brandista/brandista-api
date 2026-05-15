"""Unit tests for app.auth.apple — the Apple Sign In identity-token
verifier.

The tests generate a throwaway RSA keypair per session, build a JWK
from it, and stub the module-level cache to serve that JWK instead of
fetching apple's real endpoint. Then they mint Apple-shaped tokens
with the private half and assert the verifier accepts good ones and
rejects all the failure modes we documented.
"""
from __future__ import annotations

import time
from typing import Iterator

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt

from app.auth import apple as apple_mod


_AUDIENCE = "eu.brandista.veyra"
_KID = "TEST_KID_2026_05"


def _new_rsa_keys():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public = private.public_key()
    public_pem = public.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem.decode(), public_pem.decode()


@pytest.fixture(scope="module")
def rsa_keys():
    return _new_rsa_keys()


@pytest.fixture(autouse=True)
def stub_jwks(rsa_keys, monkeypatch) -> Iterator[None]:
    """Make `_fetch_jwks` return the test public key (as a JWK)."""
    from jose import jwk as jose_jwk

    _, public_pem = rsa_keys
    public_jwk = jose_jwk.construct(public_pem, algorithm="RS256").to_dict()
    public_jwk["kid"] = _KID
    public_jwk["alg"] = "RS256"
    public_jwk["use"] = "sig"

    def fake_fetch_jwks(force: bool = False):  # noqa: ARG001
        return [public_jwk]

    monkeypatch.setattr(apple_mod, "_fetch_jwks", fake_fetch_jwks)
    # Reset the module-level cache between tests so a stale entry from
    # an earlier test can't paper over a misconfigured one.
    apple_mod._cache["keys"] = None
    apple_mod._cache["fetched_at"] = 0.0
    yield


def _mint(rsa_keys, claims: dict, *, headers: dict | None = None) -> str:
    private_pem, _ = rsa_keys
    return jwt.encode(
        claims,
        private_pem,
        algorithm="RS256",
        headers={"kid": _KID, **(headers or {})},
    )


def _good_claims() -> dict:
    now = int(time.time())
    return {
        "iss": apple_mod.APPLE_ISSUER,
        "aud": _AUDIENCE,
        "sub": "001234.aabbccddeeff.5678",
        "email": "user@example.com",
        "email_verified": "true",
        "iat": now,
        "exp": now + 600,
    }


def test_good_token_accepted(rsa_keys):
    token = _mint(rsa_keys, _good_claims())
    claims = apple_mod.verify_apple_identity_token(token, audiences=[_AUDIENCE])
    assert claims["sub"] == "001234.aabbccddeeff.5678"
    assert claims["email"] == "user@example.com"


def test_good_token_accepts_first_audience_in_multi_list(rsa_keys):
    """Multi-product setup — Veyra bundle in slot 1, Continuity in slot 2,
    token issued for Veyra → still accepted."""
    token = _mint(rsa_keys, _good_claims())
    claims = apple_mod.verify_apple_identity_token(
        token, audiences=[_AUDIENCE, "eu.brandista.continuity"]
    )
    assert claims["aud"] == _AUDIENCE


def test_wrong_audience_rejected(rsa_keys):
    bad = {**_good_claims(), "aud": "com.evil.app"}
    token = _mint(rsa_keys, bad)
    with pytest.raises(apple_mod.AppleVerificationError) as exc:
        apple_mod.verify_apple_identity_token(token, audiences=[_AUDIENCE])
    assert "audience" in str(exc.value).lower()


def test_wrong_issuer_rejected(rsa_keys):
    bad = {**_good_claims(), "iss": "https://attacker.example/"}
    token = _mint(rsa_keys, bad)
    with pytest.raises(apple_mod.AppleVerificationError) as exc:
        apple_mod.verify_apple_identity_token(token, audiences=[_AUDIENCE])
    assert "issuer" in str(exc.value).lower() or "signature" in str(exc.value).lower()


def test_expired_token_rejected(rsa_keys):
    now = int(time.time())
    bad = {**_good_claims(), "iat": now - 7200, "exp": now - 60}
    token = _mint(rsa_keys, bad)
    with pytest.raises(apple_mod.AppleVerificationError) as exc:
        apple_mod.verify_apple_identity_token(token, audiences=[_AUDIENCE])
    assert "expired" in str(exc.value).lower()


def test_unknown_kid_rejected(rsa_keys):
    token = _mint(rsa_keys, _good_claims(), headers={"kid": "UNKNOWN"})
    with pytest.raises(apple_mod.AppleVerificationError) as exc:
        apple_mod.verify_apple_identity_token(token, audiences=[_AUDIENCE])
    # When kid doesn't match, the module retries with force-refresh; our
    # stub returns the same single key both times, so the result is the
    # "no matching kid" branch.
    assert "kid" in str(exc.value).lower()


def test_non_rs256_alg_rejected(rsa_keys):
    """If Apple ever rotated algorithm we want a loud refuse — not a
    silent accept. A `HS256`-headered token from an attacker who already
    knows our HS256 secret would otherwise sneak through."""
    # We can't actually mint an HS256 token with the RSA private key, so
    # we mint a normal one and rewrite the header. We bypass jose's
    # convenience here because it would re-sign with HS256.
    import base64
    import json

    token = _mint(rsa_keys, _good_claims())
    header_b64, payload_b64, sig_b64 = token.split(".")
    header = json.loads(base64.urlsafe_b64decode(header_b64 + "=="))
    header["alg"] = "HS256"
    bad_header_b64 = (
        base64.urlsafe_b64encode(json.dumps(header).encode()).rstrip(b"=").decode()
    )
    forged = f"{bad_header_b64}.{payload_b64}.{sig_b64}"
    with pytest.raises(apple_mod.AppleVerificationError) as exc:
        apple_mod.verify_apple_identity_token(forged, audiences=[_AUDIENCE])
    assert "alg" in str(exc.value).lower()


def test_malformed_header_rejected():
    with pytest.raises(apple_mod.AppleVerificationError):
        apple_mod.verify_apple_identity_token("not.a.jwt", audiences=[_AUDIENCE])


def test_coerce_apple_bool_handles_strings_and_booleans():
    assert apple_mod.coerce_apple_bool(True) is True
    assert apple_mod.coerce_apple_bool("true") is True
    assert apple_mod.coerce_apple_bool(False) is False
    assert apple_mod.coerce_apple_bool("false") is False
    assert apple_mod.coerce_apple_bool(None) is False
    assert apple_mod.coerce_apple_bool("yes") is False  # only the literal string 'true'
