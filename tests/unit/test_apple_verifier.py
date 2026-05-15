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


def test_stale_jwks_served_when_fetch_fails(rsa_keys, monkeypatch):
    """If Apple's keys endpoint is transiently down, a previously
    cached JWKS should keep serving rather than blocking every sign-in.
    Apple rotates keys on a months-long cadence, so the prior set is
    almost certainly still valid.
    """
    import httpx
    from jose import jwk as jose_jwk

    # Prime the cache with the test JWK as if a real fetch had succeeded.
    _, public_pem = rsa_keys
    public_jwk = jose_jwk.construct(public_pem, algorithm="RS256").to_dict()
    public_jwk["kid"] = _KID
    public_jwk["alg"] = "RS256"
    public_jwk["use"] = "sig"
    apple_mod._cache["keys"] = [public_jwk]
    apple_mod._cache["fetched_at"] = 0.0  # Expired — would normally re-fetch.

    # Restore the real _fetch_jwks for this one test (autouse fixture
    # stubs it). Then break httpx.get so the fetch path fails.
    monkeypatch.setattr(apple_mod, "_fetch_jwks", apple_mod._fetch_jwks.__wrapped__ if hasattr(apple_mod._fetch_jwks, "__wrapped__") else apple_mod.__dict__["_fetch_jwks"])
    # Use module dict directly: the autouse fixture monkeypatch sets the
    # attribute, so we restore the original.
    import importlib
    importlib.reload(apple_mod)
    # Now re-prime cache on the reloaded module.
    apple_mod._cache["keys"] = [public_jwk]
    apple_mod._cache["fetched_at"] = 0.0

    def boom(*args, **kwargs):
        raise httpx.ConnectError("simulated apple outage")

    monkeypatch.setattr(httpx, "get", boom)

    # Mint a real token signed by our test key. Verification should
    # succeed using the stale cached JWKS.
    private_pem, _ = rsa_keys
    now = int(time.time())
    token = jwt.encode(
        {
            "iss": apple_mod.APPLE_ISSUER,
            "aud": _AUDIENCE,
            "sub": "001234.aabbccddeeff.5678",
            "email": "stale@example.com",
            "email_verified": "true",
            "iat": now,
            "exp": now + 600,
        },
        private_pem,
        algorithm="RS256",
        headers={"kid": _KID},
    )

    claims = apple_mod.verify_apple_identity_token(token, audiences=[_AUDIENCE])
    assert claims["email"] == "stale@example.com"


def test_no_cache_and_fetch_fails_still_raises(rsa_keys, monkeypatch):
    """If there is no cached JWKS AND the fetch fails, the verifier
    must raise — there's nothing valid to serve. This guards against
    the stale-fallback accidentally swallowing total failure.
    """
    import httpx
    import importlib
    importlib.reload(apple_mod)
    apple_mod._cache["keys"] = None
    apple_mod._cache["fetched_at"] = 0.0

    def boom(*args, **kwargs):
        raise httpx.ConnectError("simulated apple outage")

    monkeypatch.setattr(httpx, "get", boom)

    # Mint a syntactically valid token so the verifier reaches the
    # JWKS-fetch step rather than failing earlier on header parse.
    private_pem, _ = rsa_keys
    now = int(time.time())
    token = jwt.encode(
        {"iss": apple_mod.APPLE_ISSUER, "aud": _AUDIENCE, "sub": "x", "iat": now, "exp": now + 60},
        private_pem,
        algorithm="RS256",
        headers={"kid": _KID},
    )

    with pytest.raises(apple_mod.AppleVerificationError) as exc:
        apple_mod.verify_apple_identity_token(token, audiences=[_AUDIENCE])
    assert "fetch failed" in str(exc.value).lower()
