"""Tests for authentication security."""
import pytest
from passlib.context import CryptContext


def test_password_hash_is_bcrypt():
    """Password hashes must use bcrypt, not SHA256."""
    from main import pwd_context
    hashed = pwd_context.hash("testpassword")
    # bcrypt hashes start with $2b$
    assert hashed.startswith("$2b$"), f"Expected bcrypt hash, got: {hashed[:10]}"


def test_password_verify_correct():
    from main import pwd_context
    hashed = pwd_context.hash("mypassword")
    assert pwd_context.verify("mypassword", hashed) is True


def test_password_verify_wrong():
    from main import pwd_context
    hashed = pwd_context.hash("mypassword")
    assert pwd_context.verify("wrongpassword", hashed) is False


def test_hardcoded_passwords_not_present():
    """Source code must not contain plaintext passwords."""
    with open("main.py") as f:
        source = f.read()
    for pw in ["user123", "kaikka123", "superpower123"]:
        assert pw not in source, f"Hardcoded password '{pw}' found in main.py"
