"""Unit tests for the server-to-server internal auth dependency."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.auth.internal import require_internal_auth


def test_accepts_correct_secret(monkeypatch):
    monkeypatch.setenv("BRANDISTA_INTERNAL_SECRET", "shhhh-this-is-the-internal-secret")
    # No exception = accepted. We pass the secret as the header value
    # the same way FastAPI's dependency injection would.
    require_internal_auth(x_brandista_internal_auth="shhhh-this-is-the-internal-secret")


def test_constant_time_comparison_does_not_leak_via_length(monkeypatch):
    monkeypatch.setenv("BRANDISTA_INTERNAL_SECRET", "right-secret")
    with pytest.raises(HTTPException) as exc:
        require_internal_auth(x_brandista_internal_auth="wrong")
    assert exc.value.status_code == 401
    with pytest.raises(HTTPException) as exc:
        require_internal_auth(x_brandista_internal_auth="right-secret-but-longer")
    assert exc.value.status_code == 401


def test_missing_header_is_401(monkeypatch):
    monkeypatch.setenv("BRANDISTA_INTERNAL_SECRET", "configured")
    with pytest.raises(HTTPException) as exc:
        require_internal_auth(x_brandista_internal_auth=None)
    assert exc.value.status_code == 401


def test_empty_header_is_401(monkeypatch):
    monkeypatch.setenv("BRANDISTA_INTERNAL_SECRET", "configured")
    with pytest.raises(HTTPException) as exc:
        require_internal_auth(x_brandista_internal_auth="")
    assert exc.value.status_code == 401


def test_unconfigured_env_is_503_not_silent_pass(monkeypatch):
    """Forgetting to set BRANDISTA_INTERNAL_SECRET in env must NOT
    silently let requests through. The dependency refuses fail-loud
    so the deploy mistake surfaces immediately."""
    monkeypatch.delenv("BRANDISTA_INTERNAL_SECRET", raising=False)
    with pytest.raises(HTTPException) as exc:
        require_internal_auth(x_brandista_internal_auth="any-value")
    assert exc.value.status_code == 503


def test_whitespace_only_env_is_503(monkeypatch):
    """A space-only env value reads as 'configured' to a naive check
    but is effectively no-auth. Treat as misconfigured."""
    monkeypatch.setenv("BRANDISTA_INTERNAL_SECRET", "   ")
    with pytest.raises(HTTPException) as exc:
        require_internal_auth(x_brandista_internal_auth="any-value")
    assert exc.value.status_code == 503


def test_whitespace_in_header_is_stripped_before_compare(monkeypatch):
    """Some proxies trim or pad headers. Trim on the input side so a
    routed-through request with cosmetic whitespace still validates."""
    monkeypatch.setenv("BRANDISTA_INTERNAL_SECRET", "exact-secret")
    require_internal_auth(x_brandista_internal_auth="  exact-secret  ")
